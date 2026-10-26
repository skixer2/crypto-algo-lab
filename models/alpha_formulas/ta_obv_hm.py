# ta_obv_hm — OBV divergence, horizon-matched arm (OBV itself unchanged)
# Canonical rule, IDENTICAL to ta_obv_native except lookback x96:
#   OBV higher low while price lower low = long; exit on OBV lower low with
#   price flat/up.
# Arm: HORIZON-MATCHED — lookback L = 14x96 = 1344 on 15m bars. OBV is
# cumulative from the start (no period to scale).
# DEVIATION DECLARED BEFORE RUN (same discrete rule as ta_obv_native):
#   disjoint NOW/PREV windows of L bars; price LL = min(low,NOW) < min(low,PREV);
#   OBV HL = min(OBV,NOW) > min(OBV,PREV); entry level-triggered while state
#   holds; exit = OBV lower low AND price not making a new low; latch between
#   events; warmup CLOSED (2L bars). Windowed divergence replaces pivot-swing
#   divergence (the single declared deviation). Signal +1/-1, long-only clip.
#   No tuning, no variants.
import numpy as np
import pandas as pd

L = 1344   # 14 x 96

PARAMS = dict(
    long_threshold=0.5,
    short_threshold=0.55,
    signal_smoothing=1,
    atr_period=14,
    atr_stop_mult=50.0,
    atr_take_mult=50.0,
    max_position_pct=1.0,
    warmup_candles=2 * L,
    use_bias_filter=False,
    signal_exit_threshold=0.5,
)


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, low, vol = df["close"], df["low"], df["volume"]
    obv = (np.sign(close.diff()) * vol).expanding().sum()
    pl_now = low.rolling(L, min_periods=L).min()
    pl_prev = low.shift(L).rolling(L, min_periods=L).min()
    ol_now = obv.rolling(L, min_periods=L).min()
    ol_prev = obv.shift(L).rolling(L, min_periods=L).min()
    price_ll = pl_now < pl_prev
    price_nll = pl_now >= pl_prev
    obv_hl = ol_now > ol_prev
    obv_ll = ol_now < ol_prev
    ev = pd.Series(np.nan, index=df.index)
    ev[price_ll & obv_hl] = 1.0
    ev[obv_ll & price_nll] = 0.0
    latch = ev.ffill().fillna(-1.0)
    return latch
