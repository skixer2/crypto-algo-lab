"""
alpha_030 — trend-riding specialist v4: fast-break OR ride-memory (max-composite)
Hypothesis: alpha_029 failed extreme participation (+57% bench window had 0
entries) because its signal was a pure EWMA of upper-half closes — on the
FIRST days of a melt-up the memory hadn't accumulated enough to cross the
tuned entry threshold, and by the time it did the window was over. Same
story in the +14% Oct-2023 window (strat 1.4 vs required 8.5).
Fix: signal = max(fresh_break, ride) where fresh_break is an un-gated,
immediately-saturating tanh of a 24h-high breakout (fires at full strength
on bar 1 of a new trend), and ride is the alpha_029-style persistent memory
for holding through pullbacks. Composite via max, not average, so the fast
leg is never diluted by the slow leg's warm-up.
Down-shield: slow-slope softener (200-bar EWM slope of close, normalized)
scales the whole signal to ~0 in sustained downtrends — graded, not a hard
gate, preserving the proven down-shield behavior of 029.
Scale discipline: |tanh inputs| <= 2; divisions guarded .replace(0, 1e-9);
trailing ops only (rolling/ewm, shift(1) exclusions).
Rule attacked: EXTREME (bench>=15% -> strat>0), UPTREND PARTICIPATION (60%),
ADAPTIVE ACTIVITY (>=8 entries).
Author: auto-gen (isolated alpha loop), 2026-10-07. Priority 1+2 attack.
Provenance: alpha_029 (extreme 0 entries, memory warm-up too slow);
alpha_026 (threshold never crossed); alpha_025 (chandelier sound).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close = df["close"]

    # --- Leg A: fresh breakout, saturates on bar 1 of a new 24h high ---
    hh24 = close.rolling(96, min_periods=40).max().shift(1)
    rng24 = (hh24 - close.rolling(96, min_periods=40).min().shift(1)).replace(0, 1e-9)
    pos24 = (close - close.rolling(96, min_periods=40).min().shift(1)) / rng24
    fresh_break = np.tanh((pos24 - 0.55) * 4.0).clip(lower=0.0)

    # --- Leg B: persistent ride memory (alpha_029 core) ---
    hh = close.rolling(96, min_periods=40).max().shift(1)
    ll = close.rolling(192, min_periods=80).min().shift(1)
    chan = (hh - ll).replace(0, 1e-9)
    pos = (close - ll) / chan
    breakout = np.tanh((pos - 0.5) * 2.0).clip(lower=0.0)
    fast_mem = breakout.ewm(span=96, min_periods=10).mean()
    slow_mem = breakout.ewm(span=384, min_periods=30).mean()
    ride = (0.6 * fast_mem + 0.4 * slow_mem).clip(upper=1.0)

    # --- Composite: max so fast leg never diluted during slow warm-up ---
    core = np.maximum(fresh_break, ride)

    # --- Graded down-shield: fade in sustained downtrends ---
    slope = (close.ewm(span=200, min_periods=50).mean().diff(48)
             / close.ewm(span=200, min_periods=50).mean().shift(48).replace(0, 1e-9))
    shield = np.tanh(slope.replace([np.inf, -np.inf], 0).fillna(0) * 20.0)
    shield = ((shield + 1.0) / 2.0).clip(lower=0.05, upper=1.0)

    return (core * shield).fillna(0.0)
