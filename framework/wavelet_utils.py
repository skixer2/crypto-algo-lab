"""
Wavelet Utilities — Phase 1 of Pattern Matching Pipeline

Provides:
  - DWT-based denoising for OHLCV candle data
  - Multi-scale decomposition (detail coefficients at each level)
  - Edge/break detection via detail-coefficient spikes
  - Feature extraction for CNN input (4 wavelet channels)

Dependencies: PyWavelets (pywt)

Integration points:
  - model.py:     use denoised close in _detect_swings()
  - model_cnn.py: append wavelet_detail_* to extract_features()
  - template_matcher.py (Phase 2): match on denoised close

Wavelet choice:
  - db6 (Daubechies 6) — good balance of smoothness and time-localization
  - sym8 (Symlet 8)   — alternative, similar properties
  - Decomposition level is auto-capped at pywt.dwt_max_level()
"""

import logging
from typing import List, Optional, Tuple, Dict

import numpy as np

try:
    import pywt
    _PYWT_AVAILABLE = True
except ImportError:
    _PYWT_AVAILABLE = False

logger = logging.getLogger(__name__)


def _require_pywt():
    if not _PYWT_AVAILABLE:
        raise ImportError("PyWavelets required. pip install PyWavelets")


# ═══════════════════════════════════════════════════════════════════════
# Core wavelet operations
# ═══════════════════════════════════════════════════════════════════════

def denoise(
    signal: np.ndarray,
    wavelet: str = "db6",
    level: Optional[int] = None,
    threshold_levels: Optional[List[int]] = None,
    mode: str = "symmetric",
) -> np.ndarray:
    """
    Denoise a 1D signal via wavelet thresholding.

    Algorithm: DWT → soft-threshold detail coefficients → IDWT

    Args:
        signal: 1D array (e.g. close prices)
        wavelet: wavelet name ('db6', 'sym8', 'haar', etc.)
        level: decomposition depth (auto if None)
        threshold_levels: which detail levels to threshold (default: [1] only)
        mode: boundary extension mode ('symmetric' recommended for financial)

    Returns:
        Denoised signal, same length as input.

    Why only threshold level 1 by default:
      Level 1 = highest frequency = mostly noise / microstructure.
      Levels 2+ = genuine market structure (swings, trends, reversals).
      Thresholding too many levels oversmooths and erases V/U shapes.
    """
    _require_pywt()

    if level is None:
        max_lvl = pywt.dwt_max_level(len(signal), wavelet)
        level = min(max_lvl - 1, 4) if max_lvl > 1 else max_lvl

    if threshold_levels is None:
        threshold_levels = [1]

    # ── Pad to avoid boundary artifacts ───────────────────────────
    pad = 2 ** (level + 1)
    padded = np.pad(signal.astype(np.float64), (pad, pad), mode="reflect")

    # ── Decompose ─────────────────────────────────────────────────
    coeffs = pywt.wavedec(padded, wavelet, mode=mode, level=level)
    # coeffs = [cA_n, cD_n, cD_{n-1}, ..., cD_1]

    # ── Threshold detail coefficients ─────────────────────────────
    sigma = np.median(np.abs(coeffs[-1] - np.median(coeffs[-1]))) / 0.6745  # MAD estimate
    threshold = sigma * np.sqrt(2 * np.log(len(padded)))

    for i, lvl in enumerate(range(level, 0, -1)):
        idx = i + 1  # coeffs[1] = cD_n, coeffs[level] = cD_1
        if lvl in threshold_levels:
            coeffs[idx] = pywt.threshold(coeffs[idx], threshold, mode="soft")

    # ── Reconstruct ───────────────────────────────────────────────
    denoised_padded = pywt.waverec(coeffs, wavelet, mode=mode)

    # ── Trim padding ──────────────────────────────────────────────
    return denoised_padded[pad:pad + len(signal)]


def decompose(
    signal: np.ndarray,
    wavelet: str = "db6",
    level: Optional[int] = None,
    mode: str = "symmetric",
) -> Tuple[np.ndarray, List[np.ndarray]]:
    """
    Decompose signal into approximation + detail coefficients.

    Args:
        signal: 1D array
        wavelet: wavelet name
        level: decomposition depth (auto if None)
        mode: boundary mode

    Returns:
        (approximation, [detail_level_1, detail_level_2, ..., detail_level_n])
        both aligned to original signal length via upsampling.
    """
    _require_pywt()

    if level is None:
        max_lvl = pywt.dwt_max_level(len(signal), wavelet)
        level = min(max_lvl - 1, 4) if max_lvl > 1 else max_lvl

    coeffs = pywt.wavedec(signal.astype(np.float64), wavelet, mode=mode, level=level)
    # coeffs = [cA_n, cD_n, cD_{n-1}, ..., cD_1]

    # ── Extract approximation (index 0) ───────────────────────────
    approx = _reconstruct_single(coeffs, 0, wavelet, mode, len(signal))

    # ── Extract each detail level (indices 1..level) ──────────────
    details = []
    for i in range(1, level + 1):
        detail = _reconstruct_single(coeffs, i, wavelet, mode, len(signal))
        details.append(detail)

    # details[0] = highest frequency (level 1), details[-1] = lowest
    return approx, details


def _reconstruct_single(
    coeffs: list,
    idx: int,
    wavelet: str,
    mode: str,
    target_len: int,
) -> np.ndarray:
    """Reconstruct a single coefficient band to original signal length."""
    rec_coeffs = [np.zeros_like(c) for c in coeffs]
    rec_coeffs[idx] = coeffs[idx]
    reconstructed = pywt.waverec(rec_coeffs, wavelet, mode=mode)
    # Trim/pad to target length
    if len(reconstructed) > target_len:
        reconstructed = reconstructed[:target_len]
    elif len(reconstructed) < target_len:
        reconstructed = np.pad(reconstructed, (0, target_len - len(reconstructed)),
                               mode="edge")
    return reconstructed


# ═══════════════════════════════════════════════════════════════════════
# Candle-aware helpers
# ═══════════════════════════════════════════════════════════════════════

def denoise_candles(
    candles: List[dict],
    wavelet: str = "db6",
    level: Optional[int] = None,
    threshold_levels: Optional[List[int]] = None,
    inplace: bool = False,
) -> List[dict]:
    """
    Denoise the 'close' price series of a candle list.

    Adds (or overwrites) a 'close_denoised' key to each candle dict.

    Args:
        candles: list of dicts with 'close' key
        wavelet: wavelet name
        level: decomposition depth
        threshold_levels: which detail levels to threshold
        inplace: if True, modify input list; if False, return new list

    Returns:
        List of candle dicts with 'close_denoised' key added.
    """
    if len(candles) < 4:
        return candles if inplace else list(candles)

    closes = np.array([c["close"] for c in candles], dtype=np.float64)
    denoised = denoise(closes, wavelet=wavelet, level=level,
                       threshold_levels=threshold_levels)

    if inplace:
        for i, val in enumerate(denoised):
            candles[i]["close_denoised"] = float(val)
        return candles
    else:
        result = []
        for i, c in enumerate(candles):
            d = dict(c)
            d["close_denoised"] = float(denoised[i])
            result.append(d)
        return result


def wavelet_features_for_candles(
    candles: List[dict],
    n_levels: int = 4,
    wavelet: str = "db6",
) -> Optional[np.ndarray]:
    """
    Extract wavelet detail coefficients as CNN input features.

    Args:
        candles: list of dicts (typically the last 60 candles from extract_features)
        n_levels: number of detail levels to extract
        wavelet: wavelet name

    Returns:
        (n_levels, len(candles)) numpy array, or None if too few candles.
        Each row is a detail-coefficient series at one frequency level.
        Can be stacked onto the CNN feature tensor: np.vstack([existing, wavelet])
    """
    if len(candles) < 2 ** n_levels:
        return None

    closes = np.array([c["close"] for c in candles], dtype=np.float64)
    # Auto-cap level to avoid boundary effects
    max_lvl = pywt.dwt_max_level(len(closes), wavelet)
    actual_level = min(n_levels, max_lvl - 1) if max_lvl > 1 else max_lvl
    _, details = decompose(closes, wavelet=wavelet, level=actual_level)

    # Pad with zeros if fewer levels than requested
    while len(details) < n_levels:
        details.append(np.zeros_like(details[-1]) if details else np.zeros(len(closes)))

    result = np.stack(details[:n_levels], axis=0).astype(np.float32)

    # Z-score normalize each level independently
    eps = 1e-10
    for i in range(result.shape[0]):
        mean, std = result[i].mean(), result[i].std()
        if std > eps:
            result[i] = (result[i] - mean) / std
        else:
            result[i] = 0.0

    return result


# ═══════════════════════════════════════════════════════════════════════
# Structural break detection (V-shape turning points)
# ═══════════════════════════════════════════════════════════════════════

def detect_breaks(
    signal: np.ndarray,
    wavelet: str = "db6",
    level: Optional[int] = None,
    sensitivity: float = 3.0,
) -> Tuple[np.ndarray, List[int]]:
    """
    Detect structural breaks (potential V-bottom/top turning points)
    via detail-coefficient spike detection.

    How it works:
      - A sharp V reversal creates a spike in level-1 detail coefficients
      - A gradual U bottom creates a rise in level-2/3 detail coefficients
      - Threshold: abs(detail) > sensitivity × MAD(detail)

    Args:
        signal: 1D price array
        wavelet: wavelet name
        level: decomposition depth
        sensitivity: multiplier for MAD threshold (higher = fewer detections)

    Returns:
        (break_score, break_indices)
        break_score: per-sample anomaly score (sum of |z-scored| details across levels)
        break_indices: indices where break_score crosses threshold
    """
    _, details = decompose(signal, wavelet=wavelet, level=level)

    # Combine detail levels into a single anomaly score
    anomaly = np.zeros(len(signal), dtype=np.float64)
    for det in details:
        if len(det) >= len(signal):
            det = det[:len(signal)]
        else:
            det = np.pad(det, (0, len(signal) - len(det)), mode="edge")
        # Z-score then abs → spike magnitude at this frequency
        mad = np.median(np.abs(det - np.median(det))) / 0.6745 + 1e-10
        anomaly += np.abs((det - np.median(det)) / mad)

    # Threshold
    anomaly_mad = np.median(np.abs(anomaly - np.median(anomaly))) / 0.6745 + 1e-10
    threshold = sensitivity * anomaly_mad
    break_indices = np.where(anomaly > threshold)[0].tolist()

    return anomaly, break_indices


def classify_break_type(
    signal: np.ndarray,
    break_idx: int,
    wavelet: str = "db6",
    level: int = 4,
    window: int = 10,
) -> str:
    """
    Classify a detected break as 'V' (sharp) or 'U' (gradual).

    Uses detail coefficient energy ratio:
      - V-bottom: high energy in level 1-2 (sharp edges)
      - U-bottom: high energy in level 3-4 (smooth curvature)

    Args:
        signal: price array
        break_idx: index of the break point
        wavelet: wavelet name
        level: decomposition depth
        window: candles around the break to analyze

    Returns:
        'V' or 'U'
    """
    start = max(0, break_idx - window)
    end = min(len(signal), break_idx + window)
    segment = signal[start:end]

    _, details = decompose(segment, wavelet=wavelet, level=min(level, 4))

    # Energy in high-frequency vs low-frequency details
    high_energy = sum(np.sum(np.abs(d)) for d in details[:2] if len(d) > 0)
    low_energy = sum(np.sum(np.abs(d)) for d in details[2:] if len(d) > 0)
    total = high_energy + low_energy + 1e-10

    if high_energy / total > 0.55:
        return "V"
    return "U"


# ═══════════════════════════════════════════════════════════════════════
# Integration helpers
# ═══════════════════════════════════════════════════════════════════════

def get_denoised_close(candles: List[dict]) -> Optional[np.ndarray]:
    """
    Convenience: extract denoised close from candles if available,
    otherwise denoise on the fly and return.
    """
    if not candles:
        return None
    if "close_denoised" in candles[0]:
        return np.array([c["close_denoised"] for c in candles], dtype=np.float64)
    closes = np.array([c["close"] for c in candles], dtype=np.float64)
    if len(closes) < 4:
        return closes
    return denoise(closes)


def plot_wavelet_debug(
    candles: List[dict],
    output_path: str = "wavelet_debug.png",
    wavelet: str = "db6",
):
    """
    Debug plot: raw close vs denoised close + detail coefficients.
    Saves to output_path. Requires matplotlib.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not available — skipping debug plot")
        return

    closes = np.array([c["close"] for c in candles], dtype=np.float64)
    denoised_close = denoise(closes, wavelet=wavelet)
    approx, details = decompose(closes, wavelet=wavelet)

    n_rows = 2 + len(details)
    fig, axes = plt.subplots(n_rows, 1, figsize=(14, 2 * n_rows), sharex=True)

    # Top: raw vs denoised
    axes[0].plot(closes, alpha=0.5, label="Raw close", color="gray", linewidth=0.8)
    axes[0].plot(denoised_close, label="Denoised", color="steelblue", linewidth=1.5)
    axes[0].set_title("Raw vs Denoised Close")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)

    # Approximation (trend)
    axes[1].plot(approx, color="darkgreen", linewidth=1.2)
    axes[1].set_title("Approximation (Trend)")
    axes[1].grid(True, alpha=0.3)

    # Detail levels
    for i, det in enumerate(details):
        ax = axes[2 + i]
        ax.fill_between(range(len(det)), det, 0, alpha=0.5, color=f"C{i}")
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_title(f"Detail Level {i+1} ({'highest' if i==0 else 'lowest'} freq)")
        ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Wavelet debug plot saved to {output_path}")
