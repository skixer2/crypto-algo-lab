# ta_rsi_native — RSI(14) Wilder reversion, CANONICAL RULE, native 15m periods
# Verbatim published rule (Wilder 1978, New Concepts in Technical Trading Systems):
#   Long when RSI(14) < 30. Exit when RSI(14) > 50.
#   Symmetric short is NOT traded (long-only clip handles it — per pre-registration).
# Declared encoding (fixed BEFORE any run):
#   - RSI = Wilder smoothing: ewm(alpha=1/14, adjust=False, min_periods=14) on
#     gains/losses (Wilder's RMA). Warmup CLOSED: NaN until 14 obs -> engine flat.
#   - Level-latch state machine: every bar RSI<30 raises entry event; every bar
#     RSI>50 raises exit event; 30<=RSI<=50 holds prior state (canonical reading
#     of the two levels as entry/exit zones). Flat before first event.
#   - Signal: +1 long, -1 flat (engine clips to [0,1], long-only).
#   - No tuning, no variants. Arm: NATIVE (period 14 on 15m bars).
import numpy as np
import pandas as pd

W = 14  # RSI period, native 15m

PARAMS = dict(
    long_threshold=0.5,
    short_threshold=0.55,
    signal_smoothing=1,
    atr_period=14,
    atr_stop_mult=50.0,
    atr_take_mult=50.0,
    max_position_pct=1.0,
    warmup_candles=W,
    use_bias_filter=False,
    signal_exit_threshold=0.5,
)


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / W, adjust=False, min_periods=W).mean()
    avg_loss = loss.ewm(alpha=1.0 / W, adjust=False, min_periods=W).mean()
    rsi = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    ev = pd.Series(np.nan, index=df.index)
    ev[rsi < 30.0] = 1.0   # entry zone (Wilder's own level)
    ev[rsi > 50.0] = 0.0   # exit zone (Wilder's own level)
    latch = ev.ffill().fillna(-1.0)
    return latch
