# ta_stoch_native — Stochastic Oscillator (14,3,3), CANONICAL RULE, native periods
# Verbatim published rule (Lane): %K crossing %D below 20 = long;
# %K crossing %D above 80 = exit.
# Declared encoding (fixed BEFORE any run):
#   - %K raw = 100*(close - min(low,14)) / (max(high,14) - min(low,14)),
#     trailing 14-bar window incl. current bar.
#   - slow %K = SMA(%K,3); slow %D = SMA(slow %K,3).  (14,3,3 slow stochastic.)
#   - Cross = strict sign change between consecutive bars:
#     cross_up:  slowK[t] > slowD[t] AND slowK[t-1] <= slowD[t-1]
#     cross_dn:  slowK[t] < slowD[t] AND slowK[t-1] >= slowD[t-1]
#   - "below 20" / "above 80" declared as the CROSSING LINE slowK at the cross
#     bar (slowK<20 required for entry cross; slowK>80 required for exit cross).
#   - Warmup CLOSED: rolling min_periods=window -> NaN until formed -> flat.
#   - Latch: entry event -> +1, exit event -> 0 (held between events), flat
#     before first event. Signal +1/-1, engine clips long-only.
#   - Arm: NATIVE (14,3,3 on 15m bars).
import numpy as np
import pandas as pd

W = 14    # %K lookback, native
S = 3     # smoothing of %K and of %D, native

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
    ev[cross_up & (slow_k < 20.0)] = 1.0   # cross up below 20 -> long
    ev[cross_dn & (slow_k > 80.0)] = 0.0   # cross down above 80 -> exit
    latch = ev.ffill().fillna(-1.0)
    return latch
