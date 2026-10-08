"""
alpha_022 — gateless volume-confirmed sigma-velocity (melt-up specialist)
Hypothesis: the melt-up quadrant is owned solely by stale alpha_004 because its
EMA-spread gate is structurally closed exactly at a V-reversal breakout (fast
EMA still below slow EMA for hours after the vertical break), yielding 0
entries in the +31.33% window. This formula attacks EXTREME PARTICIPATION
(bench >= +15% -> strat > 0) and down-window PROFIT with a regime-BLIND
design: the raw multi-horizon sigma-velocity IS the signal, in both
directions — instant longs on vertical up-breaks from any preceding state,
and shorts on confirmed breakdowns (which earns down_shield rather than
failing it). No regime gate, no long/flat clipping, no overlay drag.
Volume confirmation is multiplicative and sign-preserving (in [0.35, 1.0]):
breakouts on expanding volume pass at full strength; thin spikes are damped
but never zeroed, preserving entry counts. A fast EWM (span=6, ~1.5h) smooths
the signal for noise stability without meaningful lag on a melt-up measured
in hours. Velocity is normalized by trailing per-bar sigma (rolling std,
replace(0,1e-9)) and tanh-squashed so |inputs| <= ~2 before any compositing.
Author: auto-gen (isolated alpha loop), 2026-10-05.
Inputs: OHLCV (close, volume). Provenance: tuner/runs/alpha_019..021_auto.json
(extreme_participation failures, 0 entries on +31.33% window) and alpha_004.py
design lessons (gate-closure at V-reversal).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    # 1. Regime-blind trigger: blended 2-bar and 8-bar return in sigma units.
    ret = close.pct_change()
    sigma = ret.rolling(48, min_periods=20).std().replace(0, 1e-9)
    velocity_sigma = (close.pct_change(2) + 0.5 * close.pct_change(8)) / (
        sigma * np.sqrt(2)
    )
    trigger = np.tanh(velocity_sigma / 1.2)  # sign-preserving, |x| <~ 2

    # 2. Volume confirmation: multiplicative, sign-preserving, in [0.35, 1].
    #    vol_rel ~ 1 (normal) -> 0.55; vol_rel = 2 -> ~0.93; thin -> 0.35 floor.
    vol_rel = volume / volume.rolling(32, min_periods=12).mean().replace(0, 1e-9)
    vol_conf = 0.35 + 0.65 * 0.5 * (np.tanh((vol_rel - 1.0) / 0.8) + 1.0)

    # 3. Fast smoothing (noise stability) — 6 bars ~ 1.5h, negligible vs a
    #    melt-up that runs for hours-to-days; keeps the breakout signal alive.
    sig = (trigger * vol_conf).ewm(span=6, min_periods=2).mean()

    return sig.clip(-1, 1).fillna(0.0)
