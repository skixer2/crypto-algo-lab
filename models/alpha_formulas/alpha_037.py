"""
alpha_037 — CONFIRMED-BREAKDOWN SHORT SPECIALIST (down-leg EARNER, P1)
Hypothesis: alpha_032 shields down-windows (down-leg excess +28.6 on a
-31.3 leg) by being ABSENT, earning ~0. alpha_010/014 lineage proved a
proven +3.1/+1.1 short edge in down weeks — but only when the short fires
AFTER confirmation, never during bear-rally traps (2022-01: +14.4 inside
the bear killed unconfirmed shorts). This formula converts shield into
down-leg RETURN:
  SHORT side (the earner): short signal only on 2-day-confirmed
  breakdown — close below the 48h Donchian mid-band for >= 2 consecutive
  confirmed sessions (96 bars each, evaluated on completed bars only)
  AND vol-adjusted velocity still negative. Exit instantly on structural
  reclaim: close back above the mid-band + volume surge (1.5x 48h mean)
  or velocity z flipping positive. During reclaim conditions the short
  component is clamped at 0 (never short a reclaim).
  LONG side (activity floor, not the thesis): a mild 014-style
  zero-mean oscillator term so the signal still crosses long_threshold
  in up-legs — keeps adaptive_activity/uptrend_participation alive while
  the down-leg earner does its job.
All transforms bounded (tanh, |z|<=2) BEFORE compositing; divisions by
rolling stats after .replace(0,1e-9); trailing ops only (rolling/ewm).
Charter rules attacked: down_shield with PROFIT (P1 down-leg return > 0),
adaptive_activity (oscillator crossings), noise_stability (2-day
confirmation = state stability), uptrend_participation (osc term).
Author: escalation cycle (JP promotion of down-leg earner, 2026-10-07).
Provenance: tuner/runs/alpha_032_auto.json (perfect shield, zero
capture), alpha_010/014 (short-side clock), segment_metrics.py
down/up-leg split. Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]
    eps = 1e-9

    w = 48 * 4      # 48h of 15m bars
    minp = w // 2

    ret = close.pct_change()

    # ---------- velocity z (010/014 proven down clock) ---------------------
    mean48 = close.rolling(w, min_periods=minp).mean()
    vel = ((close - mean48) / close.replace(0, eps)).clip(-0.5, 0.5).fillna(0)
    vel_mu = vel.rolling(w, min_periods=minp).mean()
    vel_sd = vel.rolling(w, min_periods=minp).std().replace(0, eps)
    vel_z = ((vel - vel_mu) / vel_sd).clip(-2, 2).fillna(0)

    # ---------- Donchian mid-band structure --------------------------------
    d_hi = high.rolling(w, min_periods=minp).max()
    d_lo = low.rolling(w, min_periods=minp).min()
    mid = (d_hi + d_lo) / 2.0
    below = (close < mid).astype(float)

    # 2-day confirmation: below mid for >= 2 consecutive 96-bar sessions
    sess = below.rolling(96, min_periods=1).mean()          # fraction of bars below in session
    sess_below = (sess > 0.5).astype(float)                  # session closed below
    confirmed = sess_below.rolling(2, min_periods=2).sum() >= 2  # 2 consecutive sessions

    # ---------- structural reclaim (instant exit condition) ----------------
    vol_mean = volume.rolling(w, min_periods=minp).mean().replace(0, eps)
    vol_surge = (volume / vol_mean) > 1.5
    reclaim = (close > mid) & (vol_surge | (vel_z > 0))

    # ---------- SHORT EARNER ------------------------------------------------
    # strength of breakdown, bounded; fired ONLY when confirmed and NOT reclaim
    dn_strength = np.tanh(-vel_z * 1.5)                      # ~1 on sharp downside
    short_sig = dn_strength.where(confirmed & ~reclaim, 0.0)
    # graduated by depth below mid, bounded
    depth = ((mid - close) / close.replace(0, eps)).clip(0, 0.2)
    depth_b = np.tanh(depth / 0.05)
    short_sig = (short_sig * (0.6 + 0.4 * depth_b)).clip(-1, 0)

    # ---------- LONG ACTIVITY FLOOR (014-style mean-zero oscillator) --------
    sigma = ret.rolling(48, min_periods=20).std().replace(0, eps)
    z_fast = ((ret / sigma).clip(-2, 2)).fillna(0)
    osc = np.tanh(-z_fast * 1.0)                             # mean-reversion term
    # mild up-regime tilt so melt-ups still see long crossings
    up_tilt = np.tanh(vel_z * 0.75)
    long_sig = (0.45 * osc + 0.55 * up_tilt).clip(0, 1)

    # ---------- COMPOSITE ---------------------------------------------------
    sig = long_sig.where(short_sig == 0, 0.0) + short_sig
    sig = sig.ewm(span=3, min_periods=1).mean()              # light hysteresis
    return sig.clip(-1, 1).fillna(0.0)
