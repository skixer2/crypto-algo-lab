# ta_obv_native — OBV(14) divergence, CANONICAL RULE, native lookback
# Verbatim published rule (Granville-style OBV divergence):
#   OBV making higher low while price makes lower low (14-bar lookback) = long;
#   exit on OBV lower low with price flat/up.
# DEVIATION DECLARED BEFORE RUN (divergence is not uniquely encodable; this is
# the exact discrete, strictly causal rule used):
#   - OBV = expanding sum of sign(close.diff()) * volume.
#   - Two DISJOINT trailing windows of L=14 bars: NOW = bars [t-L+1, t],
#     PREV = bars [t-2L+1, t-L].
#   - Price lower low  : min(low, NOW)  <  min(low, PREV)
#   - OBV higher low   : min(OBV, NOW)  >  min(OBV, PREV)
#   - ENTRY event = (price lower low) AND (OBV higher low), level-triggered
#     every bar the divergence state holds (latch re-arms after any exit).
#   - EXIT event = (min(OBV, NOW) < min(OBV, PREV)) AND (min(low, NOW) >=
#     min(low, PREV)) — OBV lower low while price flat/up — level-triggered.
#   - Entry/exit events mutually exclusive; latch holds between events; flat
#     before first event. Warmup CLOSED (windows NaN until 2L bars -> flat).
#   - Windowed-window divergence instead of pivot-swing divergence is the
#     single declared deviation (pre-registered allowance for this system).
#   - Signal +1/-1, engine clips long-only. Arm: NATIVE (L=14 on 15m bars).
#     No tuning, no variants.
import numpy as np
import pandas as pd

L = 14     # divergence lookback, native

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
    ev[price_ll & obv_hl] = 1.0        # bullish divergence -> long
    ev[obv_ll & price_nll] = 0.0       # OBV lower low, price flat/up -> exit
    latch = ev.ffill().fillna(-1.0)
    return latch
