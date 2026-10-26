# wq101_084 — VERBATIM port of Alpha#84 from "101 Formulaic Alphas"
# (Zura Kakushadze, arXiv:1601.00991). Formula transcribed character-for-character
# from the arXiv PDF (canonical source); this file implements its time-series
# semantics on a single-asset ETH/USDT 15m OHLCV panel (N=1), WQ operator
# conventions per the paper's Appendix.
#
# Original formula (verbatim):
#     SignedPower(Ts_Rank((vwap - ts_max(vwap, 15.3217)), 20.7127), delta(close, 4.96796))
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
#   - Non-integer windows (15.3217, 20.7127, 4.96796) rounded to int bars —
#       forced by bar-level implementation (declared).
#       Numeric hygiene: overflow to +/-inf from x**a (a can be large/negative)
#       mapped to NaN; base x in (0, 1] so no negative-base NaNs arise.
#       tanh bound: x**a is unbounded for negative exponents.

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
    h, l, c = df["high"], df["low"], df["close"]
    vwap = (h + l + c) / 3.0
    x = _ts_rank(vwap - vwap.rolling(15, min_periods=15).max(), 21)
    a = c - c.shift(5)
    with np.errstate(over="ignore", invalid="ignore"):
        raw = pd.Series(np.power(x.to_numpy(dtype=float),
                                 a.to_numpy(dtype=float)), index=df.index)
    raw = raw.replace([np.inf, -np.inf], np.nan)
    return _bound(raw)
