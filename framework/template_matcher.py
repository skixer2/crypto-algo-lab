"""
Template Matcher — Phase 2 of Pattern Matching Pipeline

Slides parameterized V-bottom, U-bottom, V-top, U-top templates across
wavelet-denoised price windows using Pearson correlation.

Two modes:
  1. Full-window (feature extraction / backtesting):
     Symmetric matching — uses candles before AND after each position.
  2. Live (forward-only):
     Only uses candles up to the current position.

Output: one score ∈ [0, 1] per candle per template type.

Integration:
  - CNNModel.predict(): scores > threshold provide an alternative entry path
  - extract_features(): scores added as CNN input channels (11-14)
  - Label generation for Phase 3 training

Dependencies: wavelet_utils.py (Phase 1) for denoised close.
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Template shapes (synthetic, zero-mean)
# ═══════════════════════════════════════════════════════════════════════

def _v_shape(width: int, depth: float = 1.0, symmetry: float = 1.0) -> np.ndarray:
    """
    V-bottom template: linear down → trough → linear up.

    Args:
        width: total number of candles
        depth: amplitude (arbitrary — Pearson correlation is scale-invariant)
        symmetry: ratio left_leg / right_leg. 1.0 = symmetric V.

    Returns:
        Array of shape (width,) with zero mean.
    """
    ratio = symmetry / (1.0 + symmetry)
    left_len = max(1, int(width * ratio))
    right_len = width - left_len

    left = np.linspace(0, -depth, left_len, endpoint=False)
    right = np.linspace(-depth, 0, right_len if right_len > 0 else 1)

    result = np.concatenate([left, right])
    # Zero-mean (Pearson uses centered data)
    result = result - result.mean()
    return result.astype(np.float64)


def _u_shape(width: int, depth: float = 1.0, symmetry: float = 1.0,
             bottom_ratio: float = 0.25) -> np.ndarray:
    """
    U-bottom template: linear down → flat/curved bottom → linear up.

    Args:
        width: total number of candles
        depth: amplitude
        symmetry: ratio left_leg / right_leg
        bottom_ratio: fraction of width spent near the trough

    Returns:
        Array of shape (width,) with zero mean.
    """
    bottom_len = max(1, int(width * bottom_ratio))
    remaining = width - bottom_len
    if remaining < 2:
        remaining = 2
        bottom_len = width - 2

    ratio = symmetry / (1.0 + symmetry)
    left_len = max(1, int(remaining * ratio))
    right_len = remaining - left_len
    if right_len < 1:
        right_len = 1
        left_len = remaining - 1

    left = np.linspace(0, -depth, left_len, endpoint=False)
    # Smooth bottom: cosine dip
    bottom = -depth + 0.5 * depth * (1.0 - np.cos(np.linspace(0, np.pi, bottom_len)))
    # Actually keep it flat for simplicity — cosine is Phase 3's job
    bottom = np.full(bottom_len, -depth, dtype=np.float64)
    right = np.linspace(-depth, 0, right_len)

    result = np.concatenate([left, bottom, right])
    result = result - result.mean()
    return result.astype(np.float64)


# ═══════════════════════════════════════════════════════════════════════
# Template Matcher
# ═══════════════════════════════════════════════════════════════════════

class TemplateMatcher:
    """
    Parametric V/U shape detector using Pearson correlation.

    Slides 4 template types (V-bottom, U-bottom, V-top, U-top)
    at multiple widths across wavelet-denoised close prices.
    Outputs a continuous score ∈ [0, 1] per candle.

    Args:
        widths: list of template widths in candles. Multi-scale detection.
        symmetries: list of symmetry ratios (left/right balance) to try.
        bottom_ratios: list of bottom-flatness ratios for U shapes.
        signal_source: which price series to match against:
            "denoised" → wavelet-denoised close (Phase 1, default)
            "raw"      → raw close
            "approx3"  → wavelet approximation level 3
    """

    def __init__(
        self,
        widths: Tuple[int, ...] = (5, 10, 15, 20),
        symmetries: Tuple[float, ...] = (0.8, 1.0, 1.25),
        bottom_ratios: Tuple[float, ...] = (0.2, 0.35),
        signal_source: str = "denoised",
    ):
        self.widths = list(widths)
        self.symmetries = list(symmetries)
        self.bottom_ratios = list(bottom_ratios)
        self.signal_source = signal_source

        # Pre-compute template library
        self._v_bottom_templates: Dict[Tuple[int, float], np.ndarray] = {}
        self._u_bottom_templates: Dict[Tuple[int, float, float], np.ndarray] = {}

        for w in widths:
            for sym in symmetries:
                self._v_bottom_templates[(w, sym)] = _v_shape(w, 1.0, sym)
                for br in bottom_ratios:
                    self._u_bottom_templates[(w, sym, br)] = _u_shape(w, 1.0, sym, br)

        logger.info(
            f"TemplateMatcher: {len(widths)} widths × {len(symmetries)} symmetries "
            f"× {len(bottom_ratios)} U-ratios = "
            f"{len(self._v_bottom_templates)} V + {len(self._u_bottom_templates)} U templates"
        )

    # ── Signal extraction ────────────────────────────────────────────

    def _get_signal(self, candles: List[dict]) -> Optional[np.ndarray]:
        """Extract the appropriate price series for matching."""
        if not candles:
            return None

        if self.signal_source == "raw":
            return np.array([c["close"] for c in candles], dtype=np.float64)

        # Denoised (Phase 1)
        if "close_denoised" not in candles[0]:
            # Denoise on the fly
            try:
                from .wavelet_utils import denoise
                closes = np.array([c["close"] for c in candles], dtype=np.float64)
                return denoise(closes)
            except ImportError:
                logger.warning("PyWavelets not available — falling back to raw close")
                return np.array([c["close"] for c in candles], dtype=np.float64)

        denoised = np.array([c["close_denoised"] for c in candles], dtype=np.float64)

        if self.signal_source == "approx3":
            try:
                from .wavelet_utils import decompose
                _, details = decompose(denoised, level=3)
                if len(details) >= 3:
                    return details[2]  # level-3 detail
            except ImportError:
                pass

        return denoised

    # ── Full-window matching (for feature extraction / backtesting) ──

    def match_all(
        self,
        candles: List[dict],
    ) -> Dict[str, np.ndarray]:
        """
        Full-window symmetric matching.

        For each candle position, slides templates that include candles
        both before AND after that position. This uses future information
        within the window — suitable for CNN feature extraction and
        historical labeling, NOT for live forward-only prediction.

        Args:
            candles: list of dicts with at least 'close' key

        Returns:
            Dict with keys "v_bottom", "u_bottom", "v_top", "u_top".
            Each value is a float array of shape (len(candles),)
            with scores in [0, 1]. NaN positions where matching is
            not possible (edges) are set to 0.
        """
        signal = self._get_signal(candles)
        if signal is None:
            return self._empty_result(len(candles))

        n = len(signal)
        v_bottom = np.full(n, np.nan, dtype=np.float64)
        u_bottom = np.full(n, np.nan, dtype=np.float64)

        max_width = max(self.widths)

        for i in range(n):
            best_vb = 0.0
            best_ub = 0.0

            for w in self.widths:
                # For V-bottom: trough is at position i
                # Need w/2 candles before and w/2 after
                half = w // 2
                start = i - half
                end = i + half + (w % 2)

                if start < 0 or end > n:
                    continue

                segment = signal[start:end]
                if len(segment) < w:
                    continue

                # Z-score normalize the segment (Pearson: scale-invariant)
                seg_std = np.std(segment)
                if seg_std < 1e-10:
                    continue  # flat segment, no pattern

                # V-bottom matching
                for (tw, tsym), template in self._v_bottom_templates.items():
                    if tw != w:
                        continue
                    # Need to match template length to segment length
                    if len(template) != len(segment):
                        # Resample template to segment length
                        t_resampled = np.interp(
                            np.linspace(0, len(template) - 1, len(segment)),
                            np.arange(len(template)),
                            template,
                        )
                    else:
                        t_resampled = template

                    corr = np.corrcoef(t_resampled, segment)[0, 1]
                    if np.isnan(corr):
                        continue
                    corr = max(0.0, corr)  # only positive correlations
                    if corr > best_vb:
                        best_vb = corr

                # U-bottom matching
                for (tw, tsym, tbr), template in self._u_bottom_templates.items():
                    if tw != w:
                        continue
                    if len(template) != len(segment):
                        t_resampled = np.interp(
                            np.linspace(0, len(template) - 1, len(segment)),
                            np.arange(len(template)),
                            template,
                        )
                    else:
                        t_resampled = template

                    corr = np.corrcoef(t_resampled, segment)[0, 1]
                    if np.isnan(corr):
                        continue
                    corr = max(0.0, corr)
                    if corr > best_ub:
                        best_ub = corr

            v_bottom[i] = best_vb
            u_bottom[i] = best_ub

        # V-top = inverted V-bottom (same templates but negative corr becomes positive)
        # U-top = inverted U-bottom
        v_top = np.full(n, np.nan, dtype=np.float64)
        u_top = np.full(n, np.nan, dtype=np.float64)

        for i in range(n):
            best_vt = 0.0
            best_ut = 0.0

            for w in self.widths:
                half = w // 2
                start = i - half
                end = i + half + (w % 2)

                if start < 0 or end > n:
                    continue

                segment = signal[start:end]
                seg_std = np.std(segment)
                if seg_std < 1e-10:
                    continue

                # V-top: negative correlation with V-bottom template
                for (tw, tsym), template in self._v_bottom_templates.items():
                    if tw != w:
                        continue
                    if len(template) != len(segment):
                        t_resampled = np.interp(
                            np.linspace(0, len(template) - 1, len(segment)),
                            np.arange(len(template)),
                            template,
                        )
                    else:
                        t_resampled = template

                    corr = np.corrcoef(t_resampled, segment)[0, 1]
                    if np.isnan(corr):
                        continue
                    # V-top: negative correlation → inverted pattern
                    corr = max(0.0, -corr)
                    if corr > best_vt:
                        best_vt = corr

                # U-top
                for (tw, tsym, tbr), template in self._u_bottom_templates.items():
                    if tw != w:
                        continue
                    if len(template) != len(segment):
                        t_resampled = np.interp(
                            np.linspace(0, len(template) - 1, len(segment)),
                            np.arange(len(template)),
                            template,
                        )
                    else:
                        t_resampled = template

                    corr = np.corrcoef(t_resampled, segment)[0, 1]
                    if np.isnan(corr):
                        continue
                    corr = max(0.0, -corr)
                    if corr > best_ut:
                        best_ut = corr

            v_top[i] = best_vt
            u_top[i] = best_ut

        # Fill NaN edges with 0
        for arr in [v_bottom, u_bottom, v_top, u_top]:
            np.nan_to_num(arr, nan=0.0, copy=False)

        return {
            "v_bottom": v_bottom,
            "u_bottom": u_bottom,
            "v_top": v_top,
            "u_top": u_top,
        }

    # ── Forward-only matching (for live trading) ─────────────────────

    def match_live(
        self,
        candles: List[dict],
    ) -> Dict[str, float]:
        """
        Forward-only matching for the most recent candle.

        Only uses candles up to and including the current position.
        Looks for pattern completion at the current candle.

        Detection strategy:
          V-bottom: checks if the last `w` candles formed a V shape
          (down then up, trough somewhere in the middle-to-recent).

        Args:
            candles: list of dicts

        Returns:
            Dict with scores {"v_bottom", "u_bottom", "v_top", "u_top"}
            for the latest candle only.
        """
        signal = self._get_signal(candles)
        if signal is None or len(signal) < min(self.widths):
            return {"v_bottom": 0.0, "u_bottom": 0.0, "v_top": 0.0, "u_top": 0.0}

        n = len(signal)
        best_vb, best_ub, best_vt, best_ut = 0.0, 0.0, 0.0, 0.0

        for w in self.widths:
            if n < w:
                continue

            segment = signal[-w:]  # last w candles
            seg_std = np.std(segment)
            if seg_std < 1e-10:
                continue

            # V-bottom: template trough aligned with end of segment
            for (tw, tsym), template in self._v_bottom_templates.items():
                if tw != w:
                    continue
                if len(template) != len(segment):
                    t_resampled = np.interp(
                        np.linspace(0, len(template) - 1, len(segment)),
                        np.arange(len(template)),
                        template,
                    )
                else:
                    t_resampled = template

                corr = np.corrcoef(t_resampled, segment)[0, 1]
                if np.isnan(corr):
                    continue
                best_vb = max(best_vb, max(0.0, corr))
                best_vt = max(best_vt, max(0.0, -corr))

            # U-bottom
            for (tw, tsym, tbr), template in self._u_bottom_templates.items():
                if tw != w:
                    continue
                if len(template) != len(segment):
                    t_resampled = np.interp(
                        np.linspace(0, len(template) - 1, len(segment)),
                        np.arange(len(template)),
                        template,
                    )
                else:
                    t_resampled = template

                corr = np.corrcoef(t_resampled, segment)[0, 1]
                if np.isnan(corr):
                    continue
                best_ub = max(best_ub, max(0.0, corr))
                best_ut = max(best_ut, max(0.0, -corr))

        return {
            "v_bottom": float(best_vb),
            "u_bottom": float(best_ub),
            "v_top": float(best_vt),
            "u_top": float(best_ut),
        }

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _empty_result(n: int) -> Dict[str, np.ndarray]:
        zeros = np.zeros(n, dtype=np.float64)
        return {"v_bottom": zeros, "u_bottom": zeros, "v_top": zeros, "u_top": zeros}

    def feature_scores(
        self,
        candles: List[dict],
        window_size: int = 60,
    ) -> Optional[np.ndarray]:
        """
        Convenience: return (4, window_size) array of template scores
        for the last window_size candles, ready to stack into CNN features.

        Returns None if not enough candles.
        """
        if len(candles) < window_size:
            return None

        window = candles[-window_size:]
        all_scores = self.match_all(window)

        return np.stack([
            all_scores["v_bottom"],
            all_scores["u_bottom"],
            all_scores["v_top"],
            all_scores["u_top"],
        ], axis=0).astype(np.float32)


# ═══════════════════════════════════════════════════════════════════════
# Auto-labeling (for Phase 3 training data)
# ═══════════════════════════════════════════════════════════════════════

def label_from_templates(
    candles: List[dict],
    matcher: Optional[TemplateMatcher] = None,
    threshold_high: float = 0.85,
    threshold_low: float = 0.30,
    direction: str = "long",  # "long" or "short"
) -> Tuple[np.ndarray, np.ndarray, int]:
    """
    Auto-label candles using template matching scores.

    Args:
        candles: list of candle dicts
        matcher: TemplateMatcher instance (created if None)
        threshold_high: scores above this → positive label (1)
        threshold_low: scores below this → negative label (0)
        direction: "long" → V/U-bottom; "short" → V/U-top

    Returns:
        (labels, confidence_mask, n_ambiguous)
        labels: 1.0 (positive), 0.0 (negative), NaN (ambiguous)
        confidence_mask: True where label is confident (not ambiguous)
        n_ambiguous: count of ambiguous positions
    """
    if matcher is None:
        matcher = TemplateMatcher()

    scores = matcher.match_all(candles)

    if direction == "long":
        combined = np.maximum(scores["v_bottom"], scores["u_bottom"])
    else:
        combined = np.maximum(scores["v_top"], scores["u_top"])

    n = len(combined)
    labels = np.full(n, np.nan, dtype=np.float64)
    confidence_mask = np.zeros(n, dtype=bool)

    high_mask = combined >= threshold_high
    low_mask = combined <= threshold_low
    ambiguous_mask = ~(high_mask | low_mask)

    labels[high_mask] = 1.0
    labels[low_mask] = 0.0
    confidence_mask[high_mask | low_mask] = True
    n_ambiguous = ambiguous_mask.sum()

    logger.info(
        f"Auto-labels: {high_mask.sum()} positive, {low_mask.sum()} negative, "
        f"{n_ambiguous} ambiguous ({n_ambiguous/n*100:.1f}%)"
    )

    return labels, confidence_mask, int(n_ambiguous)
