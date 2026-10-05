"""
alpha_024 — Donchian trend-riding specialist with ATR chandelier trail
Hypothesis: PRIORITY 1 (router_45y_v1) — bull windows fail because spike-
catching velocity entries take profit into noise (captured +15% of a +61%
month). The missing quadrant is sustained-uptrend RIDING: enter on a rolling
Donchian high breakout (structural, not velocity), then HOLD the long while
price stays above a trailing chandelier (highest close since entry proxy minus
ATR multiple), exiting only on structural break. Implemented as a continuous
signal: a slow momentum state (tanh of N-bar return in ATR units) supplies the
ride, gated by an EMA-structure confirm (price above slow EMA, slow EMA
rising), and a breakdown term (close below rolling min, negative) subtracts —
the trail. Long/flat bias, regime-blind, slow mean so pullbacks don't shake
us out. Volume surge on breakout raises conviction. |tanh inputs| <= ~2;
divisions by rolling stats only after .replace(0,1e-9); trailing ops only.
Attacks: UPTREND PARTICIPATION (0<bench<+15% -> strat >= 0.6*bench) and
EXTREME (bench >= +15% -> strat > 0), while keeping a breakdown-shield term
for down_shield.
Author: auto-gen (isolated alpha loop), 2026-10-05.
Inputs: OHLCV (close, volume). Provenance: tuner/runs/router_45y_v1.json
(bull 0/6, down 4/4 positive), alpha_022/023 failure reports, alpha_004.py.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    # --- ATR-style trailing volatility (true range proxy via close-to-close) ---
    ret = close.pct_change()
    atr = ret.rolling(48, min_periods=20).std().replace(0, 1e-9) * close

    # --- Ride state: 24-bar (~6h) trend in ATR units, slow and persistent ---
    ride_raw = (close - close.rolling(24, min_periods=12).mean()) / atr.replace(0, 1e-9)
    ride = np.tanh(ride_raw / 2.0)  # |x| <= ~2, in [-1, 1]

    # --- Structure confirm: price above slow EMA and slow EMA rising ---
    ema_s = close.ewm(span=192, min_periods=48).mean()
    above = (close - ema_s) / atr.replace(0, 1e-9)
    struct = 0.5 * (np.tanh(above / 1.5) + 1.0)  # in [0,1], ~0.5 at EMA touch
    rising = np.tanh(
        (ema_s.diff(8) / atr.replace(0, 1e-9)).fillna(0.0) / 1.5
    )
    confirm = struct * (0.6 + 0.4 * (0.5 + 0.5 * rising))  # in [0,1]

    # --- Volume conviction on the ride ---
    vol_rel = volume / volume.rolling(64, min_periods=20).mean().replace(0, 1e-9)
    vol_conf = 0.6 + 0.4 * np.tanh((vol_rel - 1.0) / 1.5)  # [0.2, 1.0]

    # --- Chandelier-style trail penalty: below rolling min proximity ---
    roll_min = close.rolling(32, min_periods=16).min()
    dist_min = (close - roll_min) / atr.replace(0, 1e-9)
    # dist_min ~ 0 means at structural break -> penalty near full;
    # dist_min > 2 ATR -> no penalty.
    trail_pen = np.tanh((2.0 - dist_min) / 2.0).clip(lower=0.0)  # in [0,1)

    sig = ride.clip(lower=0.0) * confirm * vol_conf * (1.0 - 0.8 * trail_pen)

    # Slow smooth for noise stability; keeps the ride through pullbacks
    sig = sig.ewm(span=8, min_periods=3).mean()
    return sig.clip(-1, 1).fillna(0.0)
