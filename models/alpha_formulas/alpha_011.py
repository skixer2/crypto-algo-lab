"""
alpha_011 — COMPOSITE: alpha_008 always-in long-biased graded core
+ alpha_010-style SHORT OVERLAY gated by CONFIRMED breakdown.
Hypothesis: every charter bucket has a proven specialist but no formula
holds two: 008 owns chop (100%), 010 owns down-profit (+3.13% while bench
-2.38%) but its fast valve inverted the +31% melt-up, 004 owns melt-ups.
Fix (JP directive 2026-10-02, results over method): deliberately combine
the proven mechanisms —
  CORE (from 008): continuous graded long exposure, base >= 0.15, EWMA
  conviction over ~1 day, calm-regime tilt, dip-friendly. Preserves chop
  capture and uptrend participation with wide stops.
  SHORT OVERLAY (from 010 down-profit mechanism, on a CONFIRMED clock):
  blended regime score R = 0.5*tanh(48h velocity z) + 0.5*7d-slope z,
  smoothed by a short EWM. Overlay shorts only when R < 0 on TWO
  consecutive evaluations (confirmed breakdown, not a fast wick) — this
  harvests down-windows as PROFIT instead of merely muting. Overlay is
  HARD-SUPPRESSED during reclaim conditions (Donchian 48h mid-cross with
  volume surge, or fast-EMA slope flip) so no fast-decay shorts fight an
  incipient melt-up (the 010 inversion failure mode).
Charter rules attacked: DOWN-SHIELD with profit stretch (overlay), the
WALL uptrend_participation (>=60%, core), extreme_participation (reclaim
suppression keeps core long into melt-ups), min_total_entries (always-in
core), medium_term_edge/consistency.
Author: escalation cycle 5 (explicit 008+010 component composite per JP
2026-10-02 11:23 UTC directive), 2026-10-02.
Provenance: tuner/runs/alpha_010_auto.json, tuner/runs/alpha_008_auto.json.
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]

    w = 48 * 4  # 48h of 15m bars
    minp = w // 2

    # ================= CORE (alpha_008 graded wide-stop engine) ==========
    ret = close.pct_change()
    sigma = ret.rolling(48, min_periods=20).std().replace(0, 1e-9)

    ema_f = close.ewm(span=32, min_periods=12).mean()
    ema_s = close.ewm(span=128, min_periods=40).mean()
    spread = (ema_f - ema_s) / close.replace(0, 1e-9)
    g_trend = 0.5 * (np.tanh((spread + 0.001) * 400.0) + 1.0)  # [0,1]

    mid = close.rolling(96, min_periods=32).mean()
    conviction = (close > mid).astype(float).rolling(96, min_periods=32).mean()

    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    atr_pct = (tr.rolling(48, min_periods=20).mean() / close.replace(0, 1e-9))
    atr_pct = atr_pct.replace(0, 0.001)
    calm = 0.5 * (np.tanh((0.006 - atr_pct) / 0.002) + 1.0)

    dip = np.tanh(-(close.pct_change(8) / (sigma * np.sqrt(8))) / 1.5)
    base = 0.15 + 0.30 * calm + 0.30 * conviction + 0.20 * dip.fillna(0)

    # fast-cut (008): keeps core from bleeding in sharp drops
    down_fast = -(close.pct_change(4) / (sigma * np.sqrt(4)))
    cut = 0.5 * (np.tanh((down_fast - 1.2) / 0.8) + 1.0)
    raw_core = base * (0.25 + 0.75 * g_trend) * (1.0 - 0.9 * cut)
    core = raw_core.ewm(span=32, min_periods=8).mean()  # [0, ~1]

    # ============ CONFIRMED-BREAKDOWN REGIME SCORE (blended clocks) =======
    # fast clock: 48h velocity z (010)
    vol48 = ret.rolling(w, min_periods=minp).std().replace(0, 1e-9)
    mean48 = close.rolling(w, min_periods=minp).mean()
    vel = ((close - mean48) / close.replace(0, 1e-9)).clip(-0.5, 0.5)
    vel_mu = vel.rolling(w, min_periods=minp).mean()
    vel_sd = vel.rolling(w, min_periods=minp).std().replace(0, 1e-9)
    vel_z = ((vel - vel_mu) / vel_sd).clip(-2, 2).fillna(0)
    # slow clock: 7d slope z
    slope = ((close - close.shift(w * 3)) / close.shift(w * 3).replace(0, 1e-9))
    slope = slope.clip(-0.5, 0.5).fillna(0)
    sl_mu = slope.rolling(w * 2, min_periods=w).mean()
    sl_sd = slope.rolling(w * 2, min_periods=w).std().replace(0, 1e-9)
    sl_z = ((slope - sl_mu) / sl_sd).clip(-2, 2).fillna(0)

    # blended regime score, EWM-smoothed, then require 2 consecutive
    # evaluations below 0 = CONFIRMED breakdown (not one bad bar)
    score = 0.5 * np.tanh(vel_z * 1.5) + 0.5 * np.tanh(sl_z * 1.5)
    score = score.ewm(span=16, min_periods=4).mean()
    neg = (score < 0).astype(float)
    confirmed = neg.rolling(2, min_periods=2).sum() >= 2  # 2 consecutive

    # ============ RECLAIM SUPPRESSION (anti-010-inversion) ================
    hh = high.rolling(w, min_periods=minp).max()
    ll = low.rolling(w, min_periods=minp).min()
    donch_mid = 0.5 * (hh + ll)
    above_mid = (close > donch_mid).astype(float)
    v_mu = volume.rolling(w, min_periods=minp).mean().replace(0, 1e-9)
    v_surge = (volume / v_mu > 1.5).astype(float)
    breakout = above_mid * v_surge
    ema_f_slope = (ema_f - ema_f.shift(4)).fillna(0)
    slope_flip = (ema_f_slope > 0).astype(float)
    reclaim = ((breakout > 0) | (slope_flip * above_mid > 0)).astype(float)

    # ============ SHORT OVERLAY (010 down-profit mechanism) ===============
    # graded short: stronger when blended score is deeply negative AND
    # confirmed over 2 consecutive evaluations; hard-zeroed on reclaim.
    short_mag = 0.5 * (np.tanh((-score - 0.5) * 2.0) + 1.0)  # [0,1]
    overlay = short_mag * confirmed.astype(float) * (1.0 - reclaim)
    overlay = overlay.ewm(span=8, min_periods=2).mean()

    # asymmetric composite: core always-on long bias, overlay only on
    # confirmed breakdown; instantly reclaims to core when suppression hits
    signal = core * (1.0 - 0.6 * overlay) - 0.9 * overlay
    return signal.clip(-1.0, 1.0).fillna(0.0)
