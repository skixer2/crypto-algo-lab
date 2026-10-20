# alpha_076 — RAW TURTLE192 LATCH (DS design, loop-corroborated; plumbing
# spec: reports/ENG_funding_plumbing.md). Re-armable state machine, NOT an
# expanding().max() pin (the alpha_070 lesson): entry/exit event markers,
# forward-filled state — entry re-arms after every structural release.
#   entry: close >  rolling(192, min_periods=96).max(high).shift(1)
#   exit:  close <  rolling(192, min_periods=96).min(low).shift(1) - 1.0*ATR96
#   ATR96 = SMA(TR, 96, min_periods=32)  (round-1/anchor convention)
# Entry precedence on marker ties; state 0 before the first event.
# Formula-interface encoding: +1.0 while latched, -1.0 when flat — the engine
# enters at sig >= long_threshold and manage_position's signal-flip exit
# (sig <= -signal_exit_threshold) fires exactly on the structural release.
# Engine stops (50*ATR14 rails) remain disaster rails only. Causal by
# construction (shift-1 channels). Gate/funding cost live in the engine's
# funding-gate plumbing + evaluation overlays, never in this formula.
# Provenance: bull-r3 recruit (latch x binance-gate, verified 99.85% pos
# match vs bar arithmetic), DS round-2/3 loop, JP 2026-10-19.
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
# Funding gate (ENG_funding_plumbing.md): entry-gated only, exits never gated.
FUNDING_GATE = dict(
    use_funding_gate=True,
    funding_gate_pctl=0.7,
    funding_input="binance",
)


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low = df["close"], df["high"], df["low"]
    th = high.rolling(192, min_periods=96).max().shift(1)
    tl = low.rolling(192, min_periods=96).min().shift(1)
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()],
                   axis=1).max(axis=1)
    atr = tr.rolling(96, min_periods=32).mean()
    above = close > th
    below = close < tl - 1.0 * atr
    # Event markers -> state machine: ev[exit]=0, ev[entry]=1 (entry
    # precedence), forward-fill, 0 before the first event. No
    # expanding().max() — every release re-arms the entry.
    ev = pd.Series(np.nan, index=close.index)
    ev[below] = 0.0
    ev[above] = 1.0
    latch = ev.ffill().fillna(0.0)
    return (latch * 2.0 - 1.0).clip(-1.0, 1.0).fillna(-1.0)
