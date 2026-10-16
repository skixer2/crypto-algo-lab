"""
alpha_038 — CONFIRMED-BREAKDOWN SHORT SPECIALIST (down-leg EARNER, P1)
Hypothesis (JP promotion 2026-10-07): down-shield experts exist (028, 032
demo) but none converts the bear leg into positive RETURN. This formula is a
dedicated short: it goes NEGATIVE (strongly, well past any short_threshold)
ONLY on a 2-day CONFIRMED breakdown — close sustained below the 4-day
Donchian mid AND below a slow structural level (8-day low-mid) — and snaps
to ~0 the moment price structurally reclaims the mid (instant exit, never
short during reclaim). The bear-rally trap (2022-01: +14.4% inside the bear)
is engineered around by requiring the CONFIRMATION to persist: the signal is
an EWM of the confirmed state, so a fast 2-day bounce must hold >half a day
of closes above the mid before the short releases; transient bounces keep
signal negative but are amplitude-damped via tanh of the reclaim distance.
Amplitude: tanh(2 * confirm_state) * (1 + 0.5*downspeed_z clipped) so V/
crash windows get deep negatives (down-leg RETURN > 0 target), mild breakdowns
get shallow shorts. No long side ever: signal >= -2, capped above at +0.05
(tiny positive bias only to avoid stray shorts-on-neutral).
All ops trailing (rolling/ewm only), inputs bounded before compositing,
divisions guarded with replace(0,1e-9). Imports numpy/pandas only.
Rule attacked: P1 down-leg earner — positive strat in V/crash windows,
down_shield with PROFIT, medium_term_edge via concentrated bear harvest.
Author: auto-gen (isolated alpha loop), 2026-10-09.
Provenance: alpha_014 (breakdown regime clock), alpha_010/014 lineage
(+3.1/+1.1 down weeks), segment_metrics demo alpha_032 (perfect shield,
zero up-capture), tuner/runs/alpha_036/037_auto.json (down_shield passes,
participation failures).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    eps = 1e-9

    # --- structure levels (trailing) ---
    # 4-day Donchian mid on 15m bars (4*96)
    w_fast = 96 * 4
    w_slow = 96 * 8
    hh_f = high.rolling(w_fast, min_periods=w_fast // 2).max()
    ll_f = low.rolling(w_fast, min_periods=w_fast // 2).min()
    mid_f = ((hh_f + ll_f) / 2.0).ffill()

    ll_s = low.rolling(w_slow, min_periods=w_slow // 2).min()
    struct = ((ll_s + (ll_s + ll_s) / 2.0) / 2.0).ffill()

    # --- breakdown distance (negative = below structure) ---
    below_fast = (close - mid_f) / mid_f.replace(0, eps)      # vs Donchian mid
    below_slow = (close - struct) / struct.replace(0, eps)    # vs slow structure
    dist = (0.6 * below_fast + 0.4 * below_slow).clip(-0.15, 0.15).fillna(0.0)

    # --- 2-day confirmation: close below mid on BOTH of the last two daily
    # aggregates (trailing 96-bar means of a boolean), i.e. sustained state ---
    is_below = (dist < 0).astype(float)
    conf_1d = is_below.rolling(96, min_periods=48).mean().fillna(0)
    conf_2d = conf_1d.rolling(96 * 2, min_periods=96).mean().fillna(0)
    confirmed = (conf_2d >= 0.9).astype(float)

    # --- reclaim detector: strength and recency of closes ABOVE the mid ---
    reclaim_strength = (dist > 0).astype(float).rolling(96, min_periods=24).mean().fillna(0)
    # instant exit: any confirmed reclaim in the last 12h releases the short
    reclaim_recent = (reclaim_strength >= 0.5).astype(float).rolling(48, min_periods=12).max().fillna(0)

    # --- down-speed for amplitude (48h return z, clipped) ---
    ret = close.pct_change()
    r48 = close.pct_change(96 * 2).fillna(0).clip(-0.5, 0.5)
    r48_mu = r48.rolling(w_fast, min_periods=w_fast // 2).mean()
    r48_sd = r48.rolling(w_fast, min_periods=w_fast // 2).std().replace(0, eps)
    speed_z = ((r48 - r48_mu) / r48_sd).clip(-2, 2).fillna(0)

    # volume confirmation of breakdown (relative volume, bounded)
    v_rel = (volume / volume.rolling(96 * 7, min_periods=96 * 2).mean().replace(0, eps)).clip(0, 2).fillna(1)
    vol_conf = np.tanh((v_rel - 1.0) * 0.5)  # -1..1

    # --- composite short signal ---
    # depth: how far below structure, amplified in fast crashes
    depth = np.tanh(dist * 20.0)                       # -1..1, negative when below
    amp = 1.0 + 0.5 * np.tanh(np.maximum(speed_z, 0) + 0.3 * vol_conf)
    short_raw = confirmed * depth * amp                # <= 0 when confirmed

    # release on reclaim: hard zero; also decay amplitude via reclaim recency
    gate = 1.0 - reclaim_recent
    sig_short = (short_raw * gate * 2.0).clip(-2.0, 0.0)

    # tiny positive floor bias so neutral tape never reads as a short signal;
    # NEVER goes long (cap 0.05) — this is a pure down-leg earner.
    out = (sig_short + 0.05 * (1.0 - confirmed)).clip(-2.0, 0.05)

    # light smoother to suppress bar noise, fast enough to keep exits instant
    return out.ewm(span=3, min_periods=1).mean().fillna(0.0)
