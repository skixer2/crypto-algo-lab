"""
Module 3 (alternative) — CNN Pattern Recognition Model

Replaces _detect_swings() + _analyze_structure() + _three_candle_trigger()
with a learned 1D CNN that outputs p(reversal | window).

Interface is identical to ScalpingModel → drop-in replacement for runner,
simulation, and graphing. The optimizer (module 6) needs a separate
CNN_PARAM_SPACE — see bottom of file.

Usage:
    from code.model_cnn import CNNModel, CNNModelParams

    model = CNNModel(CNNModelParams(), execution_tf="5m", bias_tfs=["1h"])
    model.update(row_5m, "5m")
    model.update(row_1h, "1h")
    action, size_pct, indicators = model.predict()

Training:
    from code.model_cnn import train_cnn
    train_cnn(model, data_files, execution_tf="5m", epochs=50)
"""

import logging
import pickle
from typing import Dict, List, Optional, Tuple, Literal
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# Phase 2 imports
from .template_matcher import TemplateMatcher

logger = logging.getLogger(__name__)

Action = Literal["long", "short", "flat"]

# ─── PyTorch imports ────────────────────────────────────────────────
try:
    import torch
    import torch.nn as _nn
    import torch.nn.functional as _F
    import torch.optim as _optim
    from torch.utils.data import DataLoader as _DataLoader
    from torch.utils.data import TensorDataset as _TensorDataset
    _torch_available = True
except ImportError:
    _torch_available = False


def _ensure_torch():
    if not _torch_available:
        raise ImportError("PyTorch required for CNN model. pip install torch")


# ═══════════════════════════════════════════════════════════════════════
# Parameters
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class CNNModelParams:
    """CNN-specific tunable parameters. Subset is shared with ModelParams."""

    # ── CNN architecture ──────────────────────────────────────────
    window_size: int = 60               # candles fed to CNN
    conv_filters: List[int] = field(default_factory=lambda: [32, 64, 128])
    kernel_sizes: List[int] = field(default_factory=lambda: [5, 5, 3])
    dropout: float = 0.3
    fc_units: int = 32

    # ── Inference threshold ───────────────────────────────────────
    reversal_threshold: float = 0.7     # p > this → signal

    # ── Shared with ModelParams (used by simulation/SL-TP) ────────
    rr_ratio: float = 2.0
    atr_stop_multiplier: float = 1.5
    atr_period: int = 14
    max_position_pct: float = 1.0
    leverage: int = 1

    # ── Bias / structure (unchanged from original model) ──────────
    swing_lookback: int = 5
    min_swing_distance: int = 3
    min_candles_for_bias: int = 20
    rejection_zone_pct: float = 0.005

    # ── Template matching (Phase 2) ───────────────────────────────
    template_enabled: bool = False               # enable template-based entry + features
    template_threshold: float = 0.85             # V/U score > this → direct entry signal
    template_widths: tuple = (5, 10, 15, 20)     # multi-scale detection widths
    template_signal_source: str = "denoised"      # "denoised", "raw", or "approx3"


# ═══════════════════════════════════════════════════════════════════════
# Bias CNN Parameters
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class BiasCNNParams:
    """Parameters for the bias-tf regime-classifier CNN."""

    # ── Architecture ─────────────────────────────────────────────
    window_size: int = 60               # candles (60 × 1H = 2.5 days context)
    conv_filters: List[int] = field(default_factory=lambda: [32, 64])
    kernel_sizes: List[int] = field(default_factory=lambda: [5, 5])
    dropout: float = 0.3
    fc_units: int = 32

    # ── Inference ────────────────────────────────────────────────
    confidence_threshold: float = 0.5    # regime call requires p > this
    stability_bars: int = 2              # regime must hold for N candles before switching

    # ── Labeling ─────────────────────────────────────────────────
    adx_threshold: float = 20.0          # ADX > this → trending (else ranging)
    sma_slope_period: int = 20           # candles for SMA slope calc
    swing_lookback: int = 5              # for structural HH/HL check


# ═══════════════════════════════════════════════════════════════════════
# 1D CNN Architectures
# ═══════════════════════════════════════════════════════════════════════

class ReversalCNN(_nn.Module):
    """
    1D CNN that scans a price window and outputs p(reversal).

    Input:  (batch, n_features, window_size)
    Output: (batch,) — probability in [0, 1]

    Lightweight: ~50K params, < 1ms forward pass on CPU.
    """

    def __init__(self, n_features: int, params: CNNModelParams):
        super().__init__()
        self.n_features = n_features
        self.window_size = params.window_size
        p = params

        # Build conv blocks dynamically
        in_ch = n_features
        self.conv_blocks = _nn.ModuleList()

        for filters, ks in zip(p.conv_filters, p.kernel_sizes):
            block = _nn.Sequential(
                _nn.Conv1d(in_ch, filters, kernel_size=ks, padding=ks // 2),
                _nn.BatchNorm1d(filters),
                _nn.ReLU(),
                _nn.MaxPool1d(2),
            )
            self.conv_blocks.append(block)
            in_ch = filters

        self.global_pool = _nn.AdaptiveAvgPool1d(1)

        self.head = _nn.Sequential(
            _nn.Flatten(),
            _nn.Linear(in_ch, p.fc_units),
            _nn.ReLU(),
            _nn.Dropout(p.dropout),
            _nn.Linear(p.fc_units, 1),
            _nn.Sigmoid(),
        )

    def forward(self, x):
        for block in self.conv_blocks:
            x = block(x)
        x = self.global_pool(x)
        return self.head(x).squeeze(-1)


class BiasCNN(_nn.Module):
    """
    1D CNN regime classifier for bias timeframes (e.g. 1H, 4H).

    Input:  (batch, n_features, window_size)
    Output: (batch, 3) — softmax probabilities for [bullish, bearish, ranging]

    Same conv backbone as ReversalCNN, but with a 3-class softmax head.
    ~40K params, < 1ms forward pass on CPU.
    """

    def __init__(self, n_features: int, params: "BiasCNNParams"):
        super().__init__()
        self.n_features = n_features
        self.window_size = params.window_size
        p = params

        in_ch = n_features
        self.conv_blocks = _nn.ModuleList()
        for filters, ks in zip(p.conv_filters, p.kernel_sizes):
            block = _nn.Sequential(
                _nn.Conv1d(in_ch, filters, kernel_size=ks, padding=ks // 2),
                _nn.BatchNorm1d(filters),
                _nn.ReLU(),
                _nn.MaxPool1d(2),
            )
            self.conv_blocks.append(block)
            in_ch = filters

        self.global_pool = _nn.AdaptiveAvgPool1d(1)

        self.head = _nn.Sequential(
            _nn.Flatten(),
            _nn.Linear(in_ch, p.fc_units),
            _nn.ReLU(),
            _nn.Dropout(p.dropout),
            _nn.Linear(p.fc_units, 3),
            _nn.Softmax(dim=-1),
        )

    def forward(self, x):
        for block in self.conv_blocks:
            x = block(x)
        x = self.global_pool(x)
        return self.head(x)


# ═══════════════════════════════════════════════════════════════════════
# Feature Extraction
# ═══════════════════════════════════════════════════════════════════════

def extract_features(candles: List[dict], window_size: int = 60,
                    use_wavelet: bool = True,
                    template_scores: Optional[np.ndarray] = None) -> Optional[np.ndarray]:
    """
    Extract normalized feature tensor from the last `window_size` candles.

    Returns: (n_features, window_size) numpy array, or None if too few candles.

    Features:
      0: close (z-score normalized)
      1: high-low range / close   (volatility proxy)
      2: close / open - 1         (candle direction + magnitude)
      3: volume (log + z-score)
      4: RSI-14
      5: ATR-14 / close           (normalized volatility)
      6: close / SMA-20 - 1       (deviation from moving average)

    When use_wavelet=True (Phase 1):
      7-10: wavelet detail coefficients levels 1-4 (z-score per level)

    When template matching is added (Phase 2):
      template_scores of shape (4, window_size): added as channels 11-14
    """
    if len(candles) < window_size:
        return None

    window = candles[-window_size:]

    closes = np.array([c["close"] for c in window], dtype=np.float64)
    opens = np.array([c["open"] for c in window], dtype=np.float64)
    highs = np.array([c["high"] for c in window], dtype=np.float64)
    lows = np.array([c["low"] for c in window], dtype=np.float64)
    volumes = np.array([c.get("volume", 0) for c in window], dtype=np.float64)

    eps = 1e-10
    features = []

    # 0: Close (z-score)
    c_mean, c_std = closes.mean(), closes.std()
    features.append((closes - c_mean) / (c_std + eps) if c_std > eps else np.zeros_like(closes))

    # 1: Normalized range
    body = (highs - lows) / (closes + eps)
    features.append(body)

    # 2: Candle direction
    direction = closes / (opens + eps) - 1.0
    features.append(direction)

    # 3: Volume (log + z-score)
    log_vol = np.log(volumes + eps)
    v_mean, v_std = log_vol.mean(), log_vol.std()
    features.append((log_vol - v_mean) / (v_std + eps) if v_std > eps else np.zeros_like(log_vol))

    # 4: RSI-14
    features.append(_compute_rsi(closes, period=14))

    # 5: ATR-14 / close
    atr_vals = _compute_atr_series(highs, lows, closes, period=14)
    features.append(atr_vals / (closes + eps))

    # 6: Close / SMA-20 - 1
    sma20 = np.convolve(closes, np.ones(20)/20, mode='same')
    sma20[:19] = sma20[19]  # fill head
    features.append(closes / (sma20 + eps) - 1.0)

    # ── Phase 1: Wavelet detail coefficients ─────────────────────
    if use_wavelet:
        try:
            from .wavelet_utils import wavelet_features_for_candles
            wf = wavelet_features_for_candles(window, n_levels=4)
            if wf is not None:
                features = np.vstack([features, wf])
        except ImportError:
            pass  # PyWavelets not installed — skip wavelet features

    # ── Phase 2: Template matching scores ─────────────────────────
    if template_scores is not None and template_scores.shape[1] == window_size:
        features = np.vstack([features, template_scores])

    return np.stack(features, axis=0).astype(np.float32)


def extract_features_with_bias(
    candles: List[dict],
    window_size: int = 60,
    bias_dist: Optional[Tuple[float, float, float]] = None,
    use_wavelet: bool = True,
    template_scores: Optional[np.ndarray] = None,
) -> Optional[np.ndarray]:
    """
    Same as extract_features() but appends bias CNN outputs as additional
    channels (p_bull, p_bear, p_range) and optionally template scores.

    These are broadcast as constant-valued channels across the time
    dimension, giving the execution CNN context about the higher-TF regime.
    """
    base = extract_features(candles, window_size, use_wavelet=use_wavelet,
                           template_scores=template_scores)
    if base is None:
        return None

    if bias_dist is not None:
        p_bull, p_bear, p_range = bias_dist
        window_len = base.shape[1]
        bias_channels = np.array([
            np.full(window_len, p_bull, dtype=np.float32),
            np.full(window_len, p_bear, dtype=np.float32),
            np.full(window_len, p_range, dtype=np.float32),
        ])
        base = np.vstack([base, bias_channels])

    return base.astype(np.float32)


def _compute_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Vectorized RSI."""
    deltas = np.diff(closes, prepend=closes[0])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.zeros_like(closes)
    avg_loss = np.zeros_like(closes)

    # SMA seed
    if len(closes) > period:
        avg_gain[period] = gains[1:period+1].mean()
        avg_loss[period] = losses[1:period+1].mean()

        # Wilder smoothing
        for i in range(period + 1, len(closes)):
            avg_gain[i] = (avg_gain[i-1] * (period-1) + gains[i]) / period
            avg_loss[i] = (avg_loss[i-1] * (period-1) + losses[i]) / period

    eps = 1e-10
    rs = avg_gain / (avg_loss + eps)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi[:period] = 50.0
    return rsi


def _compute_atr_series(highs, lows, closes, period=14) -> np.ndarray:
    """Vectorized ATR."""
    n = len(closes)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i-1]),
                     abs(lows[i] - closes[i-1]))
    tr[0] = highs[0] - lows[0]

    atr = np.zeros(n)
    if n > period:
        atr[period] = tr[1:period+1].mean()
        for i in range(period+1, n):
            atr[i] = (atr[i-1] * (period-1) + tr[i]) / period
    atr[:period] = atr[period] if n > period else tr.mean()
    return atr


# ═══════════════════════════════════════════════════════════════════════
# Bias CNN — Regime Labeling
# ═══════════════════════════════════════════════════════════════════════

def _label_bias_windows(
    candles: List[dict],
    window_size: int = 60,
    adx_threshold: float = 20.0,
    sma_slope_period: int = 20,
    swing_lookback: int = 5,
) -> np.ndarray:
    """
    Auto-label each candle position as regime: 0=bullish, 1=bearish, 2=ranging.

    Labels are assigned to the LAST candle of each window (causal — no lookahead).
    Uses three signals with a priority chain:

    1. SMA slope direction (bull/bear signal)
    2. ADX strength (trending vs ranging filter)
    3. Swing structure (HH/HL confirms bull, LH/LL confirms bear)

    Heuristic (per window ending at i):
      - ADX < adx_threshold → ranging (regardless of other signals)
      - SMA slope > 0 AND HH+HL structure → bullish
      - SMA slope < 0 AND LH+LL structure → bearish
      - Everything else → ranging

    Returns: (n_candles,) array of ints {0, 1, 2}.
    First window_size-1 positions are filled with 2 (ranging / unknown).
    """
    n = len(candles)
    labels = np.full(n, 2, dtype=np.int64)  # default: ranging

    if n < window_size + sma_slope_period:
        return labels

    closes = np.array([c["close"] for c in candles], dtype=np.float64)
    highs  = np.array([c["high"]  for c in candles], dtype=np.float64)
    lows   = np.array([c["low"]   for c in candles], dtype=np.float64)
    eps = 1e-10

    # ── Rolling ADX (simplified Wilder) ───────────────────────────
    adx_period = 14
    tr  = np.zeros(n)
    pdm = np.zeros(n)
    ndm = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i-1]),
                     abs(lows[i]  - closes[i-1]))
        up_move = highs[i] - highs[i-1]
        dn_move = lows[i-1]  - lows[i]
        pdm[i] = up_move if up_move > dn_move and up_move > 0 else 0
        ndm[i] = dn_move if dn_move > up_move and dn_move > 0 else 0

    # Wilder smoothing for TR, +DM, -DM
    def _wilder_smooth(series, period):
        out = series.copy()
        if n > period:
            out[period] = series[1:period+1].mean()
            for i in range(period+1, n):
                out[i] = (out[i-1] * (period-1) + series[i]) / period
        return out

    tr_sm  = _wilder_smooth(tr,  adx_period)
    pdm_sm = _wilder_smooth(pdm, adx_period)
    ndm_sm = _wilder_smooth(ndm, adx_period)

    pdi = 100.0 * pdm_sm / (tr_sm + eps)
    ndi = 100.0 * ndm_sm / (tr_sm + eps)
    dx  = 100.0 * np.abs(pdi - ndi) / (pdi + ndi + eps)
    adx = _wilder_smooth(dx, adx_period)

    # ── Rolling SMA slope (percentage per candle) ─────────────────
    sma = np.zeros(n)
    running_sum = 0.0
    for i in range(n):
        running_sum += closes[i]
        if i >= sma_slope_period:
            running_sum -= closes[i - sma_slope_period]
        sma[i] = running_sum / min(i + 1, sma_slope_period)
    sma[:sma_slope_period] = sma[sma_slope_period]  # fill head

    # SMA slope: (sma[-1] - sma[-slope_period]) / sma[-slope_period]
    slope = np.zeros(n)
    for i in range(sma_slope_period, n):
        slope[i] = (sma[i] - sma[i - sma_slope_period]) / (sma[i - sma_slope_period] + eps)

    # ── Swing structure check per window ──────────────────────────
    # Simple: detect if last 2 swing highs/lows imply HH/HL or LH/LL
    lb = swing_lookback

    def _detect_swings_local(h, l, start, end):
        """Return (high_points, low_points) as lists of indices."""
        hp, lp = [], []
        for i in range(start + lb, end - lb):
            if all(h[j] <= h[i] for j in range(i - lb, i + lb + 1)):
                hp.append(i)
            if all(l[j] >= l[i] for j in range(i - lb, i + lb + 1)):
                lp.append(i)
        return hp, lp

    def _structure_from_swings(highs_idx, lows_idx, h_arr, l_arr):
        """Return 'bullish', 'bearish', or 'neutral' from last 2 of each."""
        if len(highs_idx) < 2 or len(lows_idx) < 2:
            return "neutral"
        h1, h2 = h_arr[highs_idx[-2]], h_arr[highs_idx[-1]]
        l1, l2 = l_arr[lows_idx[-2]],  l_arr[lows_idx[-1]]
        if h2 > h1 and l2 > l1:
            return "bullish"
        if h2 < h1 and l2 < l1:
            return "bearish"
        return "neutral"

    h_arr, l_arr = highs, lows  # for closure in inner functions

    # ── Assign labels: iterate windows ────────────────────────────
    for i in range(window_size, n):
        w_start = i - window_size

        # ADX: use recent value (end of window)
        current_adx = adx[i]

        if current_adx < adx_threshold:
            labels[i] = 2  # ranging
            continue

        # SMA slope
        current_slope = slope[i]

        # Swing structure within window
        hp, lp = _detect_swings_local(highs, lows, w_start, i)
        structure = _structure_from_swings(hp, lp, h_arr, l_arr)

        # Determine regime
        if current_slope > 0 and structure in ("bullish", "neutral"):
            labels[i] = 0  # bullish
        elif current_slope < 0 and structure in ("bearish", "neutral"):
            labels[i] = 1  # bearish
        else:
            labels[i] = 2  # ranging

    return labels


# ═══════════════════════════════════════════════════════════════════════
# CNN Model (same interface as ScalpingModel)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SwingPoint:
    """A detected local extremum — same structure as model.py."""
    idx: int
    timestamp: pd.Timestamp
    price: float
    kind: str  # "high" | "low"


class CNNModel:
    """
    Pure signal generator using a 1D CNN for pattern recognition.

    Same interface as ScalpingModel → drop-in replacement.

    Keeps swing-point logic for BIAS DETECTION only (the CNN doesn't
    determine trend direction). The CNN replaces:
      - _detect_swings() on execution TF
      - _analyze_structure() on execution TF
      - _three_candle_trigger()

    What stays:
      - Bias TF swing detection + trend analysis (1H direction)
      - Rejection zone check
      - SL/TP calculation (ATR-based)

    Parameters
    ----------
    params : CNNModelParams
    execution_tf : str
    bias_tfs : List[str]
    model_path : str or None
        Path to a saved .pt file with trained CNN weights.
        If None, CNN outputs random noise → model won't trade.
    """

    def __init__(
        self,
        params: Optional[CNNModelParams] = None,
        execution_tf: str = "5m",
        bias_tfs: Optional[List[str]] = None,
        model_path: Optional[str] = None,
        bias_model_path: Optional[str] = None,
        bias_params: Optional[BiasCNNParams] = None,
    ):
        self.params = params or CNNModelParams()
        self.p = self.params
        self.execution_tf = execution_tf
        self.bias_tfs = bias_tfs or ["1h"]
        self.bias_params = bias_params or BiasCNNParams()

        # ── Storage ───────────────────────────────────────────────
        self.candles: Dict[str, list] = {}
        for tf in [execution_tf] + self.bias_tfs:
            self.candles[tf] = []
        self.swings: Dict[str, list] = {tf: [] for tf in self.bias_tfs}

        # ── Feature counts (must exist before load) ────────────────
        self._n_features: int = 0
        self._feature_count_detected: bool = False
        self._bias_n_features: int = 0
        self._bias_feature_count_detected: bool = False

        # ── CNN (execution TF) ────────────────────────────────────
        self._cnn: Optional[ReversalCNN] = None
        self._model_path = model_path
        if model_path and Path(model_path).exists():
            self.load(model_path)

        # ── Bias CNN (bias TF regime classifier) ──────────────────
        self._bias_cnn: Optional[BiasCNN] = None
        self._bias_model_path: Optional[str] = bias_model_path
        if bias_model_path and Path(bias_model_path).exists():
            self._load_bias_cnn(bias_model_path)

        # ── Bias regime stability tracking ────────────────────────
        self._bias_regime_history: List[int] = []  # rolling last-N regime calls

        # ── Template matching (Phase 2) ──────────────────────────
        self._template_matcher: Optional[TemplateMatcher] = None
        if self.p.template_enabled:
            self._template_matcher = TemplateMatcher(
                widths=self.p.template_widths,
                signal_source=self.p.template_signal_source,
            )
            logger.info(
                f"CNNModel: template matching ENABLED "
                f"(threshold={self.p.template_threshold}, "
                f"widths={self.p.template_widths})"
            )

        # ── Cached ────────────────────────────────────────────────
        self._last_bias: str = "neutral"
        self._last_bias_dist: Tuple[float, float, float] = (0.0, 0.0, 1.0)
        self._last_indicators: Dict = {}

    # ── Data ingestion ──────────────────────────────────────────────

    def update(self, candle_row, tf: str) -> None:
        """Feed one candle. Same signature as ScalpingModel.update()."""
        data = self._to_dict(candle_row)
        if tf not in self.candles:
            self.candles[tf] = []
        self.candles[tf].append(data)

        # Only detect swings on bias TFs (not execution TF — CNN handles that)
        if tf in self.bias_tfs:
            self._detect_swings(tf)

    def _to_dict(self, row) -> dict:
        if isinstance(row, pd.Series):
            return {
                "timestamp": row.name,
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": float(row.get("volume", 0)),
            }
        if isinstance(row, pd.DataFrame):
            return {
                "timestamp": row.index[0],
                "open": float(row["open"].iloc[0]), "high": float(row["high"].iloc[0]),
                "low": float(row["low"].iloc[0]), "close": float(row["close"].iloc[0]),
                "volume": float(row.get("volume", pd.Series([0])).iloc[0]),
            }
        return {
            "timestamp": row.get("timestamp"),
            "open": float(row.get("open", 0)), "high": float(row.get("high", 0)),
            "low": float(row.get("low", 0)), "close": float(row.get("close", 0)),
            "volume": float(row.get("volume", 0)),
        }

    # ── Swing detection (bias TFs only — same logic as ScalpingModel) ──

    def _detect_swings(self, tf: str) -> None:
        candles = self.candles[tf]
        swings = self.swings[tf]
        lb = self.p.swing_lookback

        if len(candles) < 2 * lb + 1:
            return

        last_checked = swings[-1].idx if swings else lb - 1
        start = max(lb, last_checked - lb)
        end = len(candles) - lb

        for i in range(start, end):
            ch, cl = candles[i]["high"], candles[i]["low"]

            is_high = all(candles[j]["high"] <= ch for j in range(i - lb, i + lb + 1))
            if is_high:
                sp = SwingPoint(idx=i, timestamp=candles[i]["timestamp"],
                                price=ch, kind="high")
                if not self._too_close(sp, swings):
                    swings.append(sp)

            is_low = all(candles[j]["low"] >= cl for j in range(i - lb, i + lb + 1))
            if is_low:
                sp = SwingPoint(idx=i, timestamp=candles[i]["timestamp"],
                                price=cl, kind="low")
                if not self._too_close(sp, swings):
                    swings.append(sp)

        swings.sort(key=lambda s: s.idx)

    def _too_close(self, sp: SwingPoint, swings: List[SwingPoint]) -> bool:
        count = 0
        for prev in reversed(swings):
            if prev.kind == sp.kind:
                count += 1
                if abs(sp.idx - prev.idx) < self.p.min_swing_distance:
                    return True
                if count >= 3:
                    break
        return False

    # ── Market structure (bias TFs only) ────────────────────────────

    @staticmethod
    def _get_alternating_swings(swings: List[SwingPoint], n: int = 4) -> List[SwingPoint]:
        if len(swings) < 2:
            return []
        result = [swings[-1]]
        for s in reversed(swings[:-1]):
            if s.kind != result[-1].kind:
                result.append(s)
            if len(result) >= n:
                break
        result.reverse()
        return result

    def _analyze_bias(self) -> str:
        """Determine trend from primary bias TF."""
        primary = self.bias_tfs[0] if self.bias_tfs else None
        if not primary:
            return "neutral"
        swings = self.swings.get(primary, [])
        recent = self._get_alternating_swings(swings, n=4)
        if len(recent) < 3:
            return "neutral"
        highs = [s.price for s in recent if s.kind == "high"]
        lows = [s.price for s in recent if s.kind == "low"]
        if len(highs) >= 2 and len(lows) >= 2:
            h1, h2 = highs[-2], highs[-1]
            l1, l2 = lows[-2], lows[-1]
            if h2 > h1 and l2 > l1:
                return "bullish"
            if h2 < h1 and l2 < l1:
                return "bearish"
        return "neutral"

    # ── Rejection zone ───────────────────────────────────────────────

    def _in_rejection_zone(self) -> Tuple[bool, str]:
        bias_tf = self.bias_tfs[0] if self.bias_tfs else None
        if not bias_tf:
            return False, ""
        if len(self.swings.get(bias_tf, [])) < 2:
            return False, ""
        exec_candles = self.candles.get(self.execution_tf, [])
        if not exec_candles:
            return False, ""

        price = exec_candles[-1]["close"]
        t = self.p.rejection_zone_pct
        bias_swings = self.swings[bias_tf]
        highs = [s for s in bias_swings if s.kind == "high"]
        lows = [s for s in bias_swings if s.kind == "low"]

        if highs:
            last_high = highs[-1]
            if abs(price - last_high.price) / last_high.price < t:
                return True, "resistance"
        if lows:
            last_low = lows[-1]
            if abs(price - last_low.price) / last_low.price < t:
                return True, "support"
        return False, ""

    # ── ATR ──────────────────────────────────────────────────────────

    def _compute_atr(self, candles: List[dict]) -> float:
        n = self.p.atr_period
        if len(candles) < n + 1:
            return 0.0
        trs = []
        for i in range(-n, 0):
            h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        return float(np.mean(trs))

    # ── CNN access ───────────────────────────────────────────────────

    def _ensure_cnn(self):
        """Lazy-init CNN. Auto-detects feature count from first window."""
        if self._cnn is not None:
            return
        if not self._feature_count_detected:
            self._detect_n_features()
        self._cnn = ReversalCNN(self._n_features, self.p)

    def _detect_n_features(self):
        """Run extract_features on current buffer to determine channel count."""
        exec_candles = self.candles.get(self.execution_tf, [])
        if len(exec_candles) >= self.p.window_size:
            feats = extract_features(exec_candles, self.p.window_size)
            if feats is not None:
                self._n_features = feats.shape[0]
                self._feature_count_detected = True
                logger.info(f"CNNModel: auto-detected {self._n_features} features")
        if not self._feature_count_detected:
            # Fallback: assume wavelet available → 11 channels
            self._n_features = 11
            self._feature_count_detected = True

    @property
    def has_trained_model(self) -> bool:
        """True if a trained execution CNN is loaded."""
        return self._cnn is not None and self._model_path is not None

    @property
    def has_bias_cnn(self) -> bool:
        """True if a trained bias CNN is loaded."""
        return self._bias_cnn is not None and self._bias_model_path is not None

    # ── Bias CNN access ────────────────────────────────────────────

    def _detect_bias_n_features(self):
        """Run extract_features on bias TF buffer to determine channel count."""
        primary = self.bias_tfs[0] if self.bias_tfs else None
        if not primary:
            self._bias_n_features = 11
            self._bias_feature_count_detected = True
            return
        bias_candles = self.candles.get(primary, [])
        if len(bias_candles) >= self.bias_params.window_size:
            feats = extract_features(bias_candles, self.bias_params.window_size)
            if feats is not None:
                self._bias_n_features = feats.shape[0]
                self._bias_feature_count_detected = True
                logger.info(f"BiasCNN: auto-detected {self._bias_n_features} features")
                return
        self._bias_n_features = 11
        self._bias_feature_count_detected = True

    def _ensure_bias_cnn(self):
        """Lazy-init bias CNN."""
        if self._bias_cnn is not None:
            return
        if not self._bias_feature_count_detected:
            self._detect_bias_n_features()
        self._bias_cnn = BiasCNN(self._bias_n_features, self.bias_params)

    def _load_bias_cnn(self, path: str) -> None:
        """Load trained bias CNN weights from a .pt file."""
        _ensure_torch()
        import torch
        state = torch.load(path, map_location="cpu", weights_only=True)
        saved_features = state.get("n_features", self._bias_n_features)
        if saved_features and saved_features != self._bias_n_features:
            self._bias_n_features = saved_features
            self._bias_feature_count_detected = True
        self._ensure_bias_cnn()
        self._bias_cnn.load_state_dict(state["model"])
        self._bias_model_path = path
        tl = state.get('train_loss', None)
        tl_str = f"{tl:.4f}" if tl is not None else "?"
        logger.info(f"BiasCNN: loaded weights from {path} (train_loss={tl_str})")

    def load_bias_cnn(self, path: str) -> None:
        """Public method to load bias CNN weights."""
        self._load_bias_cnn(path)

    def save_bias_cnn(self, path: str) -> None:
        """Save trained bias CNN weights."""
        _ensure_torch()
        import torch
        self._ensure_bias_cnn()
        torch.save({
            "model": self._bias_cnn.state_dict(),
            "n_features": self._bias_n_features,
        }, path)
        self._bias_model_path = path
        logger.info(f"BiasCNN: saved weights to {path}")

    def _predict_bias(self) -> Tuple[str, Tuple[float, float, float]]:
        """
        Run bias CNN forward pass and return (regime_str, (p_bull, p_bear, p_range)).

        Falls back to swing-based _analyze_bias() if bias CNN is not loaded.
        """
        if not self.has_bias_cnn:
            return self._analyze_bias(), (0.0, 0.0, 1.0)

        primary = self.bias_tfs[0] if self.bias_tfs else None
        if not primary:
            return "neutral", (0.0, 0.0, 1.0)

        bias_candles = self.candles.get(primary, [])
        if len(bias_candles) < self.bias_params.window_size:
            return "neutral", (0.0, 0.0, 1.0)

        _ensure_torch()
        import torch

        features = extract_features(bias_candles, self.bias_params.window_size)
        if features is None:
            return "neutral", (0.0, 0.0, 1.0)

        tensor = torch.from_numpy(features).unsqueeze(0)
        self._bias_cnn.eval()
        with torch.no_grad():
            probs = self._bias_cnn.forward(tensor).squeeze(0)  # (3,)
        p_bull, p_bear, p_range = probs[0].item(), probs[1].item(), probs[2].item()

        # ── Stability gate: regime only switches if sustained ─────
        regime_idx = int(torch.argmax(probs).item())
        self._bias_regime_history.append(regime_idx)
        max_hist = self.bias_params.stability_bars
        if len(self._bias_regime_history) > max_hist:
            self._bias_regime_history = self._bias_regime_history[-max_hist:]

        # Check if regime has been consistent
        if len(self._bias_regime_history) >= max_hist:
            consistent = all(r == regime_idx for r in self._bias_regime_history)
        else:
            consistent = True  # not enough history yet, trust the CNN

        if not consistent:
            # Stay with previous regime if current one isn't stable
            regime_idx = self._bias_regime_history[-2] if len(self._bias_regime_history) >= 2 else regime_idx

        idx_to_regime = {0: "bullish", 1: "bearish", 2: "neutral"}
        regime = idx_to_regime[regime_idx]

        return regime, (p_bull, p_bear, p_range)

    def load(self, path: str) -> None:
        """Load trained CNN weights from a .pt file."""
        _ensure_torch()
        import torch
        state = torch.load(path, map_location="cpu", weights_only=True)
        # Use the saved n_features to rebuild if needed
        saved_features = state.get("n_features", self._n_features)
        if saved_features and saved_features != self._n_features:
            self._n_features = saved_features
            self._feature_count_detected = True
        self._ensure_cnn()
        self._cnn.load_state_dict(state["model"])
        self._model_path = path
        tl = state.get('train_loss', None)
        tl_str = f"{tl:.4f}" if tl is not None else "?"
        logger.info(f"CNNModel: loaded weights from {path} (train_loss={tl_str})")

    def save(self, path: str) -> None:
        """Save trained CNN weights."""
        _ensure_torch()
        import torch
        self._ensure_cnn()
        torch.save({"model": self._cnn.state_dict(), "n_features": self._n_features}, path)
        self._model_path = path
        logger.info(f"CNNModel: saved weights to {path}")

    # ── Predict (main entry point) ───────────────────────────────────

    def predict(self, allow_shorts: bool = True) -> Tuple[Action, float, Dict]:
        """
        Generate a trading signal.

        Returns:
            (action, position_size_pct, indicators)
            indicators includes "p_reversal" (the CNN output) and SL/TP.
        """
        exec_candles = self.candles.get(self.execution_tf, [])
        indicators: Dict = {
            "bias": "neutral",
            "p_reversal": 0.0,
            "v_bottom_score": 0.0,
            "u_bottom_score": 0.0,
            "v_top_score": 0.0,
            "u_top_score": 0.0,
            "entry_price": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "signal": "none",
        }

        # ── Guard ─────────────────────────────────────────────────
        if len(exec_candles) < self.p.window_size:
            return "flat", 0.0, indicators

        primary_bias = self.bias_tfs[0] if self.bias_tfs else None
        if primary_bias:
            bias_candles = self.candles.get(primary_bias, [])
            if len(bias_candles) < self.p.min_candles_for_bias:
                return "flat", 0.0, indicators

        # ── 1. Bias (CNN-based if available, else swing-based) ─────
        bias, bias_dist = self._predict_bias()
        self._last_bias = bias
        self._last_bias_dist = bias_dist
        indicators["bias"] = bias
        indicators["bias_dist"] = {
            "p_bull": bias_dist[0],
            "p_bear": bias_dist[1],
            "p_range": bias_dist[2],
        }

        # ── 2. Rejection zone (unchanged) ─────────────────────────
        in_zone, zone_type = self._in_rejection_zone()
        indicators["in_rejection_zone"] = in_zone
        indicators["zone_type"] = zone_type

        # ── 3. Template matching (Phase 2) ───────────────────────
        template_feats: Optional[np.ndarray] = None
        v_bottom_live, u_bottom_live, v_top_live, u_top_live = 0.0, 0.0, 0.0, 0.0

        if self._template_matcher is not None:
            # Full-window scores for CNN features
            template_feats = self._template_matcher.feature_scores(
                exec_candles, self.p.window_size
            )
            # Live (forward-only) scores for entry decision
            live_scores = self._template_matcher.match_live(exec_candles)
            v_bottom_live = live_scores["v_bottom"]
            u_bottom_live = live_scores["u_bottom"]
            v_top_live = live_scores["v_top"]
            u_top_live = live_scores["u_top"]

            indicators["v_bottom_score"] = v_bottom_live
            indicators["u_bottom_score"] = u_bottom_live
            indicators["v_top_score"] = v_top_live
            indicators["u_top_score"] = u_top_live

        # ── 4. CNN forward pass (replaces MSS + 3-candle trigger) ─
        self._ensure_cnn()
        _ensure_torch()
        import torch

        # Use bias-aware features when bias CNN is available
        if self.has_bias_cnn:
            features = extract_features_with_bias(
                exec_candles, self.p.window_size,
                bias_dist=bias_dist,
                template_scores=template_feats,
            )
        else:
            features = extract_features(
                exec_candles, self.p.window_size,
                template_scores=template_feats,
            )

        if features is None:
            return "flat", 0.0, indicators

        # Adjust CNN input channels if bias features changed n_features
        # (lazy re-init: ReversalCNN is cheap to reconstruct)
        if features.shape[0] != self._n_features:
            logger.info(
                f"CNNModel: feature count changed ({self._n_features} → {features.shape[0]}), "
                f"re-initializing CNN"
            )
            self._n_features = features.shape[0]
            self._cnn = ReversalCNN(self._n_features, self.p)
            if self.has_trained_model and self._model_path:
                logger.warning(
                    "Bias CNN features changed input dimension. "
                    "Execution CNN must be re-trained with bias-aware features."
                )

        tensor = torch.from_numpy(features).unsqueeze(0)  # (1, n_features, window)
        self._cnn.eval()
        with torch.no_grad():
            p_reversal = self._cnn.forward(tensor).item()
        indicators["p_reversal"] = p_reversal

        # ── 5. Entry logic ────────────────────────────────────────
        price = exec_candles[-1]["close"]
        entry_signal: Optional[str] = None

        # Combined entry: CNN p_reversal OR template score above threshold
        if bias == "bullish" and in_zone:
            cnn_long = p_reversal > self.p.reversal_threshold
            template_long = (
                self.p.template_enabled
                and max(v_bottom_live, u_bottom_live) > self.p.template_threshold
            )
            if cnn_long or template_long:
                entry_signal = "long"
                indicators["entry_source"] = (
                    "cnn+template" if cnn_long and template_long
                    else "cnn" if cnn_long
                    else "template"
                )

        elif bias == "bearish" and allow_shorts and in_zone:
            cnn_short = p_reversal > self.p.reversal_threshold
            template_short = (
                self.p.template_enabled
                and max(v_top_live, u_top_live) > self.p.template_threshold
            )
            if cnn_short or template_short:
                entry_signal = "short"
                indicators["entry_source"] = (
                    "cnn+template" if cnn_short and template_short
                    else "cnn" if cnn_short
                    else "template"
                )

        if entry_signal:
            atr = self._compute_atr(exec_candles)
            stop_dist = self.p.atr_stop_multiplier * atr if atr > 0 else price * 0.01

            if entry_signal == "long":
                sl = price - stop_dist
                tp = price + stop_dist * self.p.rr_ratio
            else:
                sl = price + stop_dist
                tp = price - stop_dist * self.p.rr_ratio

            indicators.update({
                "signal": entry_signal,
                "entry_price": price,
                "stop_loss": sl,
                "take_profit": tp,
            })
            return entry_signal, self.p.max_position_pct, indicators

        indicators["entry_price"] = price

        # ── Bias-tf swings for graphing ───────────────────────────
        for tf in self.bias_tfs:
            swings = self.swings.get(tf, [])
            indicators[f"swings_{tf}_highs"] = [
                (s.timestamp, s.price) for s in swings if s.kind == "high"
            ]
            indicators[f"swings_{tf}_lows"] = [
                (s.timestamp, s.price) for s in swings if s.kind == "low"
            ]

        self._last_indicators = indicators
        return "flat", 0.0, indicators

    # ── Accessors ────────────────────────────────────────────────────

    def get_bias(self) -> str:
        return self._last_bias

    def get_indicators(self) -> Dict:
        return self._last_indicators


# ═══════════════════════════════════════════════════════════════════════
# Training
# ═══════════════════════════════════════════════════════════════════════

def _label_windows_from_swings(
    candles: List[dict],
    swing_lookback: int = 5,
    min_recovery_pct: float = 0.005,
    recovery_window: int = 10,
) -> np.ndarray:
    """
    Auto-label a candle list: 1 if the last candle is at/after a V-bottom
    reversal, 0 otherwise.

    Heuristic: local minimum followed by ≥min_recovery_pct recovery
    within recovery_window candles.

    This is a temporary labeling strategy. Phase 2 template matching
    will provide higher-quality labels.
    """
    n = len(candles)
    labels = np.zeros(n, dtype=np.float32)
    closes = np.array([c["close"] for c in candles])

    lb = swing_lookback
    for i in range(lb, n - recovery_window):
        c_i = closes[i]
        # Local minimum
        window_start = max(0, i - lb)
        window_end = min(n, i + lb + 1)
        if c_i <= closes[window_start:window_end].min():
            # Check recovery
            recovery = closes[i:i + recovery_window + 1]
            recovery_from_trough = (recovery[-1] - c_i) / c_i
            if recovery_from_trough > min_recovery_pct:
                labels[i + recovery_window] = 1.0

    return labels


def train_cnn(
    model: CNNModel,
    data_files: Dict[str, str],
    execution_tf: str = "5m",
    data_start: Optional[str] = None,
    data_end: Optional[str] = None,
    epochs: int = 50,
    batch_size: int = 64,
    lr: float = 1e-3,
    weight_decay: float = 1e-5,
    train_split: float = 0.70,
    validation_split: float = 0.15,
    # ── test gets the remainder: 1 - train_split - validation_split ──
    label_method: str = "swing_recovery",  # "swing_recovery" or "scalping_mss"
    save_path: Optional[str] = None,
    device: str = "cpu",
    positive_weight: float = 3.0,  # weight for positive class (V-bottoms are rarer)
    early_stopping_patience: int = 10,
    bias_model_path: Optional[str] = None,  # pre-trained bias CNN for context features
) -> Dict:
    """
    Train the execution CNN on historical data.

    Labels are generated automatically:
      - "swing_recovery": V-bottom = local min + X% recovery in Y candles
      - "scalping_mss": uses ScalpingModel MSS events as positive labels

    If bias_model_path is provided, the bias CNN is loaded and its
    regime predictions are injected as extra channels (features 11-13)
    during execution CNN training. This requires the bias CNN to have
    been pre-trained on the same time range.

    The CNN learns to output p(reversal | window) from raw features.

    Returns training metrics dict.
    """
    _ensure_torch()
    import torch

    # ── Load data ─────────────────────────────────────────────────
    df = pd.read_csv(data_files[execution_tf], parse_dates=["timestamp"],
                     index_col="timestamp")
    df.sort_index(inplace=True)
    if data_start:
        df = df[df.index >= pd.Timestamp(data_start)]
    if data_end:
        df = df[df.index <= pd.Timestamp(data_end)]

    candles = [
        {
            "timestamp": idx,
            "open": float(row["open"]), "high": float(row["high"]),
            "low": float(row["low"]), "close": float(row["close"]),
            "volume": float(row.get("volume", 0)),
        }
        for idx, row in df.iterrows()
    ]

    logger.info(f"Training data: {len(candles)} candles ({execution_tf})")

    # ── Generate labels ───────────────────────────────────────────
    if label_method == "swing_recovery":
        labels = _label_windows_from_swings(candles, swing_lookback=model.p.swing_lookback)
    elif label_method == "scalping_mss":
        # Use existing ScalpingModel to generate labels
        from .model import ScalpingModel, ModelParams
        label_model = ScalpingModel(ModelParams(), execution_tf=execution_tf)
        labels = np.zeros(len(candles), dtype=np.float32)
        for i, c in enumerate(candles):
            label_model.update(c, execution_tf)
            if i >= model.p.window_size:
                action, _, _ = label_model.predict()
                if action != "flat":
                    labels[i] = 1.0
    else:
        raise ValueError(f"Unknown label_method: {label_method}")

    n_pos = int(labels.sum())
    logger.info(f"Labels: {n_pos} positive / {len(labels)} total "
                 f"({100*n_pos/len(labels):.1f}%)")

    # ── Pre-compute bias context (if bias CNN is available) ───────
    bias_preds: Optional[List[Tuple[pd.Timestamp, Tuple[float, float, float]]]] = None
    if bias_model_path:
        logger.info("Bias CNN context: loading pre-trained bias model...")
        model.load_bias_cnn(bias_model_path)

        # Load bias TF data and run inference
        bias_tf = model.bias_tfs[0] if model.bias_tfs else "1h"
        if bias_tf not in data_files:
            logger.warning(f"Bias TF {bias_tf} not in data_files, skipping bias context")
        else:
            bias_df = pd.read_csv(data_files[bias_tf], parse_dates=["timestamp"],
                                   index_col="timestamp")
            bias_df.sort_index(inplace=True)
            bias_candles = [
                {"timestamp": idx,
                 "open": float(r["open"]), "high": float(r["high"]),
                 "low": float(r["low"]), "close": float(r["close"]),
                 "volume": float(r.get("volume", 0))}
                for idx, r in bias_df.iterrows()
            ]

            # Pre-compute bias predictions for every bias TF window
            import torch as _torch_inner
            bias_preds = []
            bp_ws = model.bias_params.window_size
            model._ensure_bias_cnn()
            model._bias_cnn.eval()
            for j in range(bp_ws, len(bias_candles)):
                b_window = bias_candles[j - bp_ws:j]
                b_feats = extract_features(b_window, bp_ws)
                if b_feats is not None:
                    tensor = _torch_inner.from_numpy(b_feats).unsqueeze(0)
                    with _torch_inner.no_grad():
                        probs = model._bias_cnn.forward(tensor).squeeze(0)
                    ts = bias_candles[j]["timestamp"]
                    bias_preds.append((
                        ts,
                        (probs[0].item(), probs[1].item(), probs[2].item()),
                    ))
            logger.info(f"Bias context: pre-computed {len(bias_preds)} bias predictions")

    # ── Build feature windows ─────────────────────────────────────
    ws = model.p.window_size
    X_list, y_list = [], []

    for i in range(ws, len(candles)):
        window = candles[i - ws:i]
        window_ts = candles[i]["timestamp"]

        # Look up bias context for this window
        bias_dist = None
        if bias_preds:
            # Find most recent bias prediction ≤ window timestamp
            for bts, bdist in reversed(bias_preds):
                if bts <= window_ts:
                    bias_dist = bdist
                    break
            # If no prior bias pred found (window starts before any bias data),
            # fall back to neutral distribution
            if bias_dist is None:
                bias_dist = (0.0, 0.0, 1.0)

        if bias_dist is not None:
            feats = extract_features_with_bias(window, ws, bias_dist=bias_dist)
        else:
            feats = extract_features(window, ws)

        if feats is not None:
            X_list.append(feats)
            y_list.append(labels[i])

    if len(X_list) == 0:
        raise ValueError("No training samples. Need more candles or smaller window.")

    X = np.stack(X_list, axis=0)  # (samples, features, window)
    y = np.array(y_list, dtype=np.float32)

    # ── Rebuild CNN if bias context changed n_features ────────────
    actual_features = X.shape[1]
    if actual_features != model._n_features:
        logger.info(
            f"Feature count changed ({model._n_features} → {actual_features}) "
            f"due to bias context. Rebuilding execution CNN."
        )
        model._n_features = actual_features
        model._cnn = ReversalCNN(actual_features, model.p)

    # ── Chronological train / valid / test split ──────────────────
    # No shuffle — time order must be preserved.
    # train | valid | test, each contiguous in time.
    n_total = len(X)
    n_train = int(n_total * train_split)
    n_valid = int(n_total * validation_split)
    # test gets whatever is left

    X_train, y_train = X[:n_train], y[:n_train]
    X_valid, y_valid = X[n_train:n_train + n_valid], y[n_train:n_train + n_valid]
    X_test, y_test   = X[n_train + n_valid:], y[n_train + n_valid:]

    logger.info(
        f"Split: train={len(X_train)} ({train_split:.0%}) | "
        f"valid={len(X_valid)} ({validation_split:.0%}) | "
        f"test={len(X_test)} ({(1-train_split-validation_split):.0%})"
    )

    train_ds = _TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    valid_ds = _TensorDataset(torch.from_numpy(X_valid), torch.from_numpy(y_valid))
    test_ds  = _TensorDataset(torch.from_numpy(X_test),  torch.from_numpy(y_test))
    train_loader = _DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    valid_loader = _DataLoader(valid_ds, batch_size=batch_size, shuffle=False)
    test_loader  = _DataLoader(test_ds,  batch_size=batch_size, shuffle=False)

    # ── Initialize CNN ────────────────────────────────────────────
    model._ensure_cnn()
    cnn = model._cnn

    # BCELoss matches sigmoid output. Class-weighted variant for imbalanced data.
    pos_weight_tensor = torch.tensor([positive_weight])

    def weighted_bce(preds, targets):
        """BCE with higher weight on positive examples (V-bottoms are rarer)."""
        eps = 1e-7
        preds = torch.clamp(preds, eps, 1 - eps)
        return -(
            positive_weight * targets * torch.log(preds)
            + (1 - targets) * torch.log(1 - preds)
        ).mean()

    criterion = weighted_bce

    optimizer_obj = _optim.Adam(cnn.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = _optim.lr_scheduler.ReduceLROnPlateau(
        optimizer_obj, mode='min', factor=0.5, patience=5
    )

    # ── Training loop ─────────────────────────────────────────────
    best_valid_loss = float("inf")
    patience_counter = 0
    history = {"train_loss": [], "valid_loss": [], "valid_acc": []}

    for epoch in range(epochs):
        # Train
        cnn.train()
        train_loss = 0.0
        for xb, yb in train_loader:
            optimizer_obj.zero_grad()
            preds = cnn.forward(xb)
            loss = criterion(preds, yb)
            loss.backward()
            optimizer_obj.step()
            train_loss += loss.item() * len(xb)
        train_loss /= len(train_loader.dataset)

        # Validate
        cnn.eval()
        valid_loss = 0.0
        correct = 0
        with torch.no_grad():
            for xb, yb in valid_loader:
                preds = cnn.forward(xb)
                loss = criterion(preds, yb)
                valid_loss += loss.item() * len(xb)
                correct += ((preds > 0.5) == yb).sum().item()
        valid_loss /= len(valid_loader.dataset)
        valid_acc = correct / len(valid_loader.dataset)

        scheduler.step(valid_loss)

        history["train_loss"].append(train_loss)
        history["valid_loss"].append(valid_loss)
        history["valid_acc"].append(valid_acc)

        if (epoch + 1) % 10 == 0 or epoch == 0:
            logger.info(
                f"Epoch {epoch+1:3d}/{epochs} | "
                f"train_loss={train_loss:.4f} | valid_loss={valid_loss:.4f} | "
                f"valid_acc={valid_acc:.3f}"
            )

        # Early stopping
        if valid_loss < best_valid_loss - 1e-4:
            best_valid_loss = valid_loss
            patience_counter = 0
            if save_path:
                model.save(save_path)
        else:
            patience_counter += 1
            if patience_counter >= early_stopping_patience:
                logger.info(f"Early stopping at epoch {epoch+1}")
                break

    logger.info(f"Training complete. Best valid_loss={best_valid_loss:.4f}")

    # ── Final evaluation on test set ──────────────────────────────
    cnn.eval()
    test_loss = 0.0
    test_correct = 0
    test_preds = []
    with torch.no_grad():
        for xb, yb in test_loader:
            preds = cnn.forward(xb)
            loss = criterion(preds, yb)
            test_loss += loss.item() * len(xb)
            test_correct += ((preds > 0.5) == yb).sum().item()
            test_preds.extend(preds.cpu().numpy().tolist())
    test_loss /= len(test_loader.dataset)
    test_acc = test_correct / len(test_loader.dataset) if len(test_loader.dataset) > 0 else 0.0

    # Precision/recall on test
    test_preds = np.array(test_preds)
    tp = ((test_preds > 0.5) & (y_test == 1)).sum()
    fp = ((test_preds > 0.5) & (y_test == 0)).sum()
    fn = ((test_preds <= 0.5) & (y_test == 1)).sum()
    test_precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    test_recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    logger.info(
        f"Test: loss={test_loss:.4f} | acc={test_acc:.3f} | "
        f"precision={test_precision:.3f} | recall={test_recall:.3f}"
    )

    return {
        "best_valid_loss": best_valid_loss,
        "final_valid_acc": history["valid_acc"][-1],
        "test_loss": test_loss,
        "test_acc": test_acc,
        "test_precision": test_precision,
        "test_recall": test_recall,
        "history": history,
        "epochs_run": epoch + 1,
        "n_train": len(X_train),
        "n_valid": len(X_valid),
        "n_test": len(X_test),
        "n_positive": n_pos,
    }


# ═══════════════════════════════════════════════════════════════════════
# Bias CNN Training
# ═══════════════════════════════════════════════════════════════════════

def train_bias_cnn(
    model: CNNModel,
    data_files: Dict[str, str],
    bias_tf: str = "1h",
    data_start: Optional[str] = None,
    data_end: Optional[str] = None,
    epochs: int = 50,
    batch_size: int = 64,
    lr: float = 1e-3,
    weight_decay: float = 1e-5,
    train_split: float = 0.70,
    validation_split: float = 0.15,
    save_path: Optional[str] = None,
    device: str = "cpu",
    early_stopping_patience: int = 10,
    class_weights: Optional[Tuple[float, float, float]] = None,
    # Above: optional per-class weights for CrossEntropyLoss.
    # Default: (1.0, 1.0, 0.6) — range slightly penalised to push bull/bear calls.
) -> Dict:
    """
    Train the bias CNN on bias-TF data (e.g. 1H candles).

    Uses auto-generated 3-class regime labels (bullish/bearish/ranging)
    via _label_bias_windows().

    The trained model is saved to model._bias_cnn — use model.save_bias_cnn()
    to persist.

    Returns training metrics dict.
    """
    _ensure_torch()
    import torch

    if class_weights is None:
        class_weights = (1.0, 1.0, 0.6)

    # ── Load data ─────────────────────────────────────────────────
    df = pd.read_csv(data_files[bias_tf], parse_dates=["timestamp"],
                     index_col="timestamp")
    df.sort_index(inplace=True)
    if data_start:
        df = df[df.index >= pd.Timestamp(data_start)]
    if data_end:
        df = df[df.index <= pd.Timestamp(data_end)]

    candles = [
        {
            "timestamp": idx,
            "open": float(row["open"]), "high": float(row["high"]),
            "low": float(row["low"]), "close": float(row["close"]),
            "volume": float(row.get("volume", 0)),
        }
        for idx, row in df.iterrows()
    ]

    logger.info(f"Bias CNN training data: {len(candles)} candles ({bias_tf})")

    # ── Generate regime labels ────────────────────────────────────
    bp = model.bias_params
    labels = _label_bias_windows(
        candles,
        window_size=bp.window_size,
        adx_threshold=bp.adx_threshold,
        sma_slope_period=bp.sma_slope_period,
        swing_lookback=bp.swing_lookback,
    )

    n_bull = int((labels == 0).sum())
    n_bear = int((labels == 1).sum())
    n_range = int((labels == 2).sum())
    logger.info(
        f"Bias labels: bull={n_bull} ({100*n_bull/len(labels):.1f}%) | "
        f"bear={n_bear} ({100*n_bear/len(labels):.1f}%) | "
        f"range={n_range} ({100*n_range/len(labels):.1f}%)"
    )

    # ── Build feature windows ─────────────────────────────────────
    ws = bp.window_size
    X_list, y_list = [], []

    for i in range(ws, len(candles)):
        window = candles[i - ws:i]
        feats = extract_features(window, ws)
        if feats is not None:
            X_list.append(feats)
            y_list.append(labels[i])

    if len(X_list) == 0:
        raise ValueError("No training samples. Need more candles or smaller window.")

    X = np.stack(X_list, axis=0)
    y = np.array(y_list, dtype=np.int64)

    # ── Chronological split ───────────────────────────────────────
    n_total = len(X)
    n_train = int(n_total * train_split)
    n_valid = int(n_total * validation_split)

    X_train, y_train = X[:n_train], y[:n_train]
    X_valid, y_valid = X[n_train:n_train + n_valid], y[n_train:n_train + n_valid]
    X_test, y_test   = X[n_train + n_valid:], y[n_train + n_valid:]

    logger.info(
        f"Bias split: train={len(X_train)} ({train_split:.0%}) | "
        f"valid={len(X_valid)} ({validation_split:.0%}) | "
        f"test={len(X_test)} ({(1-train_split-validation_split):.0%})"
    )

    train_ds = _TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    valid_ds = _TensorDataset(torch.from_numpy(X_valid), torch.from_numpy(y_valid))
    test_ds  = _TensorDataset(torch.from_numpy(X_test),  torch.from_numpy(y_test))
    train_loader = _DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    valid_loader = _DataLoader(valid_ds, batch_size=batch_size, shuffle=False)
    test_loader  = _DataLoader(test_ds,  batch_size=batch_size, shuffle=False)

    # ── Initialize bias CNN ───────────────────────────────────────
    model._ensure_bias_cnn()
    bcnn = model._bias_cnn

    # Weighted CrossEntropyLoss
    weight_tensor = torch.tensor(class_weights, dtype=torch.float32)
    criterion = _nn.CrossEntropyLoss(weight=weight_tensor)

    optimizer_obj = _optim.Adam(bcnn.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = _optim.lr_scheduler.ReduceLROnPlateau(
        optimizer_obj, mode='min', factor=0.5, patience=5
    )

    # ── Training loop ─────────────────────────────────────────────
    best_valid_loss = float("inf")
    patience_counter = 0
    history = {"train_loss": [], "valid_loss": [], "valid_acc": []}

    for epoch in range(epochs):
        bcnn.train()
        train_loss = 0.0
        for xb, yb in train_loader:
            optimizer_obj.zero_grad()
            logits = bcnn.forward(xb)
            loss = criterion(logits, yb)
            loss.backward()
            optimizer_obj.step()
            train_loss += loss.item() * len(xb)
        train_loss /= len(train_loader.dataset)

        # Validate
        bcnn.eval()
        valid_loss = 0.0
        correct = 0
        with torch.no_grad():
            for xb, yb in valid_loader:
                logits = bcnn.forward(xb)
                loss = criterion(logits, yb)
                valid_loss += loss.item() * len(xb)
                preds = torch.argmax(logits, dim=-1)
                correct += (preds == yb).sum().item()
        valid_loss /= len(valid_loader.dataset)
        valid_acc = correct / len(valid_loader.dataset)

        scheduler.step(valid_loss)

        history["train_loss"].append(train_loss)
        history["valid_loss"].append(valid_loss)
        history["valid_acc"].append(valid_acc)

        if (epoch + 1) % 10 == 0 or epoch == 0:
            logger.info(
                f"Bias epoch {epoch+1:3d}/{epochs} | "
                f"train_loss={train_loss:.4f} | valid_loss={valid_loss:.4f} | "
                f"valid_acc={valid_acc:.3f}"
            )

        if valid_loss < best_valid_loss - 1e-4:
            best_valid_loss = valid_loss
            patience_counter = 0
            if save_path:
                model.save_bias_cnn(save_path)
        else:
            patience_counter += 1
            if patience_counter >= early_stopping_patience:
                logger.info(f"Bias early stopping at epoch {epoch+1}")
                break

    logger.info(f"Bias training complete. Best valid_loss={best_valid_loss:.4f}")

    # ── Final evaluation on test set ───────────────────────────────
    bcnn.eval()
    test_loss = 0.0
    test_correct = 0
    all_preds = []
    with torch.no_grad():
        for xb, yb in test_loader:
            logits = bcnn.forward(xb)
            loss = criterion(logits, yb)
            test_loss += loss.item() * len(xb)
            preds = torch.argmax(logits, dim=-1)
            test_correct += (preds == yb).sum().item()
            all_preds.extend(preds.cpu().numpy().tolist())
    test_loss /= len(test_loader.dataset)
    test_acc = test_correct / len(test_loader.dataset) if len(test_loader.dataset) > 0 else 0.0

    # Per-class metrics on test
    all_preds = np.array(all_preds)
    per_class_acc = {}
    regime_names = {0: "bullish", 1: "bearish", 2: "ranging"}
    for cls in [0, 1, 2]:
        mask = y_test == cls
        if mask.sum() > 0:
            per_class_acc[regime_names[cls]] = (all_preds[mask] == cls).mean()
        else:
            per_class_acc[regime_names[cls]] = 0.0

    logger.info(
        f"Bias test: loss={test_loss:.4f} | acc={test_acc:.3f} | "
        f"bull_acc={per_class_acc['bullish']:.3f} | "
        f"bear_acc={per_class_acc['bearish']:.3f} | "
        f"range_acc={per_class_acc['ranging']:.3f}"
    )

    return {
        "best_valid_loss": best_valid_loss,
        "final_valid_acc": history["valid_acc"][-1],
        "test_loss": test_loss,
        "test_acc": test_acc,
        "per_class_acc": per_class_acc,
        "history": history,
        "epochs_run": epoch + 1,
        "n_train": len(X_train),
        "n_valid": len(X_valid),
        "n_test": len(X_test),
        "label_distribution": {
            "bullish": n_bull,
            "bearish": n_bear,
            "ranging": n_range,
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# CNN-specific Optuna param space (for module-6 style optimization)
# ═══════════════════════════════════════════════════════════════════════

CNN_PARAM_SPACE = {
    # CNN architecture
    "window_size":        {"type": "int",   "low": 30,  "high": 120, "step": 10},
    "dropout":            {"type": "float", "low": 0.1, "high": 0.5},
    "fc_units":           {"type": "int",   "low": 16,  "high": 64},

    # Inference
    "reversal_threshold": {"type": "float", "low": 0.5, "high": 0.9},

    # Shared (same ranges as ModelParams)
    "rr_ratio":           {"type": "float", "low": 1.0, "high": 4.0},
    "atr_stop_multiplier": {"type": "float", "low": 0.5, "high": 3.0},
    "atr_period":         {"type": "int",   "low": 7,   "high": 50},
    "max_position_pct":   {"type": "float", "low": 0.1, "high": 1.0},
    "rejection_zone_pct": {"type": "float", "low": 0.001, "high": 0.02},
}

BIAS_CNN_PARAM_SPACE = {
    # Architecture
    "window_size":        {"type": "int",   "low": 40,  "high": 120, "step": 10},
    "dropout":            {"type": "float", "low": 0.1, "high": 0.5},
    "fc_units":           {"type": "int",   "low": 16,  "high": 64},

    # Inference
    "confidence_threshold": {"type": "float", "low": 0.4, "high": 0.8},
    "stability_bars":     {"type": "int",   "low": 1,   "high": 5},

    # Labeling
    "adx_threshold":      {"type": "float", "low": 15.0, "high": 30.0},
    "sma_slope_period":   {"type": "int",   "low": 10,  "high": 40},
}
