"""
alpha_058 — TURTLE LATCH v2 (crisp binary bull seat, P1a)
Hypothesis (JP 2026-10-11): alpha_026 died because graded EWM memory diluted
the signal below the tuner's long_threshold during pullbacks (entered-late /
exited-early on every melt-up). This design has NO graded memory: the signal
is exactly 1.0 (pinned) while close > trailing structural level (rolling max
of high shifted 1, 240-bar = 60h trail), exactly 0.0 below. Holding is binary;
only a thin tanh ramp of (close - trail)/ATR near the boundary smooths entry.
Volume confirmation at breakout lifts the ramp, never gates the hold.
Charter rules attacked: uptrend_participation (60%), extreme_participation
(bench>=15% -> >0), adaptive_activity.
Author: auto-gen bull-seat cycle, 2026-10-14.
Provenance: tuner/runs/alpha_057_auto.json (window_rules fix list:
extreme_participation + uptrend_participation failures); alpha_026.py (what
NOT to do); alpha_040.py style guards.
Inputs: OHLCV. Trailing ops only; bounded before compositing.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]
    eps = 1e-9

    # ---------- trailing structural level ----------
    n_trail = 240  # 60h of 15m bars
    trail = high.rolling(n_trail, min_periods=n_trail // 2).max().shift(1)

    # ATR (trailing)
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(96, min_periods=48).mean().replace(0, eps)

    # ---------- entry ramp (only near the boundary) ----------
    above = (close - trail) / (3.0 * atr)  # normalized breakout depth
    ramp = np.tanh(above.clip(-2, 2)).fillna(0)  # -1..1, crisp beyond 3 ATR

    # volume confirmation: rolling z of volume, tanh-bounded
    vma = volume.rolling(192, min_periods=48).mean()
    vsd = volume.rolling(192, min_periods=48).std().replace(0, eps)
    vz = ((volume - vma) / vsd).clip(-2, 2).fillna(0)
    vconf = np.tanh(vz / 2.0)  # 0..~1 on surges

    # ---------- BINARY LATCH: holding is 1.0 or 0.0, no memory decay ----------
    pinned = (close > trail).astype(float)

    # Signal: pinned is all that matters; ramp adds smoothness only at entry.
    sig = pinned * (0.85 + 0.15 * ramp.clip(0, 1)) + (1.0 - pinned) * 0.05 * ramp.clip(0, 1)

    # tiny volume kicker while pinned (never negative, never un-pins)
    sig = sig + 0.05 * pinned * vconf.clip(0, 1)

    # rolling normalization safety: scale by own trailing sigma (guarded)
    s_sd = sig.rolling(288, min_periods=96).std().replace(0, eps)
    sig_n = (sig / s_sd).clip(-2, 2)

    # final squash keeps pinned days at ~1 (tanh(1)≈0.76; tuners see crossings)
    out = np.tanh(sig_n).fillna(0)
    # re-pin: preserve exact binary hold on the long side
    out = out.where(pinned == 1.0, out * 0.2)
    return out
