# ta_bb_hm — Bollinger reversion, horizon-matched arm (2 sigma unchanged)
# Canonical rule (Bollinger), IDENTICAL to ta_bb_native except period x96:
#   close below lower band = long; exit at middle band.
# Arm: HORIZON-MATCHED — lookback 20x96 = 1920 on 15m bars.
# Constants STAY AS PUBLISHED: sigma 2.0 (declared fixed per pre-registration).
# Declared encoding: population std ddof=0; level-latch (entry every bar
# close<lower, exit every bar close>=middle, hold between); warmup CLOSED
# (min_periods=1920 -> engine flat). Signal +1/-1, long-only clip.
# No tuning, no variants.
import numpy as np
import pandas as pd

W = 1920   # 20 x 96
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
    ev[close < lower] = 1.0
    ev[close >= mid] = 0.0
    latch = ev.ffill().fillna(-1.0)
    return latch
