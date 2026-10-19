"""bull_r3 latch-192 engine formula — exact arithmetic-anchor construction.

Signal: +1.0 while turtle-latched long, -1.0 when flat. The engine's
manage_position signal-flip exit (sig <= -signal_exit_threshold) fires
exactly on the turtle exit decision; entry (sig >= long_threshold) exactly
on the breakout decision. Round-1/anchor conventions: rolling(192,
min_periods=96) trailing high/low shifted 1; ATR = SMA(TR, 96,
min_periods=32), buffer 1.0*ATR. Causal (shift-1) by construction.
Funding gate NOT expressible here (formula contract is OHLCV-only); the
gated recruit is validated through framework.runner with a gate-carrying
model (see report). Author: bull-mining r3, 2026-10-19.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low = df["close"], df["high"], df["low"]
    th = high.rolling(192, min_periods=96).max().shift(1)
    tl = low.rolling(192, min_periods=96).min().shift(1)
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(96, min_periods=32).mean()
    above = close > th
    below = close < tl - 1.0 * atr
    ev = pd.Series(np.nan, index=close.index)
    ev[below] = 0.0
    ev[above] = 1.0
    latch = ev.ffill().fillna(0.0)
    return (latch * 2.0 - 1.0).clip(-1.0, 1.0).fillna(-1.0)
