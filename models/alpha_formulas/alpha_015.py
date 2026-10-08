"""
alpha_015 — melt-up specialist: regime-blind vertical-break velocity
Hypothesis: post-drop V-reversal melt-ups are only catchable by a signal that
does NOT wait for regime confirmation. alpha_004's gate/vol drag delayed entry
past the vertical move (0 entries in the +31.33% week). This design strips all
gates: a pure sigma-velocity impulse detector on a very fast smoothing of the
price path — fires LONG within hours of a vertical break from ANY preceding
state (drop, chop, or rally), rides with a graded signal that decays slowly so
the tuner's wide-take exit profile can hold the move. Volume surge adds punch
(multiplicative, bounded, never blocks). No EMA longer than 96 bars = 24h.
Rule attacked: extreme_participation (bench >= +15% -> strat > 0), the scarcest
quadrant, owned only by a stale alpha_004.
Author: auto-gen (isolated alpha loop), 2026-10-03.
Inputs: OHLCV (close, volume). Provenance: tuner/runs/alpha_013/014_auto.json
(extreme window 0 entries) + alpha_004.py source study.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    # 1. Smoothed momentum impulse: fast EWM of returns keeps the vertical
    #    break sharp while killing single-bar noise. Two horizons, fast-heavy.
    ret = close.pct_change()
    fast = ret.ewm(span=4, min_periods=2).mean()
    med = ret.ewm(span=12, min_periods=4).mean()
    impulse = fast + 0.5 * med

    # 2. Scale by trailing per-bar sigma -> tanh input discipline |x| <~ 2.
    sigma = ret.rolling(48, min_periods=20).std().replace(0, 1e-9)
    z = impulse / sigma

    # 3. Sustain term: how far price is above its trailing mean, in sigma.
    #    Vertical breaks create large sustain; this keeps the signal alive
    #    for hours after the initial impulse (rides the melt-up).
    ma = close.ewm(span=48, min_periods=16).mean()
    mad = (close - ma).abs().ewm(span=48, min_periods=16).mean().replace(0, 1e-9)
    sustain = (close - ma) / (mad * 2.0)

    # 4. Bounded squash BEFORE compositing (|inputs| capped by design).
    drive = np.tanh(z / 1.5) + 0.5 * np.tanh(sustain / 2.0)

    # 5. Volume surge amplifier in [0.5, 1.2]: adds punch on real breakouts,
    #    never blocks entry (alpha_004 lesson: vol gating delayed fires).
    vol_rel = volume / volume.rolling(32, min_periods=12).mean().replace(0, 1e-9)
    vol_amp = 0.5 + 0.35 * np.tanh((vol_rel - 1.0) / 1.5) + 0.35 * np.tanh(
        (vol_rel - 2.5) / 2.0
    )

    sig = drive * vol_amp
    return np.tanh(sig / 1.2).clip(-1, 1).fillna(0.0)
