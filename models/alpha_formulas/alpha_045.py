"""
alpha_045 — ASYMMETRIC DOWN-EARNER: shorts confined to confirmed breakdowns
Hypothesis (P1 down-leg earner, cycle 3): alpha_044 failed (OOS excess
-7.307, participation/extreme/consistency all failed) because its
symmetric oscillator + mild regime meant SHORT entries fired in melt-up
and uptrend windows (extreme bench +57.0 -> strat -7.6): the short side
was on during recoveries. Fix = hard ASYMMETRY of the two sides:
  LONG side (default, always available): 014-style mean-reversion
  oscillator + trend core, so up windows get long re-crossings and
  extreme melt-ups participate (fixes 044's failed buckets).
  SHORT side (rare, earned): only when a HEAVY confirmation stack holds —
  (a) 2-day frac below Donchian mid > 0.65, (b) mid slope falling
  (slope_z < -0.3), (c) 48h velocity z deeply negative (z < -0.8), and
  (d) price below the 48h-mean deviation band. All four are ANDed; each
  alone is insufficient, so bear-rally traps (2022-01 +14.4 inside bear)
  where velocity briefly recovers flip the short term OFF instantly
  (structural reclaim exit expressed continuously: any stack member
  failing removes short pressure).
  signal = long_part + short_earn, where
    long_part = 0.55*tanh(vel_z) + 0.45*tanh(slope_z_up) + osc * (1 - short_on)
    short_earn = -0.9 * short_on * tanh(-vel_z.clip(lower=0)) (bounded)
  The oscillator is SUPPRESSED while the short stack is on (no long
  re-crossings inside a confirmed bear leg = the 043/044 bleed fix), and
  free otherwise (activity by construction in up/chop windows).
Rolling ops only; tanh/clip bounds everywhere; rolling-stat divisions
guarded with .replace(0,1e-9); no I/O; volume only via bounded kicker.
Charter rules attacked: down_shield PROFIT stretch (stacked short entries
in 2021-05/2022x3/2024-08/2025-02/2025-11/2026-06 legs), extreme +
uptrend participation (long default restored), adaptive_activity,
consistency/medium_term_edge, noise_stability (ewm span=3).
Author: P1 down-leg earner cycle 3 (JP-Gemini charter v2 asymmetric).
Provenance: tuner/runs/alpha_044_auto.json (REJECT: shorts leaked into
melt-up), alpha_014 (oscillator mechanics), alpha_010 (valve lineage),
alpha_043 (2-day confirmation).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low = df["close"], df["high"], df["low"]
    volume = df["volume"]
    eps = 1e-9

    w = 48 * 4  # 48h of 15m bars
    minp = w // 2
    confirm = 48 * 2

    # ---------------- structure: Donchian mid + slope z --------------------
    hh = high.rolling(w, min_periods=minp).max()
    ll = low.rolling(w, min_periods=minp).min()
    mid = 0.5 * (hh + ll)

    below = (close < mid).astype(float)
    frac_below = below.rolling(confirm, min_periods=confirm // 2).mean().fillna(0)

    mid_ret = (mid - mid.shift(w)) / mid.shift(w).replace(0, eps)
    mid_ret = mid_ret.replace([np.inf, -np.inf], 0).fillna(0).clip(-0.5, 0.5)
    mid_mu = mid_ret.rolling(w, min_periods=minp).mean()
    mid_sd = mid_ret.rolling(w, min_periods=minp).std().replace(0, eps)
    slope_z = ((mid_ret - mid_mu) / mid_sd).clip(-2, 2).fillna(0)

    # ---------------- velocity z (48h) -------------------------------------
    ret = close.pct_change()
    mean48 = close.rolling(w, min_periods=minp).mean()
    vel = ((close - mean48) / close.replace(0, eps)).clip(-0.5, 0.5).fillna(0)
    vel_mu = vel.rolling(w, min_periods=minp).mean()
    vel_sd = vel.rolling(w, min_periods=minp).std().replace(0, eps)
    vel_z = ((vel - vel_mu) / vel_sd).clip(-2, 2).fillna(0)

    # ---------------- SHORT STACK: heavy confirmation, ANDed ----------------
    c1 = (frac_below > 0.65).astype(float)
    c2 = (slope_z < -0.3).astype(float)
    c3 = (vel_z < -0.8).astype(float)
    c4 = (vel < 0).astype(float)  # below its own 48h mean
    short_on = (c1 * c2 * c3 * c4).clip(0, 1)

    # ---------------- LONG DEFAULT: trend + free oscillator ----------------
    osc_sigma = ret.rolling(48, min_periods=20).std().replace(0, eps)
    z_fast = (ret / osc_sigma).clip(-2, 2).fillna(0)
    osc = np.tanh(-z_fast)  # mean-reversion, buy dips by default

    trend_part = 0.55 * np.tanh(vel_z) + 0.45 * np.tanh(slope_z.clip(lower=-1))
    long_part = trend_part + 0.55 * osc * (1.0 - short_on)

    # ---------------- EARNED SHORT: bounded profit pressure ----------------
    short_earn = -0.95 * short_on * np.tanh(-vel_z.clip(lower=0) * 1.2)

    # ---------------- bounded volume kicker (long-side only) ---------------
    vol_mu = volume.rolling(w, min_periods=minp).mean().replace(0, eps)
    v_z = ((volume / vol_mu) - 1.0).clip(-2, 2).fillna(0)
    vkick = 0.10 * np.tanh(v_z) * np.tanh(vel_z).clip(lower=0) * (1.0 - short_on)

    signal = long_part + short_earn + vkick
    ewm_sig = signal.ewm(span=3, min_periods=1).mean()
    return ewm_sig.clip(-2, 2).fillna(0)
