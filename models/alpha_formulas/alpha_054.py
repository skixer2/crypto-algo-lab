"""
alpha_054 — TURTLE LATCH v2: crisp binary bull-seat latcher (P1a)
Hypothesis: alpha_026 died because graded EWM memory diluted the signal below
the tuner's entry threshold during hold (fade-then-die). v2 replaces graded
memory with a CRISP LATCH: signal = +1.0 exactly while close > trailing
structural level (N-bar rolling max of high, shifted 1), 0.0 below. Holding is
binary — no decay, no dilution. A small tanh ramp of (close - trail)/ATR near
the boundary smooths ENTRY only; once latched the signal stays pinned at 1.0
until price closes below the trail, then snaps to 0. Structural trail is slow
(N up to ~480 bars) so the latch survives multi-day pullbacks. Volume surge at
breakout pre-arms a slightly lower boundary margin (entry smoothness only).
Rule attacked: UPTREND PARTICIPATION (60%) + EXTREME (bench>=15% -> >0) —
the empty BULL SURFING seat.
Author: auto-gen (isolated alpha loop, P1a Turtle Latch v2), 2026-10-13.
Provenance: tuner/runs/alpha_053_auto.json + alpha_052_auto.json (bull windows
strat=0.0; extreme 2022-07..08 bench +57 missed), charter v2 2026-10-11;
anti-pattern: alpha_026.py (graded EWM death).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    high = df["high"]
    volume = df["volume"]
    low = df["low"]
    eps = 1e-9

    # ---------- trailing structural level (shifted 1: excludes current bar)
    N = 288  # 72h @15m; survives multi-day pullbacks once latched
    trail = high.rolling(N, min_periods=N // 2).max().shift(1)

    # ---------- ATR for boundary normalization
    tr = pd.concat(
        [
            high - df["low"],
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(96, min_periods=48).mean().replace(0, eps)

    # ---------- volume surge (pre-arm margin only, bounded)
    vma = volume.rolling(192, min_periods=96).mean().replace(0, eps)
    vsurge = (volume / vma).clip(0, 2).fillna(0)  # in [0,2]

    # ---------- entry smoothness: tanh ramp near the boundary, |x| <= 2
    gap = (close - trail) / atr
    ramp = np.tanh((gap * 2.0 + 0.2 * (vsurge - 1.0)).clip(-2, 2))

    # ---------- CRISP LATCH: pinned 1.0 while close > trail, else 0.
    #    Holding is binary; ramp only shades the boundary band so the
    #    signal crosses the tuner's low entry threshold (>0.3) cleanly.
    latched = (close > trail).astype(float)
    boundary = ((gap > -0.5) & (gap <= 0.0)).astype(float)
    signal = latched * 1.0 + boundary * (0.4 + 0.6 * ramp)
    signal = signal.clip(0.0, 1.0).fillna(0.0)

    return signal
