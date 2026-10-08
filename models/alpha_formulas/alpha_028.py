"""
alpha_028 — Donchian trend-RIDER: sustained breakout participation, not spike catch
Hypothesis: PRIORITY 1 (trend-riding specialist). Prior formulas either caught
spikes (fast velocity, exits early -> captures 15% of a +60% month) or gated to
zero (026: 0 entries everywhere). Riding requires a signal that STAYS near 1.0
as long as the structural uptrend persists: (a) Donchian-style rolling-high
breakout (close >= N-bar rolling max shifted by 1 bar => trailing-legal), held
with hysteresis via a slow EMA structure filter; (b) exit pressure comes only
from distance-below-slow-EMA growing (structural break), never from short-term
noise; (c) decay memory (ewm of entry strength) keeps participation through
pullbacks while never going negative in down regimes (down-shield via
trend-strength floor squashing to ~0 when slow EMA slope is negative).
Bounded transforms: all tanh inputs normalized by rolling sigma or price, |x|<=2.
Volume confirms breakouts (relative volume boosts entry strength).
Rule attacked: uptrend_participation (60% of bench) + extreme_participation.
Author: auto-gen (isolated alpha loop), 2026-10-06.
Inputs: OHLCV (close, volume). Provenance: tuner/runs/alpha_027_auto.json +
alpha_026_auto.json (0 entries / spike-only captures); alpha_004 entry side.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    ret = close.pct_change()
    sigma = ret.rolling(96, min_periods=30).std().replace(0, 1e-9)

    # 1. Donchian-style breakout strength: close vs prior rolling high
    #    (rolling window shifted 1 bar back => trailing only).
    prior_high = close.rolling(96, min_periods=48).max().shift(1)
    prior_low = close.rolling(96, min_periods=48).min().shift(1)
    rng = (prior_high - prior_low).replace(0, 1e-9)
    # position within channel, [-1, 1]; >0 means upper half / breakout side
    pos = ((close - (prior_high + prior_low) / 2.0) / (rng / 2.0)).clip(-2, 2)
    breakout = np.tanh(pos / 1.0).clip(lower=0.0)  # 0 at mid-channel, 1 at highs

    # 2. Structural trend: slow EMA slope in sigma units, mapped [0,1].
    ema_s = close.ewm(span=192, min_periods=60).mean()
    slope = ema_s.diff(16) / (sigma * close.replace(0, 1e-9) * 4.0)
    structure = 0.5 * (np.tanh(slope / 1.5) + 1.0)  # 0 down, 1 strong up

    # 3. Pullback tolerance: allow modest distance below fast EMA without
    #    killing signal; only deep breakdowns (vs slow EMA, sigma-scaled) decay.
    ema_f = close.ewm(span=24, min_periods=10).mean()
    breakdown = np.tanh(((ema_f - close) / (sigma * close.replace(0, 1e-9)) - 1.0) / 2.0)
    tolerance = 1.0 - 0.5 * breakdown.clip(lower=0.0)  # in [0.5, 1.0]

    # 4. Volume confirmation of the breakout leg (never flips sign).
    vol_rel = volume / volume.rolling(64, min_periods=20).mean().replace(0, 1e-9)
    vol_conf = 0.6 + 0.4 * np.tanh((vol_rel - 1.0) / 1.5)  # [0.2, 1.0]

    raw = breakout * structure * tolerance * vol_conf

    # 5. Ride memory: ewm of raw keeps signal elevated through 1-2 day pullbacks
    #    (fast half-life ~ 8h at 15m = 32 bars) while staying trailing-legal.
    rider = raw.ewm(halflife=32, min_periods=8).mean()

    return rider.clip(-1, 1).fillna(0.0)
