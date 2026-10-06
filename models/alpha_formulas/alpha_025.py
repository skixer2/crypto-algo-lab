"""
alpha_025 — chandelier trend-riding specialist
Hypothesis: the missing quadrant is sustained-uptrend RIDING (2021/2024-style
+40-60% months). Spike-catching velocity triggers (alpha_004) enter late and
exit on noise, capturing ~15% of a melt-up month. Instead we emulate a
chandelier/ATR trailing-stop long: trail = max(rolling high, N) - k*ATR(N).
Signal is a graded function of (close - trail)/ATR: it saturates near full
exposure while price holds above the trail (riding pullbacks), decays
smoothly as price approaches the trail, and goes flat only on structural
break — no per-bar noise exit. A slow EMA slope gate (~6h) softly scales
exposure toward zero only in deep downtrends (down-shield), keeping the
strategy regime-blind in ordinary chop so bull windows get participation.
Graded tanh outputs in [-1,1] before compositing; inputs bounded |x|<~2 by
ATR/sigma normalization. Volume confirmation boosts entries on expansion.
Author: auto-gen (isolated alpha loop), 2026-10-06. Priority 1 attack.
Provenance: router_45y_v1/v2 (down 4/4 positive, bull 0/6);
alpha_024 (extreme bucket pass +7.9 on +31.3 bench, uptrend fail).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, volume = df["close"], df["high"], df["volume"]

    # ATR proxy (trailing, 15m bars): 96 bars = 24h structure
    prev_close = close.shift(1)
    tr = np.maximum(
        high - df["low"], np.maximum((high - prev_close).abs(), (df["low"] - prev_close).abs())
    )
    atr = tr.rolling(96, min_periods=30).mean().replace(0, 1e-9)

    # Chandelier trail: Donchian high over 24h minus 3*ATR
    donchian_high = high.rolling(96, min_periods=30).max()
    trail = donchian_high - 3.0 * tr.rolling(96, min_periods=30).mean()

    # Riding signal: +1 while well above trail, decays to 0 at the trail,
    # negative only below (structural break) — clipped to long/flat asymmetry.
    ride_raw = (close - trail) / (2.0 * atr)
    ride = np.tanh(ride_raw)  # |ride_raw| typically < 2 in trends

    # Slow regime softener: 6h EMA slope in ATR units; deep downtrend -> ~0
    ema_f = close.ewm(span=24, min_periods=10).mean()
    ema_s = close.ewm(span=96, min_periods=30).mean()
    slope = (ema_f - ema_s) / atr
    regime = 0.5 * (np.tanh((slope + 0.5) / 1.0) + 1.0)  # in [0,1]

    # Volume expansion confirmation, graded, never flips sign
    vol_rel = volume / volume.rolling(64, min_periods=20).mean().replace(0, 1e-9)
    vol_conf = 0.7 + 0.3 * np.tanh((vol_rel - 1.0) / 1.5)  # in [0.4, 1.0]

    sig = ride.clip(lower=0.0) * (0.25 + 0.75 * regime) * vol_conf
    return sig.clip(-1, 1).fillna(0.0)
