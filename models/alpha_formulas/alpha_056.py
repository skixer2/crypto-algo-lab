"""
alpha_056 — DONCHIAN-MID TURTLE LATCH + V-BOTTOM RECOVERY (dual bull seat).
Hypothesis: alpha_055's latch required close > rolling MAX OF HIGHS (192 bars):
an all-time-high breakout condition that armed only 6 times in 4.5y and scored
0.0 in the 2022-07 +57% melt-up (entered way too late). Fix (P1a): latch on the
DONCHIAN MID-BAND (upper+lower)/2 like the proven alpha_040 breakdown level —
close crosses mid far more often, giving ~40-80 latchings, while HOLDING stays
crisp binary (pin +1.0, no graded memory, no EWM dilution — the alpha_026 death).
Exit = close below the mid too (tight but trailing; whipsaw cost handled by the
tuner's thresholds). Second seat (P1b): V-BOTTOM RECOVERY — deep drawdown from
the 30d high (>15%) plus FIRST reclaim of the short Donchian mid plus fast-TR
compression (post-spike vol fading) fires a bounded long, targeting 2022-08-style
+62% recovery legs that pure breakout latches always miss. Composite = max of
both seats, clipped [0,1], never negative (down_shield-safe).
Quadrant attacked: P1 BULL SEAT — uptrend_participation + extreme_participation,
staying flat in bear legs.
Author: auto-gen (isolated alpha loop), 2026-10-13.
Provenance: tuner/runs/alpha_055_auto.json (6 entries, extreme strat 0.0),
alpha_026.py death post-mortem, alpha_040 mid-band recipe, charter v2 P1.
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    eps = 1e-9

    # ---------- shared structural + vol primitives -------------------------
    mid_w = 96  # 24h @15m (040-proven band length)
    upper = high.rolling(mid_w, min_periods=mid_w // 2).max()
    lower = low.rolling(mid_w, min_periods=mid_w // 2).min()
    don_mid = ((upper + lower) / 2.0).shift(1)  # shifted: no look-ahead

    tr = np.maximum(
        high - low,
        np.maximum((high - close.shift(1)).abs(), (close - close.shift(1)).abs()),
    )
    atr = tr.rolling(96, min_periods=24).mean().replace(0, eps)

    # ---------- SEAT 1: DONCHIAN-MID TURTLE LATCH (binary hold) ------------
    above = (close > don_mid).astype(float)
    # ratchet latch: last nonzero crossing event held forward (trailing only)
    events = above.replace(0, np.nan)
    latch = events.ffill().fillna(0.0).clip(0.0, 1.0)

    # entry smoothness: tanh ramp on distance above the level in ATR units
    edge = ((close - don_mid) / atr).clip(-2, 2).fillna(0)
    ramp = 0.5 + 0.5 * np.tanh(1.0 * edge)  # [0,1]

    # volume conviction on breakouts (legal: volume in df)
    vol_rel = (volume / volume.rolling(192, min_periods=48).mean().replace(0, eps)).clip(0, 3)
    vol_conf = 0.7 + 0.3 * np.tanh(vol_rel - 1.0)  # [0.4, 1.0]

    sig_trend = latch * ramp * vol_conf
    # crisp pin once well above the level (holding stays binary, no dilution)
    sig_trend = np.maximum(sig_trend, latch * (edge > 0.5).astype(float))

    # ---------- SEAT 2: V-BOTTOM RECOVERY DETECTOR -------------------------
    hi30 = high.rolling(96 * 30, min_periods=96 * 10).max()  # ~30d high
    drawdown = (close / hi30.replace(0, eps) - 1.0).clip(-0.5, 0.0).fillna(0)
    deep = np.tanh(drawdown / 0.15)  # <= -15% saturates to -1

    short_mid_w = 48  # 12h reclaim band
    s_up = high.rolling(short_mid_w, min_periods=short_mid_w // 2).max()
    s_lo = low.rolling(short_mid_w, min_periods=short_mid_w // 2).min()
    s_mid = ((s_up + s_lo) / 2.0).shift(1)
    reclaim = (close > s_mid).astype(float)

    # post-spike vol compression: fast TR ratio falling = capitulation fading
    tr_fast = tr.rolling(8, min_periods=4).mean()
    tr_slow = tr.rolling(96, min_periods=24).mean().replace(0, eps)
    tr_ratio = (tr_fast / tr_slow).replace([np.inf, -np.inf], 1.0).fillna(1.0)
    compress = np.tanh((1.2 - tr_ratio) / 0.5).clip(0, 1)  # falling ratio -> 1

    sig_v = deep.abs() * reclaim * compress  # in [0,1], only when deep is large
    sig_v = sig_v.fillna(0.0)

    # ---------- composite: max of the two bull seats -----------------------
    sig = np.maximum(sig_trend, 0.85 * sig_v)
    return sig.clip(0.0, 1.0).fillna(0.0)
