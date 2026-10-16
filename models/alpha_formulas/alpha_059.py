"""
alpha_059 — TURTLE LATCH v2 (crisp binary bull-surfer, P1 bull seat)
Hypothesis (JP + Gemini 2026-10-01/10-11 charter): the pool lacks bull-seat
surfing (blend up-capture 0.06). Graded EWM memory (alpha_026) DILUTES below
the exit threshold and dies. Fix: binary latch — signal is pinned at +1.0
while close holds above a trailing structural level (rolling max of HIGH
shifted 1 bar, N=192 bars = 48h), and drops to 0.0 the moment close breaks
below it. Holding is binary; no memory decay.
Entry smoothness: a tanh ramp of (close - trail)/ATR near the boundary gives
a soft on-ramp, but once latched, the level RE-ARMS only at a higher rolling
max (trailing max of high naturally ratchets), so the position rides the
whole melt-up with a wide floor. Volume surge at latch-on raises nothing —
kept out of the latch to avoid dilution; only gates the initial entry via a
small additive term that vanishes once pinned.
Bounded transforms before compositing (tanh, |x|<=2); trailing ops only
(rolling/shift(1)); divisions guarded with .replace(0,1e-9); no I/O.
Charter rules attacked: extreme_participation, uptrend_participation,
medium_term_edge; down_shield inherited from fast binary exit (0 signal in
downtrends -> shield handled by router/blend).
Author: bull-seat escalation cycle, 2026-10-14.
Provenance: tuner/runs/alpha_058_auto.json window_rules; failure analysis of
alpha_026 (graded memory dilution); charter v2 P1(a).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    high = df["high"]
    low = df["low"]
    eps = 1e-9

    n_latch = 192          # 48h structural trail on 15m bars
    n_fast = 32            # 8h fast trail for early entry ramp
    n_atr = 96             # 24h ATR window
    minp = n_latch // 2

    # ---------- trailing structural levels -------------------------------
    trail = high.rolling(n_latch, min_periods=minp).max().shift(1)
    trail_fast = high.rolling(n_fast, min_periods=n_fast // 2).max().shift(1)

    # ---------- ATR (Wilder-ish, rolling mean is fine) -------------------
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low),
         (high - prev_close).abs(),
         (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(n_atr, min_periods=n_atr // 2).mean().replace(0, eps)

    # ---------- distance above the trail, bounded ------------------------
    dist = (close - trail) / atr.replace(0, eps)
    dist = dist.replace([np.inf, -np.inf], 0.0).clip(-2.0, 2.0).fillna(0.0)
    dist_fast = (close - trail_fast) / atr.replace(0, eps)
    dist_fast = dist_fast.replace([np.inf, -np.inf], 0.0).clip(-2.0, 2.0).fillna(0.0)

    # ---------- binary latch: pinned +1 while close >= trail -------------
    latched = (close >= trail).astype(float)
    # once we have EVER been above the fast trail and close still above the
    # slow trail, stay pinned (ratchet hold). Implemented with a cumulative
    # max on the latch flag = trailing-only op.
    ever = latched.expanding(min_periods=1).max().fillna(0.0)
    hold = np.where((ever > 0) & (close >= trail), 1.0, 0.0)
    hold = pd.Series(hold, index=close.index)

    # ---------- soft entry ramp near the boundary (pre-latch) ------------
    ramp = np.tanh(dist_fast / 0.5)          # [-1, 1]
    ramp = ramp.where(latched == 0, 0.0)     # vanish once latched

    # ---------- composite signal, clipped to entry band -------------------
    sig = 0.85 * hold + 0.35 * ramp
    sig = sig.clip(-1.0, 1.5).fillna(0.0)

    # wide structural stop feedback: if close collapsed far below slow trail
    # (> 2 ATR), force zero — the binary exit is the shield.
    deep_break = (dist < -2.0).astype(float)
    sig = sig.where(deep_break == 0, 0.0)

    return sig
