# ta_bb_native — Bollinger (20,2) reversion, CANONICAL RULE, native periods
# Verbatim published rule (Bollinger): close below lower band = long;
# exit at middle band.
# Declared encoding (fixed BEFORE any run):
#   - middle = SMA(close, 20); sd = population std (ddof=0, TA-lib convention)
#     over trailing 20-bar window incl. current; lower = middle - 2.0*sd.
#   - Level-latch state machine: every bar close < lower raises entry event;
#     every bar close >= middle raises exit event; between lower and middle the
#     prior state holds (canonical reversion reading: band touch -> in, tag of
#     mean -> out). Flat before first event. Warmup CLOSED (min_periods=20).
#   - Sigma constant STAYS AS PUBLISHED: 2.0.
#   - Signal: +1 long, -1 flat (engine clips long-only).
#   - Arm: NATIVE (20,2 on 15m bars).
import numpy as np
import pandas as pd

W = 20     # BB lookback, native
K = 2.0    # sigma width, as published

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
    mid = close.rolling(W, min_periods=W).mean()
    sd = close.rolling(W, min_periods=W).std(ddof=0)
    lower = mid - K * sd
    ev = pd.Series(np.nan, index=df.index)
    ev[close < lower] = 1.0     # close below lower band -> long
    ev[close >= mid] = 0.0      # exit at middle band
    latch = ev.ffill().fillna(-1.0)
    return latch
