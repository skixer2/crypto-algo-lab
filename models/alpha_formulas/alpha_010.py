"""
alpha_010 — dual-speed asymmetric valve over the alpha_008 wide-stop core
Hypothesis: alpha_009 proved the regime valve (first down-window muted to
0.0, chop capture 3.889/3.889 preserved) but its 7-day slope clock was
2-3x too slow BOTH ways: still closed during the +31.33% melt-up window
(extreme_participation 0.0) and lagged the mute into the second drop
(fully long, -1.705 full absorption). THE MISSING PIECE IS THE CLOCK.
Fix = two asymmetric clocks instead of one slow one:
  DECAY side (fast): 48h vol-adjusted velocity baseline (close minus its
  48h rolling mean, normalized by 48h rolling std, tanh-bounded). When
  negative and accelerating down, valve shuts exposure to the 0.05 floor
  within ~48h of aggressive breakdown — no more week-late mutes.
  RECLAIM side (structural): breakout unlock — cross above the trailing
  48h Donchian mid-band (not the slow 7d slope) combined with a volume
  surge (volume > 1.5x its 48h rolling mean) opens the valve fast from
  the floor so vertical melt-ups are caught at inception.
Rolling stats only; alpha_008 graded wide-stop core kept as the engine
under the valve.
Charter rules attacked: extreme_participation (+31.3 missed), down_shield
(second drop -1.705), medium_term_edge/consistency (rolling valve keeps
exposure alive -> entries), uptrend_participation (core preserved).
Author: escalation cycle 4 (dual-speed asymmetric valve per alpha_009
next-idea / JP-Gemini frontier note), 2026-10-02.
Provenance: tuner/runs/alpha_009_auto.json.
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]

    w = 48 * 4  # 48 hours of 15m bars
    minp = w // 2

    # ---------- alpha_008 graded wide-stop core (engine under the valve) --
    ret = close.pct_change()
    vol = ret.rolling(w, min_periods=minp).std().replace(0, 1e-9)
    z = (ret / vol).clip(-2, 2)
    trend = close.rolling(96, min_periods=48).mean() / close.replace(0, 1e-9) - 1.0
    trend = trend.clip(-0.05, 0.05)
    rng = (high - low).rolling(w, min_periods=minp).mean() / close.replace(0, 1e-9)
    rng = rng.replace(0, 1e-9).clip(0, 0.2)
    # graded conviction: prefer upside drift, tolerate wide stops
    core = np.tanh(4.0 * trend / rng) + 0.5 * z.fillna(0)
    core = core.clip(-1.5, 1.5).fillna(0)

    # ---------- DECAY clock: fast 48h vol-adjusted velocity ---------------
    mean48 = close.rolling(w, min_periods=minp).mean()
    vel = (close - mean48) / vol * close.replace(0, 1e-9)  # ~ price units
    # normalize velocity by price then by its own rolling std
    vel = vel / close.replace(0, 1e-9)
    vel = vel.replace([np.inf, -np.inf], 0).fillna(0)
    vel_mu = vel.rolling(w, min_periods=minp).mean()
    vel_sd = vel.rolling(w, min_periods=minp).std().replace(0, 1e-9)
    vel_z = ((vel - vel_mu) / vel_sd).clip(-2, 2).fillna(0)
    breakdown = (0.5 - 0.5 * np.tanh(vel_z * 2.0))  # ~1 on sharp downside

    # ---------- RECLAIM clock: Donchian mid-band breakout + volume surge --
    hh = high.rolling(w, min_periods=minp).max()
    ll = low.rolling(w, min_periods=minp).min()
    mid = 0.5 * (hh + ll)
    above = (close > mid).astype(float)
    vol_mu = volume.rolling(w, min_periods=minp).mean().replace(0, 1e-9)
    v_surge = (volume / vol_mu > 1.5).astype(float)
    reclaim = above * v_surge

    # ---------- asymmetric valve ------------------------------------------
    # base scale follows fast velocity sign/magnitude (48h clock, not 7d)
    valve = 0.05 + 0.95 * (0.5 * (np.tanh(vel_z * 1.5) + 1.0))
    # decay side: sharp breakdown slams the valve toward the floor fast
    valve = valve * (1.0 - 0.95 * breakdown)
    # reclaim side: breakout + volume surge pops it straight open
    valve = valve.clip(lower=0.9 * reclaim)

    signal = core * valve
    return signal.clip(-2, 2).fillna(0)
