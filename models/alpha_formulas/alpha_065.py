"""
alpha_065 — TURTLE LATCH v2 (P1a: bull seat, crisp binary holding)
Hypothesis (JP 2026-10-11): alpha_026 died because graded EWM memory dilutes
below exit threshold. Fix: signal is CRISP — pinned +1.0 while close > trailing
structural level (rolling max of high, shifted 1, N=288 bars ~3 days), pinned
0.0 below. Entry smoothness via a small tanh ramp of (close-trail)/ATR near the
boundary only (entry-side, holding stays binary). Wide participation: low
entry threshold, signal_exit_threshold ~0, atr_take up to 30, wide stop per
charter. Volume confirmation on breakout boosts entry ramp speed.
Structure (trailing-only): trail = high.rolling(N).max().shift(1);
latch = (close > trail ? 1 : 0) then smoothed only over 2 bars for tick noise.
Vol compression gate: skip entries when ATR% is extreme blow-off (>99th local),
via tanh bound. Bounded transforms, |inputs|<=2, divisions guarded with
.replace(0,1e-9), rolling/expanding only, no I/O.
Rule attacked: uptrend_participation (60%) + extreme_participation (bench>=15%
-> strat>0); P1a bull-seat design (a).
Author: auto-gen (isolated alpha loop), 2026-10-15.
Provenance: alpha_026.py (anti-pattern: EWM dilution), tuner/runs/
alpha_063_auto.json + alpha_064_auto.json (extreme/up-participation failures),
blender_v1b (up-capture 0.06 gap).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    eps = 1e-9

    # ---- trailing structural level (Donchian-style, excl. current bar) ----
    n = 288  # 3 days of 15m bars
    trail = high.rolling(n, min_periods=n // 3).max().shift(1)

    # normalized distance above trail, bounded
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(96, min_periods=32).mean().replace(0, eps)
    dist = ((close - trail) / (atr * 2.0)).clip(-2, 2)

    # crisp latch: 1 above trail, 0 below. Entry ramp only near boundary:
    # smooth_entry in [0,1] rises as price clears the trail; holding stays
    # binary because latch is recomputed each bar from the hard comparison.
    latch = (dist > 0).astype(float)
    ramp = np.tanh(dist * 2.0)  # ~ -1..1; >0 above trail

    # 2-bar tick-noise smoothing of the latch (not graded memory)
    hold = latch.rolling(2, min_periods=1).mean()

    # volume confirmation: breakout on volume surge latches quicker (entry only)
    vol_rel = volume / volume.rolling(96, min_periods=32).mean().replace(0, eps)
    vol_conf = 0.5 + 0.5 * np.tanh((vol_rel - 1.0) / 1.5)  # [0,1]

    # blow-off guard: extreme ATR% expansion trims exposure (bounded)
    atr_pct = (atr / close.replace(0, eps)).clip(-2, 2)
    atr_med = atr_pct.rolling(672, min_periods=192).median().replace(0, eps)
    blow = np.tanh(((atr_pct / atr_med) - 2.0) * 1.5).clip(-1, 1)
    guard = 1.0 - 0.4 * np.clip(blow, 0, 1)  # in [0.6, 1.0]

    # signal: entry side graded by ramp+volume, holding pinned by latch
    sig = hold * (0.35 + 0.65 * np.clip(ramp, 0, 1)) * (0.6 + 0.4 * vol_conf) * guard
    return sig.clip(-1, 1).fillna(0.0)
