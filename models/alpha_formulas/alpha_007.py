"""
alpha_007 — dip-buy entries in confirmed uptrends + slow-fading exposure memory
Hypothesis: 3 consecutive failures on the mild-up chop wall (+3.89% bench)
share one mechanism: entries fire on strength (velocity triggers), price mean-
reverts inside the grind, the ATR stop is hit, and the cycle repeats (buy-high,
stop-low) — so long exposure never converts to capture despite a bullish gate.
The exit side (ATR SL/TP only, mult 1-4/1-5) cannot be changed from the
formula, so this formula changes WHERE entries happen instead: buy DIPS inside
a confirmed uptrend (price below its short EMA), where distance-to-stop is
favorable relative to expected grind, and keep exposure alive with a slow-
fading memory (long EWMA of the gated signal) so the engine re-enters quickly
after a stop-out instead of waiting for the next momentum burst. A low-vol
regime floor raises base exposure in calm grind (where stops are least likely
to be hit in % terms) and the trend gate still flattens in sustained downtrends.
Charter rules attacked: UPTREND PARTICIPATION (>=60% capture on 0<bench<15%)
and DOWN-SHIELD (trend gate + memory decay flatten in drops).
Author: escalated cycle (flagship model), 2026-10-01.
Inputs: OHLCV. Provenance: tuner/runs/alpha_004/5/6_auto.json — wall window
strat -0.11/-2.82/-3.56 vs bench +3.89; entries 18/20/7.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]

    # --- trend gate: fast/slow EMA spread, graded [0,1] ---
    ema_f = close.ewm(span=32, min_periods=12).mean()
    ema_s = close.ewm(span=128, min_periods=40).mean()  # ~32h context
    spread = (ema_f - ema_s) / close
    g_trend = 0.5 * (np.tanh((spread + 0.002) * 500.0) + 1.0)

    # --- dip-buy timing: NEGATIVE short-horizon return inside the uptrend
    #     (enter where mean reversion works FOR the stop, not against it) ---
    ret = close.pct_change()
    sigma = ret.rolling(48, min_periods=20).std().replace(0, 1e-9)
    dip = -(close.pct_change(8) / (sigma * np.sqrt(8)))          # + when dipping
    dip_f = np.tanh(dip / 1.5)                                    # [-1,1]
    # --- momentum continuation for trend legs (graded, smaller weight) ---
    mom = np.tanh((close.pct_change(16) / (sigma * 4.0)) / 1.5)

    # --- low-vol regime floor: calm grind -> high base exposure ---
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr_pct = (tr.rolling(48, min_periods=20).mean() / close).replace(0, 0.001)
    calm = 0.5 * (np.tanh((0.006 - atr_pct) / 0.002) + 1.0)      # 1 if ATR%<0.4%

    base = 0.45 + 0.35 * calm + 0.25 * dip_f + 0.10 * mom        # ~[0.1, 1.15]

    raw = base * g_trend

    # --- slow-fading exposure memory: EWMA keeps signal alive across
    #     stop-outs (engine only fires when flat -> fast re-entry) and
    #     decays gently in downtrends (down-shield stays intact) ---
    sig = raw.ewm(span=64, min_periods=16).mean()

    return sig.clip(0.0, 1.0).fillna(0.0)
