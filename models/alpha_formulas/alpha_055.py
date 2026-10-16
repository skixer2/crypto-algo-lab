"""
alpha_055 — TURTLE LATCH v2: crisp binary trend-latching bull surfer.
Hypothesis: the bull seat is empty because graded/EWM trend memory (alpha_026)
dilutes below the tuner's entry threshold and never re-crosses, missing melt-up
months (2022-07 +57%, 2023-10 +14%). Fix: the HOLDING is BINARY — signal is
pinned at exactly +1.0 while close > trailing structural level (rolling max of
high, shifted 1), and drops to 0.0 the moment close falls below a WIDER trailing
level. No decay, no graded memory. Entry smoothness comes only from a small
tanh ramp on (close - trail)/ATR near the boundary; holding logic is crisp.
Volume confirmation of the breakout lift raises entry ramp only.
Quadrant attacked: P1 BULL SEAT — uptrend_participation (60%) and
extreme_participation (bench >= +15% -> strat > 0), while staying flat
(signal 0.0, not negative) in down windows so down_shield passes.
Author: auto-gen (isolated alpha loop), 2026-10-13.
Provenance: tuner/runs/alpha_054_auto.json + alpha_053_auto.json (both fail
uptrend_participation + extreme_participation on 2022-07 and 2023-10 windows);
alpha_026.py death post-mortem (EWM dilution); charter v2 P1(a) spec
(JP 2026-10-11). Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    high = df["high"]
    volume = df["volume"]
    eps = 1e-9

    # ---------- trailing structural levels (shifted 1: no look-ahead) ------
    # Latch level: N-bar rolling max of highs. HOLD while close above it.
    hold_n = 192  # 48h @15m
    latch_lvl = high.rolling(hold_n, min_periods=hold_n // 2).max().shift(1)

    # Wider structural exit level: deep trail. Below this -> flat, no memory.
    exit_n = 480  # 120h @15m
    exit_lvl = high.rolling(exit_n, min_periods=exit_n // 2).max().shift(1)

    # ---------- ATR for boundary normalization -----------------------------
    tr = np.maximum(
        high - df["low"],
        np.maximum((high - close.shift(1)).abs(), (close - close.shift(1)).abs()),
    )
    atr = tr.rolling(96, min_periods=24).mean().replace(0, eps)

    # ---------- CRISP BINARY LATCH ----------------------------------------
    # state: 1.0 while close > latch level; 0.0 below the WIDE exit level.
    # Between latch and exit levels: hold last state (ratchet, forward-fill),
    # implemented with trailing-only ops.
    above = (close > latch_lvl).astype(float)
    below_exit = (close < exit_lvl).astype(float)

    # raw latch: set on `above`, cleared on `below_exit`; hold otherwise.
    # Trailing implementation: cumulative max of (set_event - clear_cum),
    # classic forward-fill latch without shift(-n) or full-sample ops.
    set_evt = above
    clear_evt = below_exit
    # flip to 1 at set, to 0 at clear; hold between via cummax trick
    events = set_evt - clear_evt
    # hold = last nonzero event sign, trailing only
    signed = events.replace(0, np.nan)
    latch = signed.ffill().fillna(0.0)
    # a simultaneous set+clear bar (weird gap) resolves to the set side only
    # if above; default conservative: keep prior (ffill already handles).
    latch = latch.clip(0.0, 1.0)

    # ---------- entry smoothness ramp (near-boundary only) -----------------
    edge = ((close - latch_lvl) / atr).clip(-2, 2)
    ramp = 0.5 + 0.5 * np.tanh(1.0 * edge)  # in [0,1]; ~1 well above level

    # ---------- volume conviction on entry lift ----------------------------
    vol_rel = (volume / volume.rolling(192, min_periods=48).mean().replace(0, eps)).clip(0, 3)
    vol_conf = 0.7 + 0.3 * np.tanh((vol_rel - 1.0) / 1.0)  # in [0.4, 1.0]

    # ---------- composite: binary hold, smooth entry, never negative -------
    sig = latch * np.maximum(ramp, 0.0) * vol_conf
    # well-established holds (close far above level) get full pin to 1.0
    strong = (edge > 0.5).astype(float)
    sig = np.maximum(sig, latch * strong)
    return sig.clip(0.0, 1.0).fillna(0.0)
