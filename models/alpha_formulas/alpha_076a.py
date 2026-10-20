# alpha_076a — RAW TURTLE192 LATCH, FUNDING GATE INSIDE THE FORMULA
# ("Machine A": skip-while-crowded, re-arm on next fresh breakout).
# Copy of alpha_076.py (plumbing spec: reports/ENG_funding_plumbing.md) with
# ONE delta: the funding gate moved from the engine's predict() (Machine B =
# wait-then-enter-late: the latch fires on the crowded breakout, the engine
# merely delays the fill until crowding clears) INTO the state machine:
#   entry: (close > rolling(192,min_periods=96).max(high).shift(1))
#          AND (fund_pct < 0.7)            <- gate at the breakout bar itself
#   exit:  close < rolling(192,min_periods=96).min(low).shift(1) - 1.0*ATR96
#   ATR96 = SMA(TR, 96, min_periods=32)  (round-1/anchor convention)
# A crowded breakout produces NO entry event: the latch stays off and the
# position can only start on a FRESH breakout after crowding clears. Exit is
# never gated (structural exits rule the latch). Engine params/funding input
# frozen identical to alpha_076's exam block; only the gate locus differs.
# Contract: the engine injects the settled-funding percentile-rank series as a
# 'fund_pct' column into this frame (funding_gate_mode='formula' in
# WQAlphaParams; fast path slices ctx.fund_pct, direct path reindexes
# model.fund_pct — identical values, enforced by equivalence tests). NaN rank
# => comparison False => gate closed (same convention as the predict()-level
# gate and the verified bar-arithmetic scripts). Causal by construction:
# shift-1 channels, settled-funding ffilled series. Funding COST is never
# charged here (evaluation overlays, JP laws).
# Provenance: JP decision 2026-10-20 "if A works better, B dies" — this file
# is Machine A; alpha_076.py stays Machine B until the A/B verdict.
import numpy as np
import pandas as pd

# WQAlphaParams-compatible frozen exam defaults (params via formula file:
# tuner.alpha_orchestrator / manifest consumers read this block).
PARAMS = dict(
    long_threshold=0.5,
    short_threshold=0.55,          # long-only formula; exam runs allow_shorts=False
    signal_smoothing=1,            # binary latch — smoothing MUST stay off
    atr_period=14,                 # engine-side disaster-rail ATR only
    atr_stop_mult=50.0,
    atr_take_mult=50.0,
    max_position_pct=1.0,
    warmup_candles=100,
    use_bias_filter=False,
    signal_exit_threshold=0.5,     # structural release => sig=-1 <= -0.5 => exit
)
# Funding gate (Machine A): gate lives INSIDE the formula via the injected
# 'fund_pct' column; the engine-level predict() gate stays OFF.
FUNDING_GATE = dict(
    use_funding_gate=True,
    funding_gate_pctl=0.7,
    funding_input="binance",
    funding_gate_mode="formula",
)


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low = df["close"], df["high"], df["low"]
    fund = df["fund_pct"]  # injected by the engine (funding_gate_mode='formula')
    th = high.rolling(192, min_periods=96).max().shift(1)
    tl = low.rolling(192, min_periods=96).min().shift(1)
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()],
                   axis=1).max(axis=1)
    atr = tr.rolling(96, min_periods=32).mean()
    # Gate INSIDE the state machine: only an UNCROWDED breakout raises the
    # entry event. NaN rank => False => gate closed (predict()-gate convention).
    uncrowded = (fund < 0.7).fillna(False)
    above = (close > th) & uncrowded
    below = close < tl - 1.0 * atr
    # Event markers -> state machine: ev[exit]=0, ev[entry]=1 (entry
    # precedence), forward-fill, 0 before the first event. No
    # expanding().max() — every release re-arms the entry, and a missed
    # (crowded) breakout is NOT remembered: re-arm needs a fresh breakout.
    ev = pd.Series(np.nan, index=close.index)
    ev[below] = 0.0
    ev[above] = 1.0
    latch = ev.ffill().fillna(0.0)
    return (latch * 2.0 - 1.0).clip(-1.0, 1.0).fillna(-1.0)
