"""
alpha_001 — volume/price rank-decoupling reversal (SEED, UNPROVEN)
Hypothesis: when short-term price change rank and volume rank become strongly
coupled (both rising together = eager buying; both falling = eager selling),
the move is over-extended and mean-reverts. Decoupling (rank-corr near zero)
is neutral. Signal = negative of the rolling rank-correlation, smoothed.
Regime target: choppy/ranging markets; expected to underperform in strong
trends (documented weakness — the bias filter should mute it).
Author: ZioClaw (GLM) — seed formula to validate the tuning loop.
Date: 2026-09-28
Inputs: OHLCV only. Provenance: inspired by WorldQuant-style rank-corr alphas.
"""
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    delta = df["close"].diff(3)
    r_delta = delta.rolling(20, min_periods=10).rank(pct=True)
    r_vol = df["volume"].rolling(20, min_periods=10).rank(pct=True)
    corr = r_delta.rolling(10, min_periods=5).corr(r_vol)
    sig = -corr
    return sig.clip(-1.0, 1.0)
