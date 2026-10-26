# wq101_043 — VERBATIM port of Alpha#43 from "101 Formulaic Alphas"
# (Zura Kakushadze, arXiv:1601.00991). Formula transcribed character-for-character
# from the arXiv PDF (canonical source); this file implements its time-series
# semantics on a single-asset ETH/USDT 15m OHLCV panel (N=1), WQ operator
# conventions per the paper's Appendix.
#
# Original formula (verbatim):
#     (ts_rank((volume / adv20), 20) * ts_rank((-1 * delta(close, 7)), 8))
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
#   - None. Product of two (0, 1] ts_ranks -> output in [0, 1]; no tanh needed.

# Provenance: arXiv:1601.00991 (one-shot bounded experiment, JP-requested).
# Contract: models/alpha_formulas/README.md — causal, trailing-only, [-1, 1].
import numpy as np
import pandas as pd


def _ts_rank(s: pd.Series, d: int) -> pd.Series:
    """WQ ts_rank(x, d): time-series rank in the past d bars.
    Percentile of the current value within the trailing window (inclusive);
    in (0, 1]. Causal: trailing window only. NaN windows -> NaN."""
    return s.rolling(d, min_periods=d).apply(
        lambda w: (np.nan if np.isnan(w).any() else
                   np.count_nonzero(w <= w[-1]) / d),
        raw=True)



def _bound(raw: pd.Series) -> pd.Series:
    """The ONLY permitted adaptation (declared in header): unbounded raw
    output rescaled to [-1, 1] via np.tanh(raw / |rolling std of raw|),
    window 480 bars (min_periods 96). Degenerate scale (sd == 0 or undefined,
    e.g. constant raw) maps to flat 0 — same convention as the wrapper's
    centralized fillna(0)."""
    sd = raw.rolling(480, min_periods=96).std().replace(0.0, np.nan)
    return np.tanh(raw / sd).fillna(0.0)


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    c, v = df["close"], df["volume"]
    adv20 = (c * v).rolling(20, min_periods=20).mean()
    return _ts_rank(v / adv20, 20) * _ts_rank(-1.0 * (c - c.shift(7)), 8)
