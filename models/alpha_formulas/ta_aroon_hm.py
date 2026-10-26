# ta_aroon_hm — Aroon, horizon-matched arm (no other constants)
# Canonical rule (Chande), IDENTICAL to ta_aroon_native except period x96:
#   AroonUp crossing above AroonDown = long; opposite cross = exit.
# Arm: HORIZON-MATCHED — P = 25x96 = 2400 on 15m bars.
# Declared encoding: window P+1 bars incl. current; Aroon = 100*(P - since)/P;
# strict sign-change crosses; latch held between events; warmup CLOSED
# (min_periods=P+1 -> engine flat). Signal +1/-1, engine clips long-only.
# No tuning, no variants.
import numpy as np
import pandas as pd

P = 2400   # 25 x 96

PARAMS = dict(
    long_threshold=0.5,
    short_threshold=0.55,
    signal_smoothing=1,
    atr_period=14,
    atr_stop_mult=50.0,
    atr_take_mult=50.0,
    max_position_pct=1.0,
    warmup_candles=P + 1,
    use_bias_filter=False,
    signal_exit_threshold=0.5,
)


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    high, low = df["high"], df["low"]
    win = P + 1
    idx_h = high.rolling(win, min_periods=win).apply(
        lambda x: float(np.argmax(x)), raw=True)
    idx_l = low.rolling(win, min_periods=win).apply(
        lambda x: float(np.argmin(x)), raw=True)
    up = 100.0 * (P - idx_h) / P
    dn = 100.0 * (P - idx_l) / P
    pu, pdn = up.shift(1), dn.shift(1)
    cross_up = (up > dn) & (pu <= pdn)
    cross_dn = (up < dn) & (pu >= pdn)
    ev = pd.Series(np.nan, index=df.index)
    ev[cross_up] = 1.0
    ev[cross_dn] = 0.0
    latch = ev.ffill().fillna(-1.0)
    return latch
