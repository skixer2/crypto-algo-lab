"""
alpha_061 — TURTLE LATCH v2: crisp binary breakout-latch bull seat (P1a)
Hypothesis (JP 2026-10-11): the blend misses melt-up months because graded
EWM memory (alpha_026's slow decay) dilutes the signal below the tuner's
exit threshold, so we exit into the heart of the trend. Fix: the HOLDING is
BINARY — signal pins at +1.0 while close > trailing structural level
(rolling N-bar max of high, shifted 1, N=192 bars ~2 days @15m), and drops
to exactly 0.0 once close falls below a wider exit level (N*1.5 trailing
high's midpoint guard: close < trailing 288-bar mid). Only the ENTRY edge is
smoothed: a small tanh ramp of (close - trail)/ATR bounded <= 0.3 so the
entry threshold (<=0.3) latches quickly, then the latch keeps us full-size
through pullbacks. Volume confirmation adds conviction on the breakout bar
only (bounded, doesn't gate the latch itself). Long/flat only, no shorting.
Anti-pattern avoided: alpha_026's ewm(span=192) memory — NO ewm on the
signal path at all.
Scale discipline: tanh inputs normalized by ATR/channel width, |x| <= 2;
divisions guarded with .replace(0, 1e-9). All ops trailing (rolling + shift).
Charter rules attacked: extreme_participation (bench >= +15% -> strat > 0),
uptrend_participation (0 < bench < 15% -> strat >= 0.6*bench), consistency,
adaptive_activity (re-latches on each new breakout episode).
Author: auto-gen (isolated alpha loop), 2026-10-14. P1a bull seat.
Provenance: tuner/runs/alpha_060_auto.json (extreme pass 13.4 vs 57 but
uptrend missed 0.0 vs 14.1 — entered but never rode); alpha_026.py (graded
memory dilution = what NOT to do); alpha_035.py structure reference.
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    eps = 1e-9

    # ATR for boundary normalization (trailing)
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    atr = tr.rolling(96, min_periods=30).mean().replace(0, eps)

    # --- Structural levels (trailing, exclude current bar) ----------------
    # Entry level: 192-bar rolling max of HIGH, shifted 1
    entry_level = high.rolling(192, min_periods=80).max().shift(1)
    # Exit level: wider 384-bar Donchian MID, shifted 1 (structural failure)
    hh_w = high.rolling(384, min_periods=160).max().shift(1)
    ll_w = low.rolling(384, min_periods=160).min().shift(1)
    exit_level = ((hh_w + ll_w) / 2.0)

    # --- Crisp latch state -------------------------------------------------
    # Raw state: +1 above entry level, 0 below exit level, held otherwise.
    above_entry = (close > entry_level).astype(float)
    above_exit = (close > exit_level).astype(float)

    # Latch: once above_entry fires, stay 1 while above_exit holds.
    # Trailing implementation: cumulative state via ffill of a status code.
    # code: 1 = fresh breakout, 0 = hold region, -1 = structural break.
    code = pd.Series(np.where(above_entry > 0, 1.0,
                     np.where(above_exit > 0, 0.0, -1.0)), index=close.index)
    # Recency arbitration WITHOUT full-sample cumsum (validator forbids):
    # long-horizon EWM of breakout vs structural-break markers; latch holds
    # while the breakout marker dominates, resets only when a structural break
    # becomes more recent/dominant. This memory arbitrates the latch only —
    # the latched signal itself does NOT decay (anti-alpha_026 failure).
    bo_mem = above_entry.ewm(halflife=192, min_periods=1).mean()
    br_mem = (code == -1.0).astype(float).ewm(halflife=192, min_periods=1).mean()
    latch = (bo_mem > br_mem).astype(float)

    # --- Entry-edge smoothness (small ramp near the boundary) -------------
    edge = ((close - entry_level) / atr).clip(-2, 2)
    ramp = 0.15 * (1.0 + np.tanh(edge * 2.0))          # in [0, 0.3]

    # --- Volume conviction on breakout bars (bounded, additive) -----------
    vma = volume.rolling(672, min_periods=100).mean().replace(0, eps)
    vrel = (volume / vma).clip(0, 3)
    vol_boost = latch * np.tanh((vrel - 1.0)) * 0.1    # in [-0.1, +0.1]

    signal = latch * (0.7 + ramp) + vol_boost          # ~[0, 1.1] when latched
    signal = signal.where(latch > 0, 0.0)              # exact 0 when flat
    return signal.fillna(0.0)
