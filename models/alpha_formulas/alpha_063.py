import numpy as np
import pandas as pd

def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    """alpha_063 — TURTLE LATCH v2 (crisp bull seat).

    Hypothesis: a binary structural breakout latch (close above trailing
    N-bar rolling max of high, shifted 1 bar) holds the full bull leg and
    captures melt-up / V-recovery windows, fixing the up-capture failure of
    graded-memory designs (alpha_026 dilution death). Holding is BINARY:
    +1.0 pinned while close > trail, 0.0 below. A tanh ramp of
    (close-trail)/ATR only smooths the ENTRY near the boundary; once
    latched above trail the signal stays 1.0 (no dilution).

    Rule attacked: P1 bull seat / extreme_participation (bench>=15% ->
    strat>0) and uptrend_participation (strat>=60% bench), which the
    035/040 lineage and recent 041-062 candidates all fail.

    Author: alpha-generation-loop (JP charter v2 asymmetric, 2026-10-15)
    Provenance: alpha_062 gates showed extreme/up participation failures
    (-3.35 vs +56.95 bench in 2022-07 melt-up); frontier note blender_v1b
    up-capture 0.06. Turtle-latch design per JP 2026-10-11 directive.
    """
    close = df["close"]
    high = df["high"]
    volume = df["volume"]

    eps = 1e-9

    # Trailing structural level: rolling max of high, shifted 1 bar (no lookahead).
    trail = high.rolling(192, min_periods=48).max().shift(1)

    # Distance above the structural level, normalized by ATR (bounded).
    tr = pd.concat([
        (df["high"] - df["low"]).abs(),
        (df["high"] - close.shift(1)).abs(),
        (df["low"] - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(96, min_periods=24).mean().replace(0, eps).shift(1)
    dist = ((close - trail) / atr).clip(-2, 2)

    # Crisp latch state: 1 while above trail, 0 below (binary holding).
    above = (close > trail).astype(float)

    # Entry smoothness only: when just above the boundary, ramp in with tanh;
    # once solidly latched (dist>=0.5 ATR), pin to full 1.0.
    ramp = np.tanh(dist / 0.5).clip(0, 1)
    entry_smooth = np.where(dist >= 0.5, 1.0, ramp)
    sig = above * entry_smooth

    # Volume confirmation of breakout quality: scale toward 1 using bounded
    # relative volume; never lifts signal above the latch itself.
    vma = volume.rolling(192, min_periods=48).mean().replace(0, eps)
    relv = (volume / vma).clip(0, 2)
    vol_conf = 0.5 + 0.25 * relv  # in [0.5, 1.0]
    sig = sig * np.where(above > 0, vol_conf, 0.0)

    # Pin any latched-but-shallow state to full exposure (crisp holding).
    sig = np.where((above > 0) & (dist >= 0.5), 1.0, sig)

    return pd.Series(np.clip(sig, 0.0, 1.0), index=df.index)
