"""
alpha_019 — melt-up specialist: regime-blind sigma-velocity breakout, v2
Hypothesis: post-drop V-reversal melt-ups (w16 2026-08-16, bench +31.3%) are
missed by every regime-gated formula; only alpha_004 (+11.8%) ever caught one
because it triggers within hours of a vertical break from ANY preceding state.
This v2 deepens that design: (1) faster multi-horizon velocity (1h+2h) in
trailing sigma units with explosive-move emphasis via tanh((v-c0.5)+) so only
accelerations fire, not drift; (2) volume thrust confirmation (relative volume
z-score, rising-volume slope) — real melt-ups expand volume, drifts don't;
(3) NO regime gate, NO slow-EMA drag — long-only asymmetric trigger that
goes flat instantly when velocity collapses (rides wide, exits fast).
Rule attacked: EXTREME_PARTICIPATION (bench >= +15% -> strat > 0), which 11
of 12 formulas log 0 entries on; secondary: uptrend participation lift.
Author: auto-gen (isolated alpha loop), 2026-10-04.
Inputs: OHLCV (close, volume). Provenance: alpha_004.py source + runs
alpha_016..018 (extreme_participation failures, 0 entries in melt-up window).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    # 1. Explosive velocity: 1h + 2h returns in trailing sigma units.
    ret = close.pct_change()
    sigma = ret.rolling(32, min_periods=16).std().replace(0, 1e-9)
    v = (close.pct_change(4) + 0.7 * close.pct_change(8)) / (
        sigma * np.sqrt(4)
    )

    # 2. Acceleration emphasis: only ABOVE-expected velocity counts.
    #    tanh((v - 0.5)+ ) -> drift/flat ~ 0, vertical break -> -> +1 fast.
    thrust = np.tanh(np.clip(v - 0.5, 0.0, None) / 1.5)

    # 3. Volume thrust: relative volume + rising-volume slope, graded [0.3,1].
    vol_rel = volume / volume.rolling(48, min_periods=16).mean().replace(0, 1e-9)
    vol_slope = (
        volume.rolling(4).mean()
        / volume.rolling(16).mean().replace(0, 1e-9)
    ).fillna(1.0)
    vol_conf = 0.3 + 0.7 * np.tanh(
        ((vol_rel - 1.0) / 1.5 + 0.5 * (vol_slope - 1.0))
    )
    vol_conf = vol_conf.clip(0.3, 1.0)

    # 4. Instant-off: velocity must persist (mean of last 2 trigger bars) so
    #    single spikes don't hold position, but real breaks ride while hot.
    fire = thrust * vol_conf
    sig = (fire + 0.5 * fire.rolling(2, min_periods=1).mean()).fillna(0.0)
    return sig.clip(0.0, 1.0)
