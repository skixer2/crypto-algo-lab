"""
alpha_050 — TURTLE LATCH v2 (P1 bull seat: crisp binary trend riding)
Hypothesis: alpha_026's graded EWM memory DILUTES below the tuner's
entry threshold (death by averaging). Fix: the HOLDING is binary and
pinned. Signal = +1.0 exactly while close > trailing structural level
(rolling max of high shifted 1, N=192 bars @15m = 48h), 0.0 below. A
tanh ramp on (close - trail)/ATR smooths ENTRY only, near the boundary;
once latched, the signal stays 1.0 until a hard structural break (close
below the N-bar LOW trailing level), with a wide allowance (ATR buffer)
so pullbacks never kill the ride. Volume surge at breakout raises the
entry-side strength; no volume dependence while held. Long/flat only.
Rule attacked: uptrend_participation (60%) + extreme_participation
(bench>=15% -> strat>0), i.e. the melt-up months 2022-07/08, 2023-10/11.
Author: auto-gen (isolated alpha loop), 2026-10-12.
Provenance: tuner/runs/alpha_026 (graded-memory failure), alpha_048/049
(extreme_participation 0.0 in the +57% window); JP charter v2 P1(a).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low = df["close"], df["high"], df["low"]
    volume = df["volume"]
    eps = 1e-9

    # ---- trailing structural levels (excl. current bar) ----
    n_hold = 192  # 48h of 15m bars
    trail_high = high.rolling(n_hold, min_periods=n_hold // 2).max().shift(1)
    trail_low = low.rolling(n_hold, min_periods=n_hold // 2).min().shift(1)

    # ATR for boundary normalization
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(96, min_periods=32).mean().replace(0, eps)

    # ---- entry smoothness: tanh ramp of (close - trail)/ATR near boundary
    edge = ((close - trail_high) / atr).replace([np.inf, -np.inf], 0).fillna(0)
    entry_ramp = np.tanh(edge.clip(-2, 2) * 2.0)  # in [-1, 1]

    # volume confirmation of breakout (surge = >1.6x rolling median volume)
    vmed = volume.rolling(n_hold, min_periods=n_hold // 2).median().replace(0, eps)
    vsurge = np.tanh(((volume / vmed).clip(0, 4) - 1.6)).clip(0, 1).fillna(0)

    entry = (entry_ramp + 0.3 * vsurge * entry_ramp.clip(0, 1)).clip(-1, 1)

    # ---- BINARY LATCH: pinned +1 while above wide structural stop ----
    above = (close > trail_high).astype(float)
    # wide stop: close below trailing low minus 1 ATR buffer = hard exit
    stop_level = trail_low - 1.0 * atr
    below_stop = (close < stop_level).astype(float)

    # latch implementation, trailing-only: state persists forward via
    # expanding-style loop replaced by cumulative logic.
    # state = 1 if latched and not stopped; latch on `above`, unlatch on below_stop.
    # Trailing recursive formulation via ffill of event markers:
    latch_on = above.where(above > 0)  # NaN unless breakout bar
    latch_off = below_stop.where(below_stop > 0)
    events = pd.Series(np.nan, index=close.index)
    events[latch_off.notna()] = 0.0
    events[latch_on.notna()] = 1.0  # breakout overrides stop on same bar
    latched = events.ffill().fillna(0.0)

    # ---- composite: while latched, PIN at 1.0 (crisp). While unlatched,
    # output the small entry ramp so entries can fire above threshold.
    signal = np.where(latched > 0, 1.0, 0.35 * entry.clip(0, 1))
    return pd.Series(signal, index=close.index)
