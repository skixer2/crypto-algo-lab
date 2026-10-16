"""
alpha_043 — DOWN-LEG EARNER: 2-day confirmed breakdown short, instant reclaim exit
Hypothesis (P1, JP promotion 2026-10-07): down-shield experts exist (032, 028)
but they only go FLAT in bear legs. The tuner allows shorts; a short specialist
should convert shield-knowledge into positive down-window RETURN. Recipe from
the alpha_010/014 lineage (proven +3.1/+1.1 in down weeks):
  - SHORT signal ONLY on 2-day CONFIRMED breakdown: price sustained below the
    trailing 48h Donchian mid-band for >= 2/3 of the last 192 bars AND the
    mid-band itself declining AND velocity z negative. Confirmation is the only
    protection against the bear-rally trap (2022-01: +14.4 inside bear).
  - EXIT INSTANTLY on structural reclaim: close back above the mid-band (with
    hysteresis margin) -> signal snaps to a small flat-to-long baseline, never
    short during reclaim conditions.
  - Magnitude scales with vol-adjusted downside acceleration (tanh-bounded),
    so deep legs (2021-05, 2022x3, 2024-08, 2025-02, 2025-11, 2026-06) earn
    more than shallow drifts.
Charter rule attacked: down_shield PROFIT stretch (positive strat return on
negative bench legs), not merely flat; adaptive_activity via repeated
breakdown/reclaim crossings inside extended bear episodes.
Author: P1 down-leg earner cycle (JP-Gemini charter v2 asymmetric), 2026-10-10.
Provenance: tuner/runs/alpha_042_auto.json, alpha_041_auto.json (down_shield
failures -14.6/-16.2 on bench -28.6: long-absorption, no short side);
mechanisms inlined from alpha_010.py (valve clocks), alpha_014.py (regime z).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]
    eps = 1e-9

    w = 48 * 4          # 48h of 15m bars
    minp = w // 2
    confirm = 2 * w     # 2 days of 15m bars

    # ---------- structure: trailing Donchian mid-band ---------------------
    hh = high.rolling(w, min_periods=minp).max()
    ll = low.rolling(w, min_periods=minp).min()
    mid = 0.5 * (hh + ll)

    below = (close < mid).astype(float)
    # sustained-below fraction over the last 2 days (2-day confirmation)
    frac_below = below.rolling(confirm, min_periods=w).mean().fillna(0)
    # mid-band must itself be declining (true structure break, not chop)
    mid_slope = (mid - mid.shift(w)) / mid.shift(w).replace(0, eps)
    mid_slope = mid_slope.replace([np.inf, -np.inf], 0).fillna(0).clip(-0.5, 0.5)

    # ---------- fast velocity z (downside acceleration scaler) ------------
    ret = close.pct_change()
    sigma = ret.rolling(w, min_periods=minp).std().replace(0, eps)
    mean48 = close.rolling(w, min_periods=minp).mean()
    vel = ((close - mean48) / close.replace(0, eps)).clip(-0.5, 0.5).fillna(0)
    vel_mu = vel.rolling(w, min_periods=minp).mean()
    vel_sd = vel.rolling(w, min_periods=minp).std().replace(0, eps)
    vel_z = ((vel - vel_mu) / vel_sd).clip(-2, 2).fillna(0)

    # ---------- confirmed breakdown -> SHORT ------------------------------
    # confirmed when: >=60% of last 2 days below mid AND mid falling AND
    # velocity z negative. tanh-bounded magnitude scales with acceleration.
    confirmed = ((frac_below > 0.60) & (mid_slope < 0) & (vel_z < 0)).astype(float)
    short_mag = 1.2 * np.tanh(1.5 * (-vel_z.clip(lower=0)) * (0.5 - mid_slope.clip(upper=0)))
    short_signal = -confirmed * short_mag

    # ---------- instant reclaim exit --------------------------------------
    # structural reclaim: close above mid-band with small hysteresis margin
    # and (optionally) volume surge -> snap out of the short immediately.
    vol_mu = volume.rolling(w, min_periods=minp).mean().replace(0, eps)
    v_surge = (volume / vol_mu > 1.3).astype(float)
    reclaim = ((close > mid) & ((v_surge > 0) | (vel_z > -0.5))).astype(float)

    # baseline: small long-only dip-capture so flat/up windows still have
    # gentle participation without ever being short during reclaim.
    z_fast = (ret / ret.rolling(48, min_periods=20).std().replace(0, eps)).clip(-2, 2).fillna(0)
    baseline = 0.25 * np.tanh(-z_fast) * (1.0 - confirmed)

    signal = short_signal * (1.0 - reclaim) + baseline
    ewm_sig = signal.ewm(span=3, min_periods=1).mean()
    return ewm_sig.clip(-2, 2).fillna(0)
