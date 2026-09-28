"""WQ Alpha Miner — bridges WorldQuant-style vectorized alpha formulas to the
framework's incremental model contract (Module 3).

Design notes (engine protocol, verified against framework/simulation.py):
  - predict() is ONLY called when FLAT: this is an entry-signal protocol.
    Exits happen exclusively via stop-loss/take-profit (close-price checks).
    Therefore the alpha's exit intelligence lives in ATR-based SL/TP placement.
  - Entries are REJECTED unless indicators carry stop_loss > 0 and take_profit > 0.
  - The engine calls model.get_indicators() on EVERY tick — mandatory.

The formula file contract lives in models/alpha_formulas/README.md:
    calculate_math_signal(df: pd.DataFrame) -> pd.Series   # values in [-1, 1]
    df columns: open, high, low, close, volume (UTC DatetimeIndex). Causal ops only.
"""
from __future__ import annotations

import hashlib
import importlib.util
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.dirname(os.path.abspath(__file__))
FORMULA_DIR = os.path.join(MODELS_DIR, "alpha_formulas")

Action = str  # "long" | "short" | "flat"


@dataclass
class WQAlphaParams:
    """All tunables — the optimizer (Module 6) tunes exactly these."""
    formula_path: str = ""            # absolute, or relative to models/alpha_formulas/
    long_threshold: float = 0.55      # signal >=  this -> long entry
    short_threshold: float = 0.55     # signal <= -this -> short entry
    signal_smoothing: int = 5         # EMA span on raw signal (1 = off)
    atr_period: int = 14
    atr_stop_mult: float = 2.0        # SL distance in ATRs
    atr_take_mult: float = 3.0        # TP distance in ATRs
    max_position_pct: float = 1.0
    warmup_candles: int = 60          # min exec candles before entries are allowed
    buffer_size: int = 1500           # per-TF candle buffer cap (memory bound)
    use_bias_filter: bool = True      # EMA fast/slow on first bias TF gates direction
    bias_fast: int = 50
    bias_slow: int = 200


class WQAlphaMinerModel:
    """Incremental wrapper around a vectorized alpha formula.

    Deterministic: state = per-TF candle buffers only; a fresh instance
    reproduces any backtest exactly. No lookahead: signals at t are computed
    from candles with timestamp <= t.
    """

    def __init__(
        self,
        params: WQAlphaParams,
        execution_tf: str = "15m",
        bias_tfs: Optional[List[str]] = None,
    ):
        self.p = params
        self.execution_tf = execution_tf
        self.bias_tfs = list(bias_tfs or [])

        path = params.formula_path
        if not os.path.isabs(path):
            path = os.path.join(FORMULA_DIR, path)
        if not os.path.isfile(path) and os.path.isfile(path + ".py"):
            path += ".py"
        if not os.path.isfile(path):
            raise FileNotFoundError(f"alpha formula not found: {path}")
        self.formula_path = path
        self.formula_name = os.path.basename(path)
        with open(path, "rb") as f:
            self.formula_hash = hashlib.sha256(f.read()).hexdigest()[:12]

        spec = importlib.util.spec_from_file_location(
            f"wqalpha_{self.formula_hash}", path
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "calculate_math_signal"):
            raise AttributeError(
                f"{self.formula_name}: missing calculate_math_signal(df)"
            )
        self._mod = mod

        self._buffers: Dict[str, List[dict]] = {tf: [] for tf in [execution_tf] + self.bias_tfs}
        self._last_indicators: Dict = {}
        self._formula_error_logged = False

    # ── Module 3 contract ──────────────────────────────────────────

    def update(self, candle_row, tf: str) -> None:
        buf = self._buffers.setdefault(tf, [])
        buf.append({
            "timestamp": candle_row.name,
            "open": float(candle_row["open"]),
            "high": float(candle_row["high"]),
            "low": float(candle_row["low"]),
            "close": float(candle_row["close"]),
            "volume": float(candle_row["volume"]),
        })
        if len(buf) > self.p.buffer_size:
            del buf[: len(buf) - self.p.buffer_size]

    def predict(self, allow_shorts: bool = True) -> Tuple[Action, float, Dict]:
        buf = self._buffers[self.execution_tf]
        if len(buf) < self.p.warmup_candles:
            return "flat", 0.0, self._last_indicators

        df = pd.DataFrame(buf).set_index("timestamp")
        close = float(df["close"].iloc[-1])

        sig = self._compute_signal(df)
        if sig is None:
            return "flat", 0.0, self._last_indicators

        atr = self._compute_atr(df)
        bias_bull = self._bias_trend()  # None if no filter / not enough data

        action: Action = "flat"
        if sig >= self.p.long_threshold and (bias_bull is None or bias_bull):
            action = "long"
        elif (
            allow_shorts
            and sig <= -self.p.short_threshold
            and (bias_bull is None or not bias_bull)
        ):
            action = "short"

        indicators: Dict = {
            "entry_price": close,
            "signal": round(sig, 4),
            "atr": round(atr, 4),
            "bias_bull": bias_bull,
            "formula": self.formula_name,
        }
        if action == "long":
            indicators["stop_loss"] = max(close - self.p.atr_stop_mult * atr, 1e-9)
            indicators["take_profit"] = close + self.p.atr_take_mult * atr
        elif action == "short":
            indicators["stop_loss"] = close + self.p.atr_stop_mult * atr
            indicators["take_profit"] = max(close - self.p.atr_take_mult * atr, 1e-9)

        self._last_indicators = indicators
        return action, self.p.max_position_pct, indicators

    def get_indicators(self) -> Dict:
        return self._last_indicators

    # ── internals ──────────────────────────────────────────────────

    def _compute_signal(self, df: pd.DataFrame) -> Optional[float]:
        try:
            s = self._mod.calculate_math_signal(df)
            s = pd.Series(s).astype(float)
            if self.p.signal_smoothing and self.p.signal_smoothing > 1:
                s = s.ewm(span=int(self.p.signal_smoothing), adjust=False).mean()
            s = s.fillna(0.0).clip(-1.0, 1.0)
            if len(s) == 0:
                return None
            return float(s.iloc[-1])
        except Exception as e:
            if not self._formula_error_logged:
                logger.error(f"formula {self.formula_name} raised: {e}")
                self._formula_error_logged = True
            return None

    def _compute_atr(self, df: pd.DataFrame) -> float:
        h, l, c = df["high"], df["low"], df["close"]
        prev_c = c.shift(1)
        tr = pd.concat(
            [h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1
        ).max(axis=1)
        atr = tr.ewm(alpha=1.0 / max(int(self.p.atr_period), 1), adjust=False).mean()
        val = float(atr.iloc[-1])
        return val if val > 0 else float(c.iloc[-1]) * 0.01  # 1% fallback

    def _bias_trend(self) -> Optional[bool]:
        """True=bullish, False=bearish, None=filter off/insufficient data."""
        if not self.p.use_bias_filter or not self.bias_tfs:
            return None
        buf = self._buffers.get(self.bias_tfs[0])
        if not buf or len(buf) < self.p.bias_slow:
            return None
        df = pd.DataFrame(buf).set_index("timestamp")
        fast = df["close"].ewm(span=self.p.bias_fast, adjust=False).mean().iloc[-1]
        slow = df["close"].ewm(span=self.p.bias_slow, adjust=False).mean().iloc[-1]
        return bool(fast > slow)
