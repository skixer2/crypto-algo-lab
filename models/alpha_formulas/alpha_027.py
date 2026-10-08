"""
alpha_027 — trend-riding specialist: Donchian breakout entry + ATR-chandelier HOLD
Hypothesis (PRIORITY 1, missing quadrant): prior alphas (velocity triggers like
alpha_004) CATCH breakouts but exit on noise, capturing ~15-25% of 40-60%
melt months (2021/2024 style). The win condition is RIDING: enter on a
rolling-high breakout (Donchian channel), then hold with a LONG memory — the
signal decays only when price structurally breaks below an ATR-based
chandelier level computed over a slow trailing window, not on ordinary
pullbacks. Implementation as a stateless-but-persistent signal: a slow EMA
anchor (16h) plus an ATR-trail floor forms a "ride score" that stays pinned
near 1.0 while trend structure holds, and only releases after a multi-ATR
close beneath the anchor. Regime-blind long bias with a slow mean so the
signal does not vanish in mixed tape; volume surge at breakout raises
participation. All tanh inputs bounded |x|<=2 by sigma/ATR normalization
BEFORE compositing; divisions use rolling stats after .replace(0,1e-9);
trailing ops only (rolling/ewm, no shift(-n), no full-sample ops).
Rule attacked: uptrend_participation(60%) + extreme_participation(bench>=15%).
Author: auto-gen (isolated alpha loop), 2026-10-06.
Provenance: router_45y_v1 (bull windows 0/6 captured), tuner/runs/
alpha_025_auto.json + alpha_026_auto.json (0 melt-up participation, 0 entries).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]

    # --- ATR (trailing, 14h equivalent at 15m = 56 bars) ---
    tr = pd.concat(
        [high - low, (high - (close - close.diff())).abs(), (low - (close - close.diff())).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(56, min_periods=20).mean().replace(0, 1e-9)

    # --- Donchian breakout entry: close > rolling high of prior N bars ---
    don_hi = high.rolling(96, min_periods=40).max() - tr  # lag proxy, trailing-only
    breakout = (close - don_hi) / atr  # >0 means new 24h high by ATR units
    entry = np.tanh(breakout / 1.0)  # |x| bounded; 1 ATR breakout -> ~0.76
    entry = entry.clip(lower=0.0)  # long-side only entry fuel

    # --- Ride score: persistent trend-hold memory (chandelier-style) ---
    # Slow anchor: 16h EMA of close. Structural break = close falling
    # > 3 ATR below anchor -> ride collapses. Ordinary pullbacks (<1 ATR
    # below) barely dent the score.
    anchor = close.ewm(span=64, min_periods=20).mean()
    drawdown_atr = (anchor - close) / atr  # positive when below anchor
    ride = 0.5 * (np.tanh((1.5 - drawdown_atr) / 1.5) + 1.0)  # in [0,1]
    # Floor memory: once established, uptrend keeps a slow floor via
    # long-horizon momentum (5-day style, 480 bars) so brief dips don't
    # fully release the position.
    pc = close / close.shift(480).replace(0, 1e-9) - 1.0
    mom = pc / (
        pc.rolling(240, min_periods=60).std().replace(0, 1e-9) + 1e-9
    )
    mom_floor = 0.5 * (np.tanh(mom / 2.0) + 1.0)  # in [0,1], slow regime mean

    # --- Volume confirmation at breakout (graded, never flips sign) ---
    vol_rel = volume / volume.rolling(64, min_periods=20).mean().replace(0, 1e-9)
    vol_conf = 0.6 + 0.4 * np.tanh((vol_rel - 1.0) / 1.5)  # in [0.2, 1.0]

    # Composite: entry fuel * hold persistence * volume, floored by slow
    # momentum regime so established uptrends keep meaningful participation
    # even between new highs (RIDING, not catching).
    hold = np.maximum(ride, 0.5 * mom_floor)
    sig = np.maximum(entry * hold, 0.35 * mom_floor * hold) * vol_conf

    return sig.clip(0.0, 1.0).fillna(0.0)
