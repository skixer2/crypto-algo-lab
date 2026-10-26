# ta_macd_native — MACD (12,26,9), CANONICAL RULE, native periods
# Verbatim published rule (Appel): MACD crossing above its signal line = long;
# MACD crossing below its signal line = exit.
# Declared encoding (fixed BEFORE any run):
#   - MACD = EMA(close,12) - EMA(close,26); signal = EMA(MACD,9).
#     EMAs via ewm(span=N, adjust=False, min_periods=N) — warmup CLOSED:
#     signal finite only after 26+9 valid obs; engine flat during NaN.
#   - Cross = strict sign change between consecutive bars:
#     cross_up: MACD[t] > sig[t] AND MACD[t-1] <= sig[t-1]
#     cross_dn: MACD[t] < sig[t] AND MACD[t-1] >= sig[t-1]
#   - Latch: entry event -> +1, exit event -> 0, held between events, flat
#     before first event. Signal +1/-1, engine clips long-only.
#   - Arm: NATIVE (12,26,9 on 15m bars). No tuning, no variants.
import numpy as np
import pandas as pd

F = 12     # fast EMA, native
S = 26     # slow EMA, native
G = 9      # signal EMA, native

PARAMS = dict(
    long_threshold=0.5,
    short_threshold=0.55,
    signal_smoothing=1,
    atr_period=14,
    atr_stop_mult=50.0,
    atr_take_mult=50.0,
    max_position_pct=1.0,
    warmup_candles=S + G,
    use_bias_filter=False,
    signal_exit_threshold=0.5,
)


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    ema_f = close.ewm(span=F, adjust=False, min_periods=F).mean()
    ema_s = close.ewm(span=S, adjust=False, min_periods=S).mean()
    macd = ema_f - ema_s
    sig = macd.ewm(span=G, adjust=False, min_periods=G).mean()
    pm, ps = macd.shift(1), sig.shift(1)
    cross_up = (macd > sig) & (pm <= ps)
    cross_dn = (macd < sig) & (pm >= ps)
    ev = pd.Series(np.nan, index=df.index)
    ev[cross_up] = 1.0
    ev[cross_dn] = 0.0
    latch = ev.ffill().fillna(-1.0)
    return latch
