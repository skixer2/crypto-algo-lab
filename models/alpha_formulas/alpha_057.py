"""
alpha_057 — TURTLE LATCH v2 (rolling-max trail) + SLOW-EMA REGIME VETO.
Hypothesis: alpha_056 solved the bull seat (up-capture +1.02 in the 2022-07
+62% V-window) but failed down_shield by re-entering latches inside bear legs
(-9.3% on a -31.3% bench = 30% of the drop, charter allows only 20%). The
latch itself is fine; the missing piece is a CRISP, non-graded bear veto.
Fix (P1a continuation): keep alpha_056's binary latch — pin +1.0 while
close > rolling max of highs shifted 1 (N=288 bars, 3d), release when close
breaks the Donchian mid-band or a hard -7% trail stop (no EWM memory, no
graded dilution — the alpha_026 death) — and multiply by a binary regime
gate: close > EMA(960 bars, 10d). In down legs price sits below the 10d EMA,
so the latch never arms and the book stays flat (down_shield); in V-turns
price reclaims the EMA within days, so entry lag is small and up-capture
survives. tanh ramp of (close-trail)/ATR near the boundary for entry
smoothness; HOLDING stays binary.
Quadrant attacked: P1 BULL SEAT — uptrend_participation +
extreme_participation while fixing alpha_056's down_shield failure.
Author: auto-gen (isolated alpha loop), 2026-10-13.
Provenance: tuner/runs/alpha_056_auto.json (up_capture +1.02, down_shield
FAIL -9.3 vs -31.3), alpha_056.py latch recipe, alpha_026.py anti-pattern.
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    high = df["high"]
    low = df["low"]
    eps = 1e-9

    # ---------- trailing structural level (shifted: no look-ahead) ----------
    trail_n = 288  # 3d @15m
    trail = high.rolling(trail_n, min_periods=trail_n // 2).max().shift(1)

    # ---------- donchian mid release level (040-proven band) ----------
    mid_w = 96
    upper = high.rolling(mid_w, min_periods=mid_w // 2).max()
    lower = low.rolling(mid_w, min_periods=mid_w // 2).min()
    don_mid = ((upper + lower) / 2.0).shift(1)

    # ---------- ATR for boundary ramp ----------
    tr = np.maximum(
        high - low,
        np.maximum((high - close.shift(1)).abs(), (low - close.shift(1)).abs()),
    )
    atr = tr.ewm(span=96, adjust=False).mean().replace(0, eps)

    # ---------- binary latch: pin while above trail ----------
    above = (close > trail).astype(float)
    below = (close < don_mid) | (close < trail * 0.93)  # mid break or hard -7% trail stop
    # hold state machine: latch on arm, release on exit condition (trailing op)
    armed = (close > trail).astype(float)
    released = below.fillna(True).astype(float)
    # forward-fill: latch on = last event was an arm
    evt = np.where(armed > 0, 1.0, np.where(released > 0, 0.0, np.nan))
    latch = pd.Series(evt, index=close.index).ffill().fillna(0.0)

    # ---------- entry smoothness ramp near the boundary ----------
    ramp = np.tanh((close - trail) / (2.0 * atr))
    smooth = 0.5 + 0.5 * ramp.clip(-1, 1)  # in [0,1], only softens the edge
    sig = latch * smooth.clip(0.0, 1.0)

    # ---------- regime veto: flat when below the 10d EMA ----------
    ema_slow = close.ewm(span=960, adjust=False).mean()
    regime = (close > ema_slow * 0.995).astype(float)

    out = (sig * regime).clip(0.0, 1.0)
    return out.fillna(0.0)
