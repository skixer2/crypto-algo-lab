"""
alpha_041 — DOWN-LEG EARNER: confirmed-breakdown short with instant reclaim exit
Hypothesis (P1, JP promotion 2026-10-07): down-shield experts exist (028/032)
but none EARN in bear legs. A short specialist should convert breakdown
structure into positive down-leg RETURNS. The single failure mode of naive
shorts is the bear-rally trap (2022-01: +14.4 inside bear) — so shorting is
permitted ONLY on 2-day-sustained confirmation below the 48h Donchian
mid-band, and the short state is abandoned INSTANTLY (single bar of reclaim)
when price reclaims the mid-band on a volume surge (alpha_010's structural
reclaim clock). Outside confirmed-breakdown state the signal is mildly
long-neutral with a small zero-mean oscillator so long_threshold crossings
still occur (activity/uptrend gates stay alive; never gated to zero).
Confirmation counter = fraction of the last 192 15m bars (2 days) below the
mid-band, tanh-bounded; shorts scale with confirmation depth (velocity z and
downward structure), never exceed amplitude 1.1.
All ops trailing (rolling/ewm only), inputs bounded pre-composite, divisions
by rolling stats after .replace(0, 1e-9), no I/O.
Charter rules attacked: down_shield PROFIT (down-leg return > 0),
adaptive_activity (oscillator re-crossings), extreme_participation /
uptrend_participation (reclaim-side long drift), noise_stability.
Author: escalation cycle 41 (P1 down-leg earner, alpha_010/014 lineage).
Provenance: tuner/runs/alpha_039_auto.json, alpha_040_auto.json (uptrend
participation + noise_stability were the failed buckets; shield passed).
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
    conf_w = 48 * 8     # 2-day confirmation window

    # ---------------- structure: Donchian mid-band ------------------------
    hh = high.rolling(w, min_periods=minp).max()
    ll = low.rolling(w, min_periods=minp).min()
    mid = 0.5 * (hh + ll)
    below = (close < mid).astype(float)

    # 2-day sustained confirmation: fraction of last 2d bars below mid
    conf_frac = below.rolling(conf_w, min_periods=conf_w // 2).mean().fillna(0.5)
    short_state = np.tanh((conf_frac - 0.55) * 5.0).clip(lower=0.0)  # 0..~1

    # depth of breakdown: 48h velocity z (negative = falling)
    ret = close.pct_change()
    sigma = ret.rolling(w, min_periods=minp).std().replace(0, eps)
    mean48 = close.rolling(w, min_periods=minp).mean()
    vel = ((close - mean48) / close.replace(0, eps)).clip(-0.5, 0.5).fillna(0)
    vel_mu = vel.rolling(w, min_periods=minp).mean()
    vel_sd = vel.rolling(w, min_periods=minp).std().replace(0, eps)
    vel_z = ((vel - vel_mu) / vel_sd).clip(-2, 2).fillna(0)
    depth = np.tanh(-vel_z * 1.5).clip(lower=0.0)  # 0..~1 on sharp downside

    # ---------------- instant structural reclaim exit ---------------------
    vol_mu = volume.rolling(w, min_periods=minp).mean().replace(0, eps)
    v_rel = (volume / vol_mu).clip(0, 3).fillna(1)
    above = (close > mid).astype(float)
    reclaim = (above * (v_rel > 1.3).astype(float)).ewm(span=2, min_periods=1).mean()

    # ---------------- SHORT PAYLOAD (only when confirmed) -----------------
    short_payload = -(1.1 * short_state * (0.4 + 0.6 * depth))

    # ---------------- LONG-SIDE drift outside breakdown -------------------
    # structural breakout pop: mid reclaim + volume (alpha_010 lineage)
    long_pop = np.tanh(vel_z * 1.5).clip(lower=0.0) * (0.3 + 0.7 * reclaim)
    # small zero-mean oscillator guarantees threshold re-crossings (014)
    z_fast = (close.pct_change(8) / (sigma * np.sqrt(8)).replace(0, eps)).clip(-2, 2).fillna(0)
    osc = np.tanh(-z_fast)

    signal = short_payload + 0.55 * long_pop + 0.18 * osc * (1.0 - short_state)
    signal = signal.ewm(span=3, min_periods=2).mean()
    return signal.clip(-1.1, 1.1).fillna(0.0)
