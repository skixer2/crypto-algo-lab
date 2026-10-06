"""
alpha_026 — trend-riding specialist: Donchian breakout entries, slow decay exit
Hypothesis: the missing quadrant is sustained-uptrend RIDING. Spike-catching
velocity triggers (alpha_004 lineage) enter late and exit on noise, capturing
~15-25% of +40-60% months. This formula replaces the fast trigger with a
rolling Donchian-channel breakout state: once price closes above the N-bar
high, the signal turns on and DECAYS SLOWLY (multi-day EWM memory) instead of
flipping off at the first pullback — exit only when price structurally breaks
below a wider trailing channel. Volume surge at breakout raises conviction;
no volume, gradual fade. Long/flat only, regime-blind.
Scale discipline: every tanh input normalized by rolling sigma or channel
width, |x| <= ~2 before squashing. Divisions guarded with .replace(0, 1e-9).
Rule attacked: UPTREND PARTICIPATION (60%) + EXTREME (bench>=15% -> >0).
Author: auto-gen (isolated alpha loop), 2026-10-06.
Provenance: router_45y_v1 (down 4/4 positive, bull 0/6); tuner/runs/
alpha_024_auto.json + alpha_025_auto.json (uptrend_participation failures);
alpha_004.py entry-side study.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    # 1. Breakout state: close vs trailing N-bar Donchian high (excl. current).
    #    Breaking above the channel -> state ramps toward 1 and holds.
    hh = close.rolling(96, min_periods=40).max().shift(1)
    ll = close.rolling(192, min_periods=80).min().shift(1)
    chan = (hh - ll).replace(0, 1e-9)

    # Position within channel, squashed: >0.5 means upper half, breakout near 1
    pos = (close - ll) / chan
    breakout = np.tanh((pos - 0.75) * 4.0)  # 0 at 75% of channel, ~1 at breakout

    # 2. SLOW memory: multi-day EWM so pullbacks don't kill the position.
    #    Structural exit: also decay if price sinks deep into the channel.
    ride = breakout.ewm(span=192, min_periods=10).mean()          # ~2 days @15m
    deep_break = np.tanh((pos - 0.35) * 4.0)                      # -1 if falling apart
    structural = 0.5 * (deep_break.ewm(span=96, min_periods=10).mean() + 1.0)

    # 3. Trend slope confirmation: slow EMA spread, mild gate (never kills ride)
    ema_f = close.ewm(span=96, min_periods=30).mean()
    ema_s = close.ewm(span=384, min_periods=100).mean()
    ret = close.pct_change()
    sigma = ret.rolling(192, min_periods=50).std().replace(0, 1e-9)
    spread_sigma = (ema_f - ema_s) / (close * sigma * np.sqrt(96) + 1e-9)
    slope = 0.5 + 0.5 * np.tanh(spread_sigma / 1.5)  # in [0, 1]

    # 4. Volume conviction: surge at/after breakout boosts; quiet fades slowly
    vol_rel = volume / volume.rolling(96, min_periods=30).mean().replace(0, 1e-9)
    vol_conf = 0.55 + 0.45 * np.tanh((vol_rel - 1.0) / 1.5)  # in [0.1, 1.0]

    # Composite: ride state gated by structure and slope, modulated by volume.
    # Long/flat asymmetric: negative breakout periods contribute ~0.
    sig = ride.clip(lower=0.0) * structural * (0.4 + 0.6 * slope) * vol_conf
    return sig.clip(-1, 1).fillna(0.0)
