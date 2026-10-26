# ta_stoch_hm — Stochastic Oscillator, horizon-matched arm (20/80 bands unchanged)
# Canonical rule (Lane), IDENTICAL to ta_stoch_native except periods x96:
#   %K crossing %D below 20 = long; %K crossing %D above 80 = exit.
# Arm: HORIZON-MATCHED — daily-equivalent periods on 15m bars:
#   lookback 14x96 = 1344; both smoothings 3x96 = 288.
# Band constants STAY AS PUBLISHED: 20 / 80 (declared fixed per pre-registration).
# Declared encoding: raw %K over trailing 1344-bar window; slow %K = SMA(288),
# slow %D = SMA(288); strict sign-change cross; crossing line = slowK at cross
# bar; warmup CLOSED; latch held between events. Signal +1/-1, long-only clip.
# No tuning, no variants.
import numpy as np
import pandas as pd

W = 1344   # 14 x 96
S = 288    # 3 x 96

PARAMS = dict(
    long_threshold=0.5,
    short_threshold=0.55,
    signal_smoothing=1,
    atr_period=14,
    atr_stop_mult=50.0,
    atr_take_mult=50.0,
    max_position_pct=1.0,
    warmup_candles=W + 2 * S,
    use_bias_filter=False,
    signal_exit_threshold=0.5,
)


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low = df["close"], df["high"], df["low"]
    hh = high.rolling(W, min_periods=W).max()
    ll = low.rolling(W, min_periods=W).min()
    raw_k = 100.0 * (close - ll) / (hh - ll)
    slow_k = raw_k.rolling(S, min_periods=S).mean()
    slow_d = slow_k.rolling(S, min_periods=S).mean()
    pk, pd_ = slow_k.shift(1), slow_d.shift(1)
    cross_up = (slow_k > slow_d) & (pk <= pd_)
    cross_dn = (slow_k < slow_d) & (pk >= pd_)
    ev = pd.Series(np.nan, index=df.index)
    ev[cross_up & (slow_k < 20.0)] = 1.0
    ev[cross_dn & (slow_k > 80.0)] = 0.0
    latch = ev.ffill().fillna(-1.0)
    return latch
