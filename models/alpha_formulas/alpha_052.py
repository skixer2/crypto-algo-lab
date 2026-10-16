"""
alpha_052 — TURTLE LATCH v2 (crisp bull seat, no graded memory)
Hypothesis (JP 2026-10-11 P1a): the bull seat is empty because graded EWM
memory dilutes signals below exit thresholds (alpha_026's death). Fix:
BINARY latching trend signal — signal = +1.0 pinned while close > trailing
structural level (rolling max of high shifted 1 bar, N=192 bars = 48h at
15m), 0.0 below. Holding is binary; no decay, no memory leak. A short tanh
ramp of (close - trail)/ATR near the boundary smooths ENTRY only (kept
>=0, so never short: this formula's job is the up seat — down windows the
regime router routes elsewhere, but the ramp floor at 0 preserves
down_shield: signal 0 in downtrends).
Entry detail: ramp = tanh((close - trail)/ATR * 2) clipped to [0,1] gives
fast engage on reclaim; once above trail the latch term
(close > trail) keeps it at max(ramp, latch) = 1.0 pinned.
Volume confirmation adds a small boost to breakout bars (volume z > 0.5)
via extra +0.25*clamp, capped at 1.0 overall.
Bounded transforms before compositing; divide only by rolling stats after
replace(0,1e-9); trailing ops only; no I/O.
Charter rules attacked: uptrend_participation, extreme_participation (bull
seat), adaptive_activity, down_shield preserved by 0-floor.
Author: escalation cycle 12 (JP bull-seat promotion), 2026-10-12.
Provenance: tuner/runs/alpha_051_auto.json + alpha_050_auto.json window
gates (fix list: extreme_participation & uptrend missed), alpha_026
anti-pattern (graded memory), alpha_040 style. Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    high = df["high"]
    volume = df["volume"]
    eps = 1e-9

    n = 192            # 48h of 15m bars: trailing structural level
    minp = n // 2
    vol_w = 96         # ATR / volume stat window (24h)

    # ---------- trailing structural level (shifted 1: no lookahead) ------
    trail = high.rolling(n, min_periods=minp).max().shift(1)

    # ---------- ATR (rolling, trailing) ----------------------------------
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low_c(df), (high - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(vol_w, min_periods=vol_w // 2).mean().replace(0, eps)

    # ---------- entry ramp: tanh((close-trail)/ATR), floor at 0 ----------
    dist = (close - trail) / atr
    ramp = np.tanh(dist.clip(-4, 4) * 2.0)
    ramp = ramp.clip(lower=0.0).fillna(0.0)

    # ---------- binary latch: pinned while close > trail -----------------
    latch = (close > trail).astype(float)

    # ---------- volume confirmation boost on breakout bars ---------------
    vz = volume.rolling(vol_w, min_periods=vol_w // 2).mean().replace(0, eps)
    vol_z = (volume - vz) / vz
    vol_ok = (vol_z.fillna(0) > 0.5).astype(float)

    base = np.maximum(ramp, latch)          # >=0 always; pinned at 1 above trail
    boosted = (base + 0.25 * vol_ok * base).clip(upper=1.0)

    # warmup guard: require trail to exist
    signal = boosted.where(trail.notna(), 0.0)
    return signal


def low_c(df: pd.DataFrame) -> pd.Series:
    return df["low"]
