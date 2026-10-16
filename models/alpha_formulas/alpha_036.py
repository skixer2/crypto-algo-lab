"""
alpha_036 — CONFIRMED-BREAKDOWN SHORT SPECIALIST (down-leg EARNER, P1)
Hypothesis: alpha_014 proved symmetric re-crossing generates entries in
down windows, but its mean-reversion oscillator half drags the signal back
to long too early, so down-legs are shielded yet never EARN (alpha_035:
down_shield passed +10.5/+14.3 but medium_term_edge/consistency failed).
JP's 2026-10-07 promotion demands positive down-leg RETURNS from a short
specialist. Design:
  SHORT ENGINE (the earner): short signal issued ONLY on a 2-bar CONFIRMED
  breakdown — close below the 48h Donchian mid for 2 consecutive bars AND
  fast velocity z < 0 (sustained, not a one-bar wick). Signal rides the
  regime floor (-0.9) while price stays below the mid-band.
  INSTANT EXIT: the moment price reclaims the mid-band (structural reclaim,
  single bar close above), the short component collapses to 0 — no fading
  of reclaim conditions. This engineers around the bear-rally trap
  (2022-01 +14.4%): bounces that reclaim structure kill the short fast;
  bounces that fail (still below mid) keep us short.
  LONG RESIDUAL (participation, not the point): small tanh trend core
  (alpha_008 graded core, amplitude 0.45) keeps melt-up/uptrend windows
  alive so we never go fully dark; it is dwarfed by the short engine in
  breakdowns. Anti-trap gate: during reclaim bars the long core is halved
  (reclaim = unconfirmed, wait for Donchian-mid hold).
All transforms bounded (tanh / clip +-2) BEFORE compositing; rolling stats
replaced(0,1e-9) before division; trailing ops only.
Charter rules attacked: down_shield + down-leg PROFIT (P1 promotion),
medium_term_edge, adaptive_activity (short engine re-triggers each
breakdown cycle), noise_stability (2-bar confirmation).
Author: alpha-generation-loop cycle 2026-10-08 (P1 down-leg earner).
Provenance: tuner/runs/alpha_035_auto.json (down_shield pass, edge fail);
recipes alpha_010.py, alpha_014.py; alpha_032 (entry willingness).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]
    eps = 1e-9

    w = 48 * 4  # 48h of 15m bars
    minp = w // 2

    ret = close.pct_change()
    vol = ret.rolling(w, min_periods=minp).std().replace(0, eps)

    # ---------- SHORT ENGINE: 2-bar confirmed Donchian-mid breakdown -------
    don_mid = high.rolling(w, min_periods=minp).max().add(
        low.rolling(w, min_periods=minp).min()
    ) / 2.0

    below = (close < don_mid).astype(float)
    confirm = below.rolling(2, min_periods=2).sum() >= 2  # 2 consecutive bars
    confirm = confirm.fillna(False)

    # sustained velocity: fast 8h velocity z-score must be negative
    vw = 32
    vel = ((close - close.rolling(vw, min_periods=vw // 2).mean())
           / close.replace(0, eps)).clip(-0.2, 0.2).fillna(0)
    vel_mu = vel.rolling(w, min_periods=minp).mean()
    vel_sd = vel.rolling(w, min_periods=minp).std().replace(0, eps)
    vel_z = ((vel - vel_mu) / vel_sd).clip(-2, 2).fillna(0)

    # reclaim: close back above mid-band -> short dies INSTANTLY
    reclaim = (close > don_mid)

    short_engine = np.where(confirm & (vel_z < 0), -0.9, 0.0)
    short_engine = np.where(reclaim, 0.0, short_engine)
    short_engine = pd.Series(short_engine, index=close.index)

    # volume confirmation bonus: breakdown on volume surge rides harder
    v_mu = volume.rolling(w, min_periods=minp).mean().replace(0, eps)
    v_z = ((volume - v_mu) / v_mu.replace(0, eps)).clip(-2, 2).fillna(0)
    short_engine = short_engine * (1.0 + 0.15 * np.tanh(v_z))

    # ---------- LONG RESIDUAL: graded trend core (alpha_008/010 lineage) ---
    z = (ret / vol).clip(-2, 2).fillna(0)
    trend = close.rolling(96, min_periods=48).mean() / close.replace(0, eps) - 1.0
    trend = trend.clip(-0.05, 0.05)
    rng = (high - low).rolling(w, min_periods=minp).mean() / close.replace(0, eps)
    rng = rng.replace(0, eps).clip(0, 0.2)
    core = np.tanh(4.0 * trend / rng) + 0.5 * z
    core = core.clip(-1.5, 1.5).fillna(0)

    # anti-trap: during unconfirmed reclaim bars, halve the long core
    long_resid = np.where(reclaim & ~confirm, 0.5 * core, core)
    long_resid = pd.Series(long_resid, index=close.index)

    signal = 0.45 * long_resid + short_engine

    # light smoother removes bar-noise, fast enough to keep instant exits
    signal = signal.ewm(span=3, min_periods=1).mean()
    return signal.clip(-2, 2).fillna(0)
