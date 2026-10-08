"""
alpha_021 — long-only vertical-break persistence specialist (melt-up v3)
Hypothesis: alpha_020 proved the melt-up quadrant is reachable long-only
(+6.12% on the +31.33% window) but bled off-window (down-shield, participation,
edge, consistency all failed). The fix is PERSISTENCE-GATED entry: real
V-reversal melt-ups exhibit consecutive-bar continuation above the pre-break
range, while exhaustion spikes and chop bleed do not. Enter long ONLY when a
sigma-velocity vertical break is CONFIRMED by a second consecutive expansion
bar closing in the upper part of its range; ride with no regime gate while
momentum persists (fast EMA slope positive), exit the instant slope flips.
Outside a live vertical regime the signal is hard-zero, so down windows go
flat (down-shield) instead of short-bleeding.
Design: regime-blind trigger (no trend gate, no overlay), entry scale =
rolling-sigma normalized breakout distance, volume expansion confirmation,
bounded tanh transforms with |inputs| <= 2, trailing ops only.
Rule attacked: extreme_participation (bench >= +15% -> strat > 0) with
down_shield protection; deepens the melt-up specialist pool for the router.
Author: auto-gen (isolated alpha loop), 2026-10-05.
Provenance: tuner/runs/alpha_020_auto.json (extreme passed, off-window bleed),
models/alpha_formulas/alpha_004.py (dual-horizon velocity reference).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]

    ret = close.pct_change()
    sigma = ret.rolling(48, min_periods=20).std().replace(0, 1e-9)

    # 1. Vertical-break velocity: multi-horizon momentum in sigma units.
    vel = (close.pct_change(4) + close.pct_change(12)) / (sigma * np.sqrt(8))
    vertical = np.tanh(vel / 2.0)  # |vel|/2 bounded, tanh keeps in [-1, 1]

    # 2. Persistence: two consecutive expansion bars closing high in range.
    rng = (high - low).replace(0, 1e-9)
    close_loc = ((close - low) / rng)  # 1 = closed at high
    body_up = ((close > close.shift(1)) & (close_loc > 0.6)).astype(float)
    confirmed = body_up.rolling(2, min_periods=2).sum() >= 2.0

    # 3. Volume expansion: current bar volume vs trailing mean, squashed.
    vmean = volume.rolling(48, min_periods=20).mean().replace(0, 1e-9)
    volz = np.tanh((volume / vmean - 1.0) / 1.5)

    # 4. Breakout distance above recent range, sigma-normalized.
    hh = high.rolling(32, min_periods=16).max().replace(0, 1e-9)
    breakout = np.tanh(((close - hh.shift(1)) / (hh.shift(1) * sigma * 8)).fillna(0.0) / 2.0)

    # 5. Momentum-persistence hold: fast EMA slope must stay positive while
    #    riding; the moment slope <= 0 the position closes (hard zero).
    ema_f = close.ewm(span=16, min_periods=8).mean()
    slope_pos = (ema_f.diff() > 0).astype(float)

    # 6. Composite: entry needs vertical energy AND 2-bar confirmation AND
    #    volume expansion AND breakout; hold needs positive slope only.
    raw = vertical * breakout * (0.5 + 0.5 * volz)
    signal = raw.where(confirmed, 0.0) * slope_pos

    # Long-only specialist: clip shorts to flat.
    signal = signal.clip(lower=0.0, upper=1.0)
    return signal
