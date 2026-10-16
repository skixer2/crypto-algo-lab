"""
alpha_062 — TURTLE LATCH v2: crisp binary bull-surfing latch (P1 bull seat)
Hypothesis (JP design 2026-10-11): the bull seat fails because graded/EWM
memory dilutes the signal below the tuner's entry threshold (alpha_026 death).
Here the signal is a PINNED BINARY LATCH: +1.0 while close > trailing
structural level (rolling max of high, shifted 1 bar so it is trailing-only),
0.0 below. No decay, no memory bleed — holding is binary. A short tanh ramp
on (close - trail)/ATR gives the tuner a smooth entry slope near the boundary
only (max +0.4, so even the ramp cannot be diluted: full entry at
signal_exit_threshold is guaranteed by the pinned +1.0 body).
Volume confirmation boosts the entry ramp slightly (legal, bounded) but the
latch itself is price-structural only. Wide structural exit only: the latch
drops when close falls below the N-bar trailing high, N long (192 bars = 48h)
chosen so slow melt-ups (2022-07/2023-10 style V-recoveries, +56%/+14% bench)
stay latched for the whole leg.
Charter rules attacked: uptrend_participation (>=60% x bench), extreme_
participation (bench>=15% -> strat>0), adaptive_activity (latch spans are
long => mean activity/active window high), medium_term_edge.
What NOT to do (alpha_026 autopsy): no EWM decay on the holding state, no
graded memory — the latch is exactly {0, 1} away from the boundary ramp.
Author: auto-gen isolated alpha loop, 2026-10-15. Provenance:
tuner/runs/alpha_061_auto.json, alpha_060_auto.json (failed_gates:
uptrend_participation, extreme_participation, adaptive_activity=0).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    high = df["high"]
    volume = df["volume"]
    eps = 1e-9

    # Trailing structural level: rolling max of high, shifted 1 bar.
    n = 192  # 48h of 15m bars
    trail = high.rolling(n, min_periods=n // 2).max().shift(1)

    # ATR (Wilder-lite, EWM) for boundary normalization.
    tr = pd.concat(
        [
            high - df["low"],
            (high - close.shift(1)).abs(),
            (df["low"] - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(span=96, adjust=False).mean().replace(0, eps)

    # Distance above the structural level in ATR units, bounded to 2.
    dist = ((close - trail) / atr).clip(-2, 2)

    # Latch state: 1 above level, 0 below.
    latch = (close > trail).astype(float)

    # Entry smoothness ramp near the boundary only (max 0.4, cannot dilute
    # the pinned latch body once inside).
    ramp = 0.4 * np.tanh(dist / 1.0) * latch

    # Volume confirmation of the breakout edge (bounded, optional boost).
    vma = volume.rolling(96, min_periods=24).mean().replace(0, eps)
    volz = ((volume - vma) / (vma * 2.0)).clip(-2, 2)
    vol_boost = 0.1 * np.tanh(volz) * ramp

    signal = latch + ramp + vol_boost
    return signal.fillna(0.0)
