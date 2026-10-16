"""
alpha_046 — short-leg breakdown earner v1 (JP promotion 2026-10-07, P1)
Hypothesis: down-shield experts (alpha_032: +28.6 excess on a -31.3 leg)
protect but never EARN in down-windows. The tuner permits shorts; a signal
that goes NEGATIVE during confirmed breakdowns converts shield-knowledge
into down-leg RETURN. Design: short ONLY on 2-day confirmed breakdown —
close below the 1-day Donchian mid AND 4h EMA below 1-day EMA, both held
for 2 consecutive daily confirmations (ewm-persist > 0.6) — sized by
tanh(breakdown depth). EXIT INSTANTLY on structural reclaim: cross back
above the Donchian mid with a volume surge kills the short immediately
(bear-rally trap protection, 2022-01 style). Flat (0) whenever neither
confirmed-breakdown nor it is decaying; never fights reclaim conditions.
Charter rules attacked: DOWN-SHIELD (bench<=0 -> strat>=0.2*bench) via
down-leg RETURNS, plus medium_term_edge through active short entries.
Author: auto-gen (isolated alpha loop), 2026-10-11.
Provenance: alpha_010/014 lineage (valve + breakdown confirm lessons);
alpha_032 demo (perfect shield, zero up-capture); tuner/runs/alpha_044
and alpha_045 (extreme/uptrend failures irrelevant to short specialist).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]

    d = 96  # 1 day of 15m bars
    h4 = 16

    # ---- structure: 1-day Donchian mid ----
    hh = high.rolling(d, min_periods=40).max().shift(1)
    ll = low.rolling(d, min_periods=40).min().shift(1)
    mid = 0.5 * (hh + ll)
    chan = (hh - ll).replace(0, 1e-9)

    # breakdown depth below mid, normalized by channel width
    depth = (mid - close) / chan  # >0 when below mid

    # ---- confirmation 1: below mid, sustained (2-day persistence via ewm) --
    below = (depth > 0.02).astype(float)
    below_persist = below.ewm(span=2 * d, min_periods=10).mean()  # ~2-day memory

    # ---- confirmation 2: fast trend below slow trend (4h ema < 1d ema) ----
    ema_f = close.ewm(span=h4, min_periods=6).mean()
    ema_s = close.ewm(span=d, min_periods=30).mean()
    atr = (
        np.maximum(
            high - low,
            np.maximum((high - close.shift(1)).abs(), (low - close.shift(1)).abs()),
        )
        .rolling(d, min_periods=30)
        .mean()
        .replace(0, 1e-9)
    )
    trend_down = np.tanh((ema_s - ema_f) / atr * 2.0).clip(lower=0.0)

    # ---- reclaim detector: structural reclaim kills the short ----
    reclaim = (
        (close > mid).astype(float)
        * (0.5 + 0.5 * (volume / volume.rolling(d, min_periods=30).mean().replace(0, 1e-9)).clip(0, 2) / 2)
    )
    reclaim_dec = reclaim.ewm(span=8, min_periods=2).mean()  # fast decay memory

    # ---- confirmed breakdown gate (min-gate keeps amplitude) ----
    conf = np.minimum(below_persist * 2.0, 1.0) * trend_down

    # short signal: negative, sized by depth, bounded
    short = -1.6 * np.tanh(depth * 4.0) * conf * (1.0 - reclaim_dec.clip(0.0, 1.0))

    # never long; flat is fine. Final: negative during confirmed breakdowns, 0 else.
    sig = short.clip(-2.0, 0.0)
    return sig.fillna(0.0)
