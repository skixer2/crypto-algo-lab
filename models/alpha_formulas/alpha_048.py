"""
alpha_048 — TURTLE LATCH v2: binary pinned long while above trailing structural level
Hypothesis (P1a, JP 2026-10-11): the empty pool seat is BULL SURFING. Failures
(026, 047, blender up-capture 0.06) came from graded EWM memory diluting below
tuner thresholds in melt-up months. Fix: CRISP binary latch — signal is pinned
at +1.0 while close > trailing structural level (rolling max of high, shifted
1 bar, N in the 2..5-day range), exactly 0.0 below. A short tanh ramp of
(close - trail)/ATR near the boundary smooths ENTRY only; HOLDING is binary.
Wide channel (480 bars) keeps the latch on through minor pullbacks inside a
melt-up; a shorter confirmation channel re-arms fast after deep breaks.
Charter rule attacked: extreme_participation (bench >= +15% => strat > 0) and
uptrend_participation (0 < bench < 15% => strat >= 0.6*bench). Diagnostic
target: segment up-capture >= 0.5 in V-shaped windows.
What NOT to do (alpha_026 post-mortem): no graded memory that decays below
thresholds; no multi-factor dilution of the bull signal.
Author: auto-gen (isolated alpha loop), 2026-10-11. P1a bull seat.
Provenance: tuner/runs/alpha_047_auto.json (gates: extreme & uptrend failed),
blender_v1b (up-capture 0.06 lesson), alpha_026 (graded-memory death).
Inputs: OHLCV. Trailing ops only; bounded transforms; guarded divisions.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    eps = 1e-9

    # ATR (15m bars), trailing, guarded
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    atr = tr.rolling(96, min_periods=30).mean().replace(0, eps)

    # --- Trailing structural level (Turtle): rolling max of high, shifted 1
    # Wide structural channel (5 days of 15m bars = 480) holds through pullbacks
    trail_wide = high.rolling(480, min_periods=120).max().shift(1)
    # Faster structural channel (2 days = 192) for re-arm after deep breaks
    trail_fast = high.rolling(192, min_periods=60).max().shift(1)

    # --- Entry ramp: proximity to the wide level, ATR-normalized, bounded ---
    prox = (close - trail_wide) / atr.replace(0, eps)
    entry_ramp = np.tanh(prox / 1.0).clip(0, 1).fillna(0.0)  # smooth near boundary

    # --- Binary HOLDING latch (crisp): above EITHER structural level --------
    above_wide = (close > trail_wide).astype(float)
    above_fast = (close > trail_fast).astype(float)

    # Latch proxy, trailing-only: fraction of last 4 bars above the level.
    # >= any single bar above keeps the pinned seat; equals binary in practice
    # because the tuner entry threshold (<=0.3) and exit threshold (<=0.1)
    # sit far below the pinned level.
    hold_wide = above_wide.rolling(4, min_periods=1).max()
    hold_fast = above_fast.rolling(4, min_periods=1).max()
    latch = np.maximum(hold_wide, hold_fast)

    # --- Volume confirmation of breakouts (legal & encouraged) --------------
    vol_rel = volume / volume.rolling(96, min_periods=30).mean().replace(0, eps)
    vol_conf = 0.5 + 0.5 * np.tanh((vol_rel - 1.0) / 1.5).fillna(0.0)

    # --- Composite: pinned long. Ramp only modulates ENTRY conviction; -----
    # once latched the signal is pinned at 1.0 regardless of pullback depth.
    sig = np.maximum(entry_ramp * vol_conf, latch)

    # Long-only signal, bounded in [0, 1]
    return sig.clip(0, 1).fillna(0.0)
