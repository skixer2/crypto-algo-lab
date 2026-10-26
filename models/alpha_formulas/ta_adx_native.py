# ta_adx_native — ADX(14) with DI, CANONICAL RULE, native period
# Verbatim published rule (Wilder): DI+ > DI- AND ADX > 25 = long;
# DI+ < DI- = exit.
# Declared encoding (fixed BEFORE any run):
#   - Wilder DI: +DM = up-move when up_move > down_move AND up_move > 0 else 0;
#     -DM symmetric on down_move; TR = max(H-L, |H-prevC|, |L-prevC|).
#   - Wilder smoothing = ewm(alpha=1/14, adjust=False, min_periods=14) on TR,
#     +DM, -DM. DI+ = 100*sma(+DM)/sma(TR); DI- = 100*sma(-DM)/sma(TR).
#   - DX = 100*|DI+ - DI-| / (DI+ + DI-); ADX = Wilder-smoothed DX (alpha=1/14,
#     min_periods=14). Warmup CLOSED (~28+ bars NaN -> engine flat).
#   - ENTRY is a level-state event: every bar (DI+ > DI-) AND (ADX > 25)
#     raises the entry event (so a later ADX re-strengthening above 25 while
#     DI+ still leads re-arms entry — canonical state reading).
#   - EXIT is the event DI+ < DI- (ADX decay alone does NOT exit, per rule).
#     Entry/exit events mutually exclusive; latch holds in between; flat
#     before first event. Signal +1/-1, engine clips long-only.
#   - ADX threshold STAYS AS PUBLISHED: 25.
#   - Arm: NATIVE (period 14 on 15m bars). No tuning, no variants.
import numpy as np
import pandas as pd

P = 14     # ADX/DI period, native
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
    ev[(pdi > mdi) & (adx > K)] = 1.0   # trending up with DI+ leading -> long
    ev[pdi < mdi] = 0.0                 # DI+ loses lead -> exit
    latch = ev.ffill().fillna(-1.0)
    return latch
