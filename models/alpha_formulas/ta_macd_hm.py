# ta_macd_hm — MACD, horizon-matched arm (no other constants)
# Canonical rule (Appel), IDENTICAL to ta_macd_native except periods x96:
#   MACD crossing above signal line = long; crossing below = exit.
# Arm: HORIZON-MATCHED — daily-equivalent periods on 15m bars:
#   fast 12x96 = 1152; slow 26x96 = 2496; signal 9x96 = 864.
# Declared encoding: ewm(span, adjust=False, min_periods=span); strict
# sign-change crosses; latch held between events; warmup CLOSED; signal +1/-1,
# engine clips long-only. No tuning, no variants.
import numpy as np
import pandas as pd

F = 1152    # 12 x 96
S = 2496    # 26 x 96
G = 864     # 9 x 96

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
