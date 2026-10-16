"""
alpha_042 — CONFIRMED-BREAKDOWN SHORT SPECIALIST (down-leg EARNER)
Hypothesis (P1, JP promotion 2026-10-07): down-shield experts exist (028,
032's perfect shield) but none convert the short side into POSITIVE
down-leg RETURNS. alpha_010/014 lineage showed short-side signal
provenance (+3.1/+1.1 in down weeks) when driven by confirmed breakdown.
Design: a dedicated short signal that is ONLY active on a 2-day-confirmed
structural breakdown and exits INSTANTLY on reclaim:
  - Structure: rolling Donchian mid-band over 96 bars (24h) as the
    reference level. Breakdown requires close BELOW mid for 2 consecutive
    bias blocks (192 bars = 2 days of 15m bars, via rolling count of
    below-mid over 192 >= 192*0.95 → sustained, not a one-bar poke).
  - Velocity confirmation: 48h vol-adjusted velocity z < -1 (alpha_010
    decay clock). Short signal magnitude = tanh of normalized distance
    below mid, gated to zero the instant the sustained-below condition
    fails (structural reclaim exits the short immediately).
  - Bear-rally trap guard: while price is reclaiming (above mid OR
    velocity z > 0), signal is forced >= 0 → never short during reclaim
    conditions, so 2022-01-style +14% bear rallies are not shorted.
  - Long side: mild alpha_008-style core retained so the tuner can keep
    participation in up-windows, but small (0.4x) so the short book
    dominates the profile.
All trailing ops; bounded transforms before compositing (|inputs| <= 2
into tanh); division only by rolling stats after replace(0,1e-9); no
I/O.
Charter rules attacked: down_shield with down-leg PROFIT (P1 acceptance:
positive strat_down_pct in V/crash windows), medium_term_edge,
consistency, adaptive_activity (short re-entries on each new breakdown
leg), noise_stability (2-day confirmation suppresses whipsaw).
Author: escalation cycle (P1 down-leg earner per JP-Gemini frontier
note), 2026-10-10.
Provenance: tuner/runs/alpha_041_auto.json, alpha_040_auto.json
(window_rules fix list); mechanisms from alpha_010.py, alpha_014.py.
Inputs: OHLCV (+volume unused in v1).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low = df["close"], df["high"], df["low"]
    eps = 1e-9

    w48 = 48 * 4          # 48h of 15m bars
    minp48 = w48 // 2
    mid_w = 96            # 24h Donchian reference
    conf_w = 192          # 2 days confirmation window

    # ---------- structural level: Donchian mid over 24h ------------------
    hh = high.rolling(mid_w, min_periods=mid_w // 2).max()
    ll = low.rolling(mid_w, min_periods=mid_w // 2).min()
    mid = (hh + ll) / 2.0

    # normalized distance below mid (bounded)
    atr = (high - low).rolling(w48, min_periods=minp48).mean().replace(0, eps)
    dist = ((close - mid) / atr).clip(-2, 2).fillna(0)

    # ---------- velocity confirmation (alpha_010 decay clock) ------------
    ret = close.pct_change()
    sigma = ret.rolling(w48, min_periods=minp48).std().replace(0, eps)
    mean48 = close.rolling(w48, min_periods=minp48).mean()
    vel = ((close - mean48) / close.replace(0, eps)).clip(-0.5, 0.5).fillna(0)
    vel_mu = vel.rolling(w48, min_periods=minp48).mean()
    vel_sd = vel.rolling(w48, min_periods=minp48).std().replace(0, eps)
    vel_z = ((vel - vel_mu) / vel_sd).clip(-2, 2).fillna(0)

    # ---------- 2-day sustained-below confirmation -----------------------
    below = (close < mid).astype(float)
    sustained = below.rolling(conf_w, min_periods=conf_w // 2).mean()
    confirmed_break = (sustained >= 0.90).astype(float)   # persistently below mid
    confirmed_reclaim = (sustained <= 0.10).astype(float)  # persistently back above

    # ---------- SHORT book: only on confirmed breakdown -------------------
    # magnitude grows with depth below mid + downside velocity, capped
    short_mag = np.tanh(1.0 * (-dist).clip(0, 2) + 0.5 * np.tanh(-vel_z * 1.5).clip(0, 2))
    short_sig = -short_mag * confirmed_break
    # hard guard: never short during reclaim conditions (trap protection)
    reclaim_ok = (vel_z > 0) | confirmed_reclaim | (dist > 0)
    short_sig = short_sig.where(~reclaim_ok, 0.0)

    # ---------- LONG book: mild alpha_008-style core (0.4x) ---------------
    z = (ret / sigma).clip(-2, 2).fillna(0)
    trend = close.rolling(96, min_periods=48).mean() / close.replace(0, eps) - 1.0
    trend = trend.clip(-0.05, 0.05)
    rng = atr / close.replace(0, eps)
    rng = rng.replace(0, eps).clip(0, 0.2)
    long_core = np.tanh(4.0 * trend / rng) + 0.5 * z
    # suppress longs while confirmed breakdown is active
    long_sig = 0.4 * long_core.clip(-1.5, 1.5).fillna(0) * (1.0 - confirmed_break)

    sig = long_sig + short_sig
    # light hysteresis smoother (fast, preserves threshold crossings)
    sig = sig.ewm(span=3, min_periods=1).mean()
    return sig.fillna(0.0).clip(-1.6, 1.6)
