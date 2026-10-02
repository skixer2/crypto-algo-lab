"""
alpha_009 — regime-gated exposure valve over the alpha_008 wide-stop core
Hypothesis: alpha_008's always-in graded core SOLVED the +3.89% chop wall
(3.90 vs 3.89) but its base exposure never went to zero, so it absorbed
both down-windows in full (-2.38/-2.35 vs <=20% floor) and sat out the
+31% melt-up. Fix = MACRO VALVE, not a new core: keep the graded
continuous base exactly as in 008, but gate its SCALE by a trailing
7-day macro baseline — a rolling regression slope (rolling covariance of
close vs bar-index over 7 days, divided by rolling variance of the
index; no full-sample ops, no lookahead). Baseline slope <= 0 mutes the
base toward a small 0.05 floor (cash-ish, controlled bleed legal); a
positive baseline unlocks the full core, and a fast positive flip
(reclaim of the slope from below within 2 days) lets the signal rise
quickly enough to enter melt-up regimes early. Fast-cut downside
detector kept to sharpen the mute during multi-day distribution.
Entry frequency: with a rolling (not binary) valve, exposure stays > 0
in mixed regimes and the 0.15 Optuna threshold floor should fire more
than 008's 6 entries.
Charter rules attacked: DOWN_SHIELD (macro valve), extreme_participation
(fast unlock on slope reclaim), min_total_entries (rolling valve keeps
continuous exposure alive), uptrend_participation (core preserved).
Author: escalated cycle 3 (regime-gated exposure per alpha_008
next-idea + Gemini round-10), 2026-10-02.
Inputs: OHLCV. Provenance: tuner/runs/alpha_008_auto.json — down windows
-2.38/-2.35 absorbed in full; melt-up 0.0 vs bench +31.3; 6 entries.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]

    # ---------- macro baseline: trailing 7-day regression slope ----------
    n_bars = 7 * 24 * 4  # 7 days of 15m bars
    idx = pd.Series(np.arange(len(close), dtype=float), index=close.index)
    # slope(t) = cov(x, y over window) / var(x over window); x = bar index
    x_mean = idx.rolling(n_bars, min_periods=n_bars // 2).mean()
    y_mean = close.rolling(n_bars, min_periods=n_bars // 2).mean()
    cov_xy = ((idx - x_mean) * (close - y_mean)).rolling(
        n_bars, min_periods=n_bars // 2
    ).mean()
    var_x = ((idx - x_mean) ** 2).rolling(n_bars, min_periods=n_bars // 2).mean()
    slope = cov_xy / var_x.replace(0, 1e-9)
    # normalize slope by rolling price level to make tanh input bounded
    slope_n = slope / close.replace(0, 1e-9)
    slope_n = slope_n.replace([np.inf, -np.inf], 0).fillna(0)
    slope_n = slope_n.clip(-0.002, 0.002)

    # valve: baseline <= 0 -> 0.05 floor; baseline > 0 -> up to 1.0
    valve = 0.05 + 0.95 * (0.5 * (np.tanh(slope_n * 1500.0) + 1.0))

    # fast unlock: slope reclaiming from negative within last 2 days ->
    # let the valve rise quickly so melt-ups are entered early
    slope_below = (slope_n < 0).astype(float)
    was_recently_below = slope_below.rolling(2 * 96, min_periods=16).max()
    reclaim = (slope_n > 0) & (was_recently_below > 0)
    valve = valve.clip(lower=np.where(reclaim.fillna(False), 0.35, 0.05))

    # ---------- alpha_008 core, preserved ----------
    ema_f = close.ewm(span=32, min_periods=12).mean()
    ema_s = close.ewm(span=128, min_periods=40).mean()
    spread = (ema_f - ema_s) / close
    g_trend = 0.5 * (np.tanh((spread + 0.001) * 400.0) + 1.0)

    ret = close.pct_change()
    sigma = ret.rolling(48, min_periods=20).std().replace(0, 1e-9)
    down_fast = -(close.pct_change(4) / (sigma * np.sqrt(4)))
    cut = 0.5 * (np.tanh((down_fast - 1.2) / 0.8) + 1.0)

    mid = close.rolling(96, min_periods=32).mean()
    above = (close > mid).astype(float)
    conviction = above.rolling(96, min_periods=32).mean()

    dip = -(close.pct_change(8) / (sigma * np.sqrt(8)))
    dip_f = np.tanh(dip / 1.5)

    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr_pct = (tr.rolling(48, min_periods=20).mean() / close).replace(0, 0.001)
    calm = 0.5 * (np.tanh((0.006 - atr_pct) / 0.002) + 1.0)

    base = 0.15 + 0.30 * calm + 0.30 * conviction + 0.20 * dip_f

    # ---------- valve applied to the core ----------
    raw = base * valve * (0.25 + 0.75 * g_trend) * (1.0 - 0.9 * cut)
    sig = raw.ewm(span=32, min_periods=8).mean()

    return sig.clip(0.0, 1.0).fillna(0.0)
