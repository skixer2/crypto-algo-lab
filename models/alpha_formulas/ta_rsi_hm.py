# ta_rsi_hm — RSI reversion, horizon-matched arm (Wilder levels unchanged)
# Canonical rule (Wilder 1978), IDENTICAL to ta_rsi_native except periods x96:
#   Long when RSI < 30. Exit when RSI > 50.
#   Short NOT traded (long-only clip).
# Arm: HORIZON-MATCHED — daily-equivalent periods on 15m bars:
#   RSI period = 14 x 96 = 1344 (one 15m bar ~ 1/96 day).
# Band constants STAY AS PUBLISHED: 30 / 50 (declared fixed per pre-registration).
# Declared encoding: Wilder ewm(alpha=1/1344, adjust=False, min_periods=1344);
# warmup CLOSED (NaN until 1344 obs -> engine flat); level-latch state machine
# (entry event every bar RSI<30, exit event every bar RSI>50, hold between).
# Signal: +1 long, -1 flat. No tuning, no variants.
import numpy as np
import pandas as pd

W = 1344  # 14 x 96, horizon-matched to daily on 15m bars

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
    ev[rsi < 30.0] = 1.0
    ev[rsi > 50.0] = 0.0
    latch = ev.ffill().fillna(-1.0)
    return latch
