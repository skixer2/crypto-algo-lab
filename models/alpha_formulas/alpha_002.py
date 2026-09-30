"""
alpha_002 — volatility compression breakout (trend-inception complement)
Hypothesis: breakouts from low-volatility compression regimes, confirmed by
volume expansion, initiate structural trends. Signal = volatility-normalized
momentum, amplified while the short/long ATR ratio is low (compression) and
volume velocity is high.
Regime target: compression -> expansion transitions. Complements alpha_001
(mean-reversion; wins in chop/down, fades in trends).
Author: blueprint by Gemini (round 4, 2026-09-30), audited+adapted by ZioClaw.
Documented deviations from the blueprint:
  (1) fixed NameError: `high - l` — `l` undefined (blueprint was never run);
  (2) compression amplifier clamped to [0.25, 2.0]: the raw `2.0 - ratio`
      form turns NEGATIVE when ratio > 2 (violent expansion), inverting the
      signal and shorting exactly the breakouts the strategy hunts;
  (3) scale 3.0 instead of 10.0: tanh saturates above ~2, and x10 pinned the
      signal at +-1 almost always, leaving entry thresholds unable to
      discriminate; x3 keeps the grading.
Inputs: OHLCV only. Provenance: Gemini round-4 blueprint + ZioClaw audit.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]

    # 1. Causal volatility tracking (True Range, short vs long horizon)
    tr = pd.concat([high - low,
                    (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs()], axis=1).max(axis=1)
    short_atr = tr.rolling(10, min_periods=5).mean()
    long_atr = tr.rolling(60, min_periods=20).mean()
    compression_ratio = short_atr / long_atr.replace(0, 1e-9)

    # 2. Volume velocity (expansion confirmation)
    volume_velocity = volume / volume.rolling(30, min_periods=10).mean().replace(0, 1e-9)

    # 3. Volatility-normalized momentum direction
    price_delta = close.diff(5)
    rolling_std = close.diff(1).rolling(20, min_periods=10).std().replace(0, 1e-9)
    vol_norm_momentum = price_delta / rolling_std

    # 4. Composite: momentum amplified under compression + volume thrust
    amplifier = (2.0 - compression_ratio).clip(0.25, 2.0)  # no sign inversion
    raw_signal = vol_norm_momentum * amplifier * volume_velocity * 3.0

    # 5. Bounded causal output
    return np.tanh(raw_signal).fillna(0.0)
