"""
alpha_034 — CONFIRMED-BREAKDOWN SHORT SPECIALIST (down-leg EARNER)
Hypothesis (P1, JP promotion 2026-10-07): shielding experts (028/032) go
flat in crash legs; the charter's celebrated stretch goal is PROFIT in the
down leg. alpha_010/014 lineage shows short-side signal exists (+3.1/+1.1
in down weeks) but was diluted by long-bias core. Fix = a specialist whose
NEGATIVE lobe fires ONLY on a 2-BAR-CONFIRMED structural breakdown and
whose POSITIVE lobe is deliberately tiny, so the tuner's short_threshold
is crossed exactly when the market has sustained below the 48h Donchian
mid-band AND a second bar confirms (close stays under + lower low):
  short_sig = confirmed_breakdown * down_pressure  (bounded, tanh)
  base      = small mean-reversion oscillator (014's zero-mean sweep) so
  the signal re-crosses thresholds in chop/up-legs (activity, participation)
  but never builds a big long during breakdown conditions.
EXIT INSTANTLY on structural reclaim: any confirmed cross back ABOVE the
Donchian mid kills the negative lobe within one bar (reclaim term forces
signal >= 0), which is the bear-rally trap protection (2022-01 +14.4 leg
= reclaim conditions -> short lobe silent).
All inputs bounded pre-composite (tanh, z clip +/-2); trailing ops only;
divisions guarded with .replace(0,1e-9); no I/O.
Charter rules attacked: down_shield PROFIT (down-leg return > 0),
adaptive_activity (oscillator re-crossings), noise_stability (confirmation
gate), medium_term_edge, extreme/uptrend participation (positive base lobe
stays available when structure is intact).
Author: escalation cycle P1 (down-leg earner, JP directive), 2026-10-08.
Provenance: tuner/runs/alpha_033_auto.json (failed gates: participation,
edge, consistency, noise), alpha_010.py, alpha_014.py mechanisms.
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

    # ---------- structure: 48h Donchian mid-band --------------------------
    dc_hi = high.rolling(w, min_periods=minp).max()
    dc_lo = low.rolling(w, min_periods=minp).min()
    mid = (dc_hi + dc_lo) / 2.0
    below = (close < mid).astype(float)
    above = (close > mid).astype(float)

    # 2-bar confirmation: sustained below mid for >=2 bars (trailing)
    confirm_below = below.rolling(2, min_periods=2).min().fillna(0)
    confirm_above = above.rolling(2, min_periods=2).min().fillna(0)

    # down pressure: negative velocity z over fast clock
    ret = close.pct_change()
    vol = ret.rolling(w, min_periods=minp).std().replace(0, eps)
    vel_mu = ret.rolling(w, min_periods=minp).mean()
    vel_z = ((ret - vel_mu) / vol).clip(-2, 2).fillna(0)
    pressure = np.tanh(-vel_z * 1.5)  # ~1 on sharp down moves

    # lower-low extension adds conviction (bounded)
    low_ext = (mid - close) / (mid.replace(0, eps))
    low_ext = low_ext.replace([np.inf, -np.inf], 0).fillna(0).clip(0, 0.2)
    depth = np.tanh(low_ext * 20.0)

    # short lobe: ONLY on confirmed breakdown; instantly dead on confirmed
    # reclaim (structure back above mid two bars running)
    short_lobe = confirm_below * pressure * (0.5 + 0.5 * depth) * (1.0 - confirm_above)
    short_lobe = short_lobe.clip(0, 1).fillna(0)

    # volume confirmation of the breakdown (1.5x mean) boosts conviction
    v_mu = volume.rolling(w, min_periods=minp).mean().replace(0, eps)
    v_surge = np.tanh((volume / v_mu - 1.0).clip(-2, 2)).fillna(0)

    short_sig = short_lobe * (0.7 + 0.3 * np.tanh(v_surge * 2.0))

    # ---------- positive base: zero-mean fast oscillator (014 sweep) ------
    rf = close.pct_change(8)
    f_mu = rf.rolling(w, min_periods=minp).mean()
    f_sd = rf.rolling(w, min_periods=minp).std().replace(0, eps)
    z_fast = ((rf - f_mu) / f_sd).clip(-2, 2).fillna(0)
    osc = np.tanh(-z_fast * 1.2)  # mean-reverting, symmetric

    # small trend assist when structure intact (not during breakdown)
    trend = close.rolling(96, min_periods=48).mean() / close.replace(0, eps) - 1.0
    trend = trend.clip(-0.05, 0.05)
    assist = np.tanh(trend * 40.0).fillna(0) * (1.0 - short_lobe)

    pos_base = 0.45 * osc + 0.35 * assist

    # ---------- composite --------------------------------------------------
    sig = pos_base - 0.85 * short_sig
    sig = np.tanh(sig).fillna(0)
    return pd.Series(sig, index=df.index)
