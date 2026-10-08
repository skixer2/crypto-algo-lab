"""
alpha_023 — melt-up specialist: regime-blind sigma-velocity break trigger
Hypothesis: the melt-up quadrant (+31.33% window) is owned only by alpha_004,
whose params are stale and whose clip(lower=0) long-only asymmetry plus a
1.5-sigma tanh saturation fires too late/slow on a vertical break. This
evolution keeps the regime-BLIND mandate (no regime gate, no overlay drag)
but sharpens the trigger: (a) multi-scale velocity with extra weight on the
fastest leg so a vertical break saturates within ~1-4 bars of 15m data,
(b) sigma estimated on a short trailing window so baseline chop does not
inflate the denominator and dampen real breaks, (c) volume surge
confirmation that boosts (never gates to zero) so quiet tape doesn't kill
the position, (d) mild asymmetric expansion: rides stay full (no decay once
fired — signal holds while velocity stays positive), giving the wide-take
ride the design requires.
Rule attacked: EXTREME_PARTICIPATION (bench >= +15% -> strat > 0) and
UPTREND_PARTICIPATION, with down-shield as secondary (velocity negative ->
signal ~0, shorts allowed softly).
Author: auto-gen (isolated alpha loop), 2026-10-05.
Inputs: OHLCV (close, volume only). Provenance: alpha_004.py source;
tuner/runs/alpha_021/022 failure reports (missed melt-up windows).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    # 1. Short-window trailing sigma (12 bars ~ 3h): fast adaptive baseline
    ret = close.pct_change()
    sigma = ret.rolling(12, min_periods=6).std().replace(0, 1e-9)

    # 2. Multi-scale velocity in sigma units, fastest leg dominant
    v_fast = close.pct_change(2)
    v_mid = close.pct_change(6)
    v_slow = close.pct_change(16)
    velocity_sigma = (1.0 * v_fast + 0.6 * v_mid + 0.3 * v_slow) / (
        sigma * np.sqrt(2.0)
    )

    # 3. Regime-blind trigger: saturates by ~1.2 sigma — fires within hours
    trigger = np.tanh(velocity_sigma / 1.2)

    # 4. Volume surge: boosts a real break, floors at 0.5 (never kills it)
    vol_rel = volume / volume.rolling(24, min_periods=8).mean().replace(0, 1e-9)
    vol_conf = 0.5 + 0.5 * np.tanh((vol_rel - 1.0) / 1.0)  # in [0.0, 1.0] +0.5

    # 5. Ride-preserving softener: hold full size while momentum intact.
    #    EMA of trigger over 8 bars keeps fired positions from flickering
    #    back to zero on the first pullback bar (wide-take ride).
    ride = trigger.ewm(span=8, min_periods=2).mean()

    sig = ride * (0.7 + 0.6 * vol_conf)
    return np.tanh(sig / 1.5).clip(-1, 1).fillna(0.0)
