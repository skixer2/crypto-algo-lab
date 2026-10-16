"""
alpha_047 — short-leg breakdown earner v2 (reclaim-hard-kill fix)
Hypothesis: alpha_046 proved P1 (down-leg RETURNS: +11.3 on -28.6 leg,
+9.1 on -21.9, both down_shield gates PASS) but bled -42.5/-14.5 in
melt-up windows — its ewm-based reclaim memory let shorts survive the
turn. Fix = THREE hard instantaneous vetoes, zero memory lag:
 (1) RECLAIM KILL: close above the 1-day Donchian mid for even one bar
     multiplies the short by exactly 0 (no decay tail);
 (2) DAILY-TREND VETO: 1-day EMA(96 bars) rising vs 4h ago -> no short
     (melt-ups have rising daily EMA; bear legs do not);
 (3) depth requirement: short only below mid AND 4h-ema under 1d-ema,
     2-day confirmation persist >= 0.5 (unchanged core from 046).
Charter rules attacked: DOWN-SHIELD via down-leg returns (already proven
in 046) while removing extreme/uptrend bleed.
Author: auto-gen (isolated alpha loop), 2026-10-11, cycle 2.
Provenance: tuner/runs/alpha_046_auto.json (shield PASS, melt-up bleed).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]

    d = 96   # 1 day of 15m bars
    h4 = 16  # 4 hours

    # ---- structure: 1-day Donchian mid ----
    hh = high.rolling(d, min_periods=40).max().shift(1)
    ll = low.rolling(d, min_periods=40).min().shift(1)
    mid = 0.5 * (hh + ll)
    chan = (hh - ll).replace(0, 1e-9)
    depth = (mid - close) / chan  # >0 when below mid

    # ---- confirmation 1: below mid, 2-day persistence ----
    below = (depth > 0.02).astype(float)
    below_persist = below.ewm(span=2 * d, min_periods=10).mean()

    # ---- confirmation 2: 4h ema below 1d ema ----
    ema_f = close.ewm(span=h4, min_periods=6).mean()
    ema_s = close.ewm(span=d, min_periods=30).mean()
    atr = (
        np.maximum(
            high - low,
            np.maximum((high - close.shift(1)).abs(), (low - close.shift(1)).abs()),
        )
        .rolling(d, min_periods=30)
        .mean()
        .replace(0, 1e-9)
    )
    trend_down = np.tanh((ema_s - ema_f) / atr * 2.0).clip(lower=0.0)

    # ---- VETO 1: instant reclaim kill (no memory) ----
    # short dies the bar close re-crosses the mid
    reclaim_now = (close >= mid).astype(float)

    # ---- VETO 2: daily trend rising -> no shorts ----
    ema_s_prev = ema_s.shift(h4)  # 4h ago
    daily_up = (ema_s > ema_s_prev).astype(float)

    # ---- short core (unchanged 046 logic) ----
    conf = np.minimum(below_persist * 2.0, 1.0) * trend_down
    short = -1.5 * np.tanh(depth * 4.0) * conf

    # hard gates: any veto active -> exactly 0
    kill = np.maximum(reclaim_now, daily_up)
    sig = short * (1.0 - kill)

    return sig.clip(-1.5, 0.0).fillna(0.0)
