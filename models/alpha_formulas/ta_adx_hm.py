# ta_adx_hm — ADX with DI, horizon-matched arm (ADX 25 threshold unchanged)
# Canonical rule (Wilder), IDENTICAL to ta_adx_native except period x96:
#   DI+ > DI- AND ADX > 25 = long; DI+ < DI- = exit.
# Arm: HORIZON-MATCHED — period 14x96 = 1344 on 15m bars.
# Constants STAY AS PUBLISHED: ADX threshold 25 (declared fixed).
# Declared encoding: identical machinery to ta_adx_native (Wilder ewm
# smoothing, level-state entry events, DI-cross exit events, latch, warmup
# CLOSED). Signal +1/-1, engine clips long-only. No tuning, no variants.
import numpy as np
import pandas as pd

P = 1344   # 14 x 96
K = 25.0   # ADX threshold, as published

PARAMS = dict(
    long_threshold=0.5,
    short_threshold=0.55,
    signal_smoothing=1,
    atr_period=14,
    atr_stop_mult=50.0,
    atr_take_mult=50.0,
    max_position_pct=1.0,
    warmup_candles=2 * P,
    use_bias_filter=False,
    signal_exit_threshold=0.5,
)


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    a = 1.0 / P
    up_m = high.diff()
    dn_m = -low.diff()
    plus_dm = pd.Series(np.where((up_m > dn_m) & (up_m > 0.0), up_m, 0.0),
                        index=df.index)
    minus_dm = pd.Series(np.where((dn_m > up_m) & (dn_m > 0.0), dn_m, 0.0),
                         index=df.index)
    prev_c = close.shift(1)
    tr = pd.concat([high - low, (high - prev_c).abs(), (low - prev_c).abs()],
                   axis=1).max(axis=1)
    atr = tr.ewm(alpha=a, adjust=False, min_periods=P).mean()
    pdi = 100.0 * plus_dm.ewm(alpha=a, adjust=False, min_periods=P).mean() / atr
    mdi = 100.0 * minus_dm.ewm(alpha=a, adjust=False, min_periods=P).mean() / atr
    dx = 100.0 * (pdi - mdi).abs() / (pdi + mdi)
    adx = dx.ewm(alpha=a, adjust=False, min_periods=P).mean()
    ev = pd.Series(np.nan, index=df.index)
    ev[(pdi > mdi) & (adx > K)] = 1.0
    ev[pdi < mdi] = 0.0
    latch = ev.ffill().fillna(-1.0)
    return latch
