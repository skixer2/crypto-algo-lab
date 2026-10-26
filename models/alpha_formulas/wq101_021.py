# wq101_021 — VERBATIM port of Alpha#21 from "101 Formulaic Alphas"
# (Zura Kakushadze, arXiv:1601.00991). Formula transcribed character-for-character
# from the arXiv PDF (canonical source); this file implements its time-series
# semantics on a single-asset ETH/USDT 15m OHLCV panel (N=1), WQ operator
# conventions per the paper's Appendix.
#
# Original formula (verbatim):
#     ((((sum(close, 8) / 8) + stddev(close, 8)) < (sum(close, 2) / 2)) ? (-1 * 1) : (((sum(close, 2) / 2) < ((sum(close, 8) / 8) - stddev(close, 8))) ? 1 : (((1 < (volume / adv20)) || ((volume / adv20) == 1)) ? 1 : (-1 * 1))))
#
# Operator mapping (WQ appendix definition -> pandas on ETH 15m OHLCV, N=1):
#   correlation(x, y, d) = x.rolling(d, min_periods=d).corr(y)   [time-serial]
#   delay(x, d)          = x.shift(d)
#   sign(x)              = np.sign(x)
#   returns              = close.pct_change()
#   sum(x, d)            = x.rolling(d, min_periods=d).sum()
#   stddev(x, d)         = x.rolling(d, min_periods=d).std()
#   ts_rank(x, d)        = trailing percentile rank of x_t within the past d
#                          bars (inclusive), in (0, 1]
#   ts_min / ts_max      = rolling(d).min() / rolling(d).max()
#   vwap                 = (high + low + close) / 3   [bar VWAP proxy; paper's
#                          vwap is a daily field unavailable at bar level]
#   adv{d}               = (close * volume).rolling(d, min_periods=d).mean()
#                          [dollar-volume per appendix; d in 15m BARS not days -
#                          declared N=1 unit deviation]

#
# Deviations (declared):
#   - None. Conditional ladder of +/-1 constants -> bounded by construction;
#       no tanh needed. Ternary chain and the literal condition `(1 < volume/adv20) || (volume/adv20 == 1)` kept exactly as written.

# Provenance: arXiv:1601.00991 (one-shot bounded experiment, JP-requested).
# Contract: models/alpha_formulas/README.md — causal, trailing-only, [-1, 1].
import numpy as np
import pandas as pd

def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    c, v = df["close"], df["volume"]
    sma8 = c.rolling(8, min_periods=8).mean()
    sd8 = c.rolling(8, min_periods=8).std()
    sma2 = c.rolling(2, min_periods=2).mean()
    r = v / (c * v).rolling(20, min_periods=20).mean()
    return pd.Series(np.where(sma8 + sd8 < sma2, -1.0,
                     np.where(sma2 < sma8 - sd8, 1.0,
                     np.where((1.0 < r) | (r == 1.0), 1.0, -1.0))),
                     index=df.index)
