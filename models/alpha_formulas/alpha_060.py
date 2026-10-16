"""
alpha_060 — RECOVERY-START DETECTOR (V-bottom buyer, P1 bull seat)
Hypothesis (charter v2 P1b): a distinct bull skill vs trend-riding — buy the
FIRST structural reclaim after a deep drawdown. Three trailing conditions:
(1) DEEP DRAWDOWN: close is >12% below the rolling 2880-bar (30d) high of
    close at some point in the recent past (measured via distance of the
    rolling min of close vs that high — the dip happened recently);
(2) FIRST RECLAIM: close crosses above the short Donchian mid (192-bar
    high/low midpoint, 48h) — the first structural higher ground;
(3) VOL COMPRESSION: post-spike fast/slow true-range ratio falling below 1.2
    (panic selling exhausted).
Signal is LONG-ONLY and in [0, 1.2]: tanh-bounded amplitude scaled by reclaim
strength; exactly 0 when no dip-context exists. Fix of alpha_059: no
expanding-max permanent latch, no negative ramp shorts — negatives in
downtrends got the +57% recovery window shorted to -42.7%.
Trailing ops only (rolling/shift(1)); tanh-bounded |inputs|<=2; guarded
divisions (.replace(0,1e-9)); no I/O.
Charter rules attacked: extreme_participation (2022-07-15 +57% recovery),
uptrend_participation (2023-10-29 +14%), medium_term_edge, consistency,
adaptive_activity (reclaims re-arm on every new dip-reclaim cycle).
Author: auto-gen (isolated alpha loop), 2026-10-14.
Provenance: tuner/runs/alpha_059_auto.json failed gates (extreme/uptrend
participation from negative-ramp shorts + permanent latch); alpha_056
(V-bottom up-capture +1.02 lesson); alpha_026 (no graded memory).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low = df["close"], df["high"], df["low"]
    eps = 1e-9

    # ---------- trailing structure ----------------------------------------
    n_high = 2880          # 30d rolling high window (15m bars)
    n_mid = 192            # 48h Donchian mid
    n_atr = 96

    roll_high = close.rolling(n_high, min_periods=n_high // 2).max().shift(1)
    dd = (roll_high - close) / roll_high.replace(0, eps)   # drawdown depth [0..~1]

    # dip happened recently: rolling min of close still >=12% below the high
    dip_recent = (
        close.rolling(960, min_periods=240).min().shift(1) / roll_high.replace(0, eps)
    )
    deep_dip = (dip_recent < 0.88).astype(float)

    # ---------- first structural reclaim -----------------------------------
    mid_hi = high.rolling(n_mid, min_periods=n_mid // 2).max().shift(1)
    mid_lo = low.rolling(n_mid, min_periods=n_mid // 2).min().shift(1)
    mid = (mid_hi + mid_lo) / 2.0
    reclaim = (close > mid).astype(float)

    # strength of reclaim, bounded
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr = tr.rolling(n_atr, min_periods=n_atr // 2).mean().replace(0, eps)
    strength = ((close - mid) / atr.replace(0, eps)).clip(-2.0, 2.0).fillna(0.0)
    strength = np.tanh(strength / 0.8)

    # ---------- vol compression: fast TR vs slow TR, falling ---------------
    tr_fast = tr.rolling(16, min_periods=8).mean().replace(0, eps)
    tr_slow = tr.rolling(192, min_periods=48).mean().replace(0, eps)
    ratio = (tr_fast / tr_slow).clip(0.0, 2.0).fillna(1.0)
    compressed = (ratio < 1.2).astype(float)

    # ---------- composite: long-only, gated by dip + reclaim ----------------
    gate = deep_dip * reclaim
    sig = gate * (0.55 + 0.45 * strength) * (0.75 + 0.25 * compressed)
    sig = sig.clip(0.0, 1.2).fillna(0.0)

    # exit context: once close is back within 5% of the 30d high, the recovery
    # trade is done (hand back to trend seat) — trailing-only condition.
    near_top = (dd < 0.05).astype(float)
    sig = sig.where(near_top == 0, 0.0)

    return sig
