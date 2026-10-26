# ta_aroon_native — Aroon(25), CANONICAL RULE, native period
# Verbatim published rule (Chande): AroonUp crossing above AroonDown = long;
# AroonUp crossing below AroonDown = exit.
# Declared encoding (fixed BEFORE any run):
#   - Window = trailing P+1 bars incl. current (P=25).
#   - periods_since_high = argmax(high, window)  (0 = current bar is the high)
#   - periods_since_low  = argmin(low,  window)
#   - AroonUp   = 100 * (P - periods_since_high) / P   (0..100)
#   - AroonDown = 100 * (P - periods_since_low)  / P
#     (high at current bar -> 100; high at oldest window bar -> 0.)
#   - Cross = strict sign change between consecutive bars:
#     cross_up: Up[t] > Dn[t] AND Up[t-1] <= Dn[t-1]  -> entry event
#     cross_dn: Up[t] < Dn[t] AND Up[t-1] >= Dn[t-1]  -> exit event
#   - Latch held between events; flat before first event. Warmup CLOSED
#     (rolling min_periods=P+1). Signal +1/-1, engine clips long-only.
#   - Arm: NATIVE (P=25 on 15m bars). No tuning, no variants.
import numpy as np
import pandas as pd

P = 25     # Aroon period, native

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
