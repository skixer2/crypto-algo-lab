"""
alpha_044 — SHORT-EARNING OSCILLATOR: entries-by-construction down-leg earner
Hypothesis (P1, JP promotion 2026-10-07, cycle 2): alpha_043 had the right
mechanics (2-day confirmed Donchian breakdown, instant reclaim exit) but
NEVER TRADED — 0 entries in every window, so gates showed
adaptive_activity 0/0.0 and even down-shield passed only by sitting flat.
Post-mortem says the failure is alpha_011/012/013's failure repeated:
one-signed, gated signals do not re-cross the tuner's long/short
thresholds. alpha_014 fixed exactly this with a MEAN-ZERO oscillator whose
crossings are guaranteed by construction. alpha_044 fuses the two:
  signal = A * regime + B * osc,  A = 0.65, B = 0.50
  regime  = tanh(0.7*tanh(-vel_z) + 0.3*tanh(mid_slope_z)) — negative in
    confirmed breakdowns (48h velocity z + declining Donchian mid), positive
    on reclaim, bounded +/-1. The confirmed-breakdown gate from 043 (frac of
    last 2 days below mid > 0.55 AND mid falling) DEEPENS the regime rather
    than hard-gating it to zero, so the signal is never dead.
  osc     = tanh(-z_fast) — 014's zero-mean 8-bar mean-reversion oscillator.
    Bear regime pulls the mean to ~ -0.7, so every dead-cat bounce re-crosses
    the short_threshold (short entries earn down-windows: 2021-05, 2022x3,
    2024-08, 2025-02, 2025-11, 2026-06) and every micro-dip re-crosses
    long_threshold in up windows (participation preserved). Reclaim
    (close back above mid with volume/velocity support) flips the regime
    positive fast — the 043 instant-exit, now expressed continuously.
  Volume surge component scaled by its own tanh to keep bounds.
Charter rules attacked: down_shield PROFIT stretch (short-side re-crossings
in confirmed bear legs), adaptive_activity (entries by construction),
medium_term_edge/consistency, noise_stability (ewm span=3 smoother),
uptrend_participation (positive regime mean on reclaim).
Author: P1 down-leg earner cycle 2 (JP-Gemini charter v2 asymmetric),
2026-10-10.
Provenance: tuner/runs/alpha_043_auto.json (0 entries everywhere —
gate-to-zero failure), mechanisms from alpha_014.py (entries by
construction), alpha_010.py (valve clocks), alpha_043.py (confirmation).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    high, low = df["high"], df["low"]
    volume = df["volume"]
    eps = 1e-9

    w = 48 * 4          # 48h of 15m bars
    minp = w // 2
    confirm = 2 * w     # 2 days of 15m bars

    # ---------------- structure: trailing Donchian mid-band ----------------
    hh = high.rolling(w, min_periods=minp).max()
    ll = low.rolling(w, min_periods=minp).min()
    mid = 0.5 * (hh + ll)

    below = (close < mid).astype(float)
    frac_below = below.rolling(confirm, min_periods=w).mean().fillna(0)

    # mid-band slope as a z-score (bounded) instead of a hard sign gate
    mid_ret = (mid - mid.shift(w)) / mid.shift(w).replace(0, eps)
    mid_ret = mid_ret.replace([np.inf, -np.inf], 0).fillna(0).clip(-0.5, 0.5)
    mid_mu = mid_ret.rolling(w, min_periods=minp).mean()
    mid_sd = mid_ret.rolling(w, min_periods=minp).std().replace(0, eps)
    mid_slope_z = ((mid_ret - mid_mu) / mid_sd).clip(-2, 2).fillna(0)

    # ---------------- velocity z (48h) -------------------------------------
    ret = close.pct_change()
    mean48 = close.rolling(w, min_periods=minp).mean()
    vel = ((close - mean48) / close.replace(0, eps)).clip(-0.5, 0.5).fillna(0)
    vel_mu = vel.rolling(w, min_periods=minp).mean()
    vel_sd = vel.rolling(w, min_periods=minp).std().replace(0, eps)
    vel_z = ((vel - vel_mu) / vel_sd).clip(-2, 2).fillna(0)

    # ---------------- REGIME: continuous, never zero-gated ------------------
    # confirmed breakdown deepens the bear view; no hard kill anywhere.
    confirmed = ((frac_below > 0.55) & (mid_slope_z < 0)).astype(float)
    regime_raw = 0.7 * np.tanh(-1.2 * vel_z) + 0.3 * np.tanh(-1.0 * mid_slope_z)
    # confirmation boosts the bear magnitude (deepens short side)
    regime_raw = regime_raw - 0.4 * confirmed * np.tanh(-vel_z.clip(lower=0))
    regime = np.tanh(regime_raw)  # bounded +/-1

    # ---------------- OSC: zero-mean fast mean reversion --------------------
    sigma_fast = ret.rolling(48, min_periods=20).std().replace(0, eps)
    z_fast = (ret / sigma_fast).clip(-2, 2).fillna(0)
    osc = np.tanh(-z_fast)

    # ---------------- volume kicker (bounded, both sides) -------------------
    vol_mu = volume.rolling(w, min_periods=minp).mean().replace(0, eps)
    v_z = ((volume / vol_mu) - 1.0).clip(-2, 2).fillna(0)
    vkick = 0.10 * np.tanh(v_z) * regime  # amplifies the prevailing view

    signal = 0.65 * regime + 0.50 * osc + vkick
    ewm_sig = signal.ewm(span=3, min_periods=1).mean()
    return ewm_sig.clip(-2, 2).fillna(0)
