# LINEAGE: NNPILOT-A-20261028 (GBM rule-extractor, H={96: '1d', 672: '7d'}, fold-stable leaf path)
# Machine-generated candidate. Pre-registered pilot: PILOT_A_SPEC.md. NOT a proposal card;
# screens once canonically; cannot be seal-grade on extractor-seen data. [CONTROL] selection excess 0.898%/mo, support 14438 bars (selection-only number)
import numpy as np
import pandas as pd


def _features(df):
    close, high, low = df["close"], df["high"], df["low"]
    lr = np.log(close / close.shift(1))
    X = pd.DataFrame(index=df.index)
    X["f_ret24"] = np.log(close / close.shift(96))
    X["f_ret7d"] = np.log(close / close.shift(672))
    X["f_vol24"] = lr.rolling(96).std()
    tr = pd.concat([high - low, (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs()], axis=1).max(axis=1)
    X["f_atr"] = tr.rolling(96, min_periods=32).mean() / close
    ch_hi = high.rolling(192, min_periods=96).max().shift(1)
    ch_lo = low.rolling(192, min_periods=96).min().shift(1)
    X["f_chan"] = (close - ch_lo) / (ch_hi - ch_lo)
    X["f_disth"] = close / ch_hi - 1.0
    fund = df["fund_pct"] if "fund_pct" in df.columns else pd.Series(np.nan, index=df.index)
    X["f_fund"] = fund
    X["f_volratio"] = X["f_vol24"] / lr.rolling(2016).std()
    bod = df.index.hour * 4 + df.index.minute // 15
    ph = 2.0 * np.pi * bod / 96.0
    X["f_tod_sin"] = np.sin(ph)
    X["f_tod_cos"] = np.cos(ph)
    return X


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    X = _features(df)
    rule = pd.Series(True, index=df.index)
    rule &= (X["f_ret7d"] > 0.0257153)
    rule &= (X["f_fund"] > 0.766586)
    pos = rule.astype(float)
    return pos.fillna(0.0).clip(0.0, 1.0)
