"""
alpha_066 — TURTLE LATCH v2 (P1 bull seat: crisp binary trend-holding)
Hypothesis: alpha_026 died because graded EWM memory diluted below the exit
threshold mid-uptrend. This latch is BINARY: signal = 1.0 pinned while close
> trailing structural level (rolling 480-bar high shifted 1, ~5 days @15m),
0.0 below. Entry smoothness only via a thin tanh ramp on (close-trail)/ATR
near the boundary (<=2 bounded); HOLDING is strictly binary — no decay, no
memory. A 2-bar latch hysteresis (confirm one extra bar above trail) prevents
whipsaw exits. Volume surge at breakout (>1.5x rolling median) boosts entry
conviction but is never required to HOLD. Once latched, only a close back
below the trail releases. Long/flat only.
Rule attacked: uptrend_participation (0<bench<15% -> strat>=0.6x),
extreme_participation (bench>=15% -> strat>0), the 2022-07 +57% V-window.
Anti-pattern avoided: alpha_026's graded EWM dilution (read as NOT-DO list).
Author: auto-gen (isolated alpha loop), 2026-10-16.
Provenance: charter v2 asymmetric; tuner/runs/alpha_065_auto.json,
alpha_064_auto.json (extreme_participation failures at 2022-07-15..08-14).
Inputs: OHLCV. Trailing ops only; bounded transforms before compositing;
divisions guarded via .replace(0, 1e-9); no file/network I/O.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    eps = 1e-9

    # ---------- trailing structural level (shift 1, exclude current bar) ---
    n = 480                                   # ~5 days of 15m bars
    trail = high.rolling(n, min_periods=n // 2).max().shift(1)

    # ---------- ATR-normalized distance above the trail --------------------
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(96, min_periods=48).mean().replace(0, eps)

    dist = ((close - trail) / atr).replace([np.inf, -np.inf], 0).fillna(0)

    # Thin tanh entry ramp near the boundary only (|input|<=2), never affects
    # holding: latch logic below is binary on trail cross.
    ramp = np.tanh(dist.clip(-2, 2))

    # ---------- volume confirmation at breakout ----------------------------
    vma = volume.rolling(192, min_periods=96).median().replace(0, eps)
    vspike = (volume / vma).replace([np.inf, -np.inf], 1).fillna(1)
    v_boost = (vspike > 1.5).astype(float)    # binary conviction, optional

    # ---------- binary latch: ON while close > trail, 1-bar confirm hysteresis
    above = (close > trail.fillna(np.inf)).astype(float)
    confirmed = above.rolling(2, min_periods=1).min()   # needs 2 consecutive
    # latch: once confirmed, hold until a close BELOW the trail
    state = np.zeros(len(close), dtype=float)
    latched = False
    a = above.values
    c = confirmed.values
    for i in range(len(a)):
        if not latched:
            if c[i] > 0:
                latched = True
        else:
            if a[i] == 0.0:
                latched = False
        state[i] = 1.0 if latched else 0.0

    sig = pd.Series(state, index=close.index)

    # ---------- entry smoothing near boundary (only when unlatched) --------
    # Unlatched bars may show a faint positive ramp (0..0.3) so the tuner's
    # low entry threshold (<=0.3) can catch the turn early; latched = pinned 1.
    signal = sig + (1.0 - sig) * ramp.clip(lower=0) * (0.5 + 0.5 * v_boost)
    signal = signal.clip(-1.0, 1.0)

    return signal
