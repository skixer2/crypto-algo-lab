"""
alpha_040 — CONFIRMED-BREAKDOWN SHORT SPECIALIST (P1 down-leg earner)
Hypothesis (JP promotion 2026-10-07): down-shield experts exist (028, 032's
perfect down-shield legs) but none EARNS in the down-leg. Recipe from the
alpha_010/014 lineage (proven +3.1/+1.1 short captures in down weeks):
short signal ONLY after a 2-STAGE CONFIRMED breakdown, exit instantly on
structural reclaim.
  Stage 1 (break): close below the rolling Donchian mid-band (96-bar, 24h)
  while velocity z is negative.
  Stage 2 (confirm): close still below that mid-band 96 bars (24h) LATER,
  i.e. a LAGGED self-check: breakdown_level = mid at t-96; short pressure
  engages only when close < mid AND close(t-96) < mid(t-96) — a sustained
  break, not a one-bar wick. Signal = -confirm_strength (tanh-bounded), so
  the tuner's short_threshold is crossed only under sustained breakdown.
  Reclaim: close crossing back above the mid-band plus volume surge flips
  the signal positive fast (014-style oscillator term guarantees crossings
  in the other direction), so the short is never held into bear-rally traps
  (2022-01 +14.4 inside bear): confirmation must re-arm from scratch.
  A mean-reversion oscillator (8-bar return z, 014-proven) rides on top so
  activity stays alive in up/chop windows (adaptive_activity, participation).
Bounded transforms before compositing; trailing ops only; rolling stats
replace(0,1e-9) before division; no I/O.
Charter rules attacked: down_shield + down-leg RETURN (P1 earner),
adaptive_activity (oscillator crossings), uptrend_participation (reclaim
unlock + osc longs), medium_term_edge/consistency.
Author: escalation cycle 11 (JP down-leg earner promotion), 2026-10-09.
Provenance: tuner/runs/alpha_039_auto.json, alpha_038_auto.json
(failed_gates); mechanisms inlined from alpha_010.py, alpha_014.py.
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]
    eps = 1e-9

    w = 48 * 4      # 48h of 15m bars
    mid_w = 96      # 24h Donchian mid window (confirmation lag length)
    minp = w // 2

    # ---------- Donchian mid + rolling vol -------------------------------
    upper = high.rolling(mid_w, min_periods=mid_w // 2).max()
    lower = low.rolling(mid_w, min_periods=mid_w // 2).min()
    don_mid = (upper + lower) / 2.0

    ret = close.pct_change()
    vol = ret.rolling(w, min_periods=minp).std().replace(0, eps)

    # velocity z (010 proven)
    mean48 = close.rolling(w, min_periods=minp).mean()
    vel = (close - mean48) / close.replace(0, eps)
    vel = vel.replace([np.inf, -np.inf], 0).fillna(0)
    vel_mu = vel.rolling(w, min_periods=minp).mean()
    vel_sd = vel.rolling(w, min_periods=minp).std().replace(0, eps)
    vel_z = ((vel - vel_mu) / vel_sd).clip(-2, 2).fillna(0)

    # ---------- STAGE 1: break below Donchian mid ------------------------
    below = (close < don_mid).astype(float)

    # ---------- STAGE 2: still broken one lag later (sustained) ----------
    below_lag = below.shift(mid_w).fillna(0.0)
    confirmed = below * below_lag * (vel_z < 0).astype(float)

    # confirm strength scales with depth below mid and downside velocity,
    # bounded; only nonzero under sustained breakdown -> short crossings
    depth = ((don_mid - close) / close.replace(0, eps)).clip(0, 0.1) / 0.1
    short_press = confirmed * np.tanh(2.0 * depth) * np.tanh(-0.75 * vel_z)

    # ---------- RECLAIM: instant exit / long unlock ----------------------
    vol_mu = volume.rolling(w, min_periods=minp).mean().replace(0, eps)
    vsurge = (volume / vol_mu).clip(0, 3.0)
    reclaim = (
        (close > don_mid).astype(float)
        * np.tanh(0.5 * (vsurge - 1.0)).clip(0, 1)
        * np.tanh(0.75 * vel_z).clip(0, 1)
    )

    # ---------- mean-reversion oscillator (014, activity by design) ------
    zf = (ret / vol).clip(-2, 2).fillna(0)
    osc = np.tanh(-1.0 * zf.rolling(8, min_periods=4).mean().fillna(0))

    # ---------- composite -------------------------------------------------
    signal = 0.55 * short_press - 0.45 * reclaim + 0.40 * osc
    signal = signal.ewm(span=3, min_periods=1).mean()
    return signal.clip(-1.5, 1.5).fillna(0)
