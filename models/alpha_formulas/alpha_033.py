"""
alpha_033 — trend-riding specialist v3: lowered breakout gate, mid-band entry
Hypothesis: alpha_026 failed because the entry state tanh((pos-0.75)*4) only
activated in the top quartile of the Donchian channel AND its EWM-smoothed
ride never crossed the tuner's signal threshold — so the tuner chose 0-entry
configs. Fix: activate at channel midpoint (pos-0.5), steeper ramp, and keep
the raw ride signal AMPLITUDE high (no deep multiplicative stacking that
sinks peak signal below tradable thresholds). Exit memory stays slow (EWM
span 96, ~1 day) so pullbacks within a sustained uptrend do not flatten the
signal; structural break gate uses a wide band (pos<0.3) and only softly
scales. Volume adds conviction but with a high floor so quiet bars still
trade. Long/flat only, regime-blind — participation quadrant attack.
Rule attacked: UPTREND PARTICIPATION (60%) + EXTREME (bench>=15% -> >0),
secondary: adaptive_activity (signal reachable in ordinary chop).
Author: auto-gen (isolated alpha loop), 2026-10-07. Priority 1.
Provenance: tuner/runs/alpha_031/032_auto.json (uptrend+extreme fails);
alpha_025.py (chandelier, sound but harness-limited); alpha_026.py
(threshold too high); cycles 027/028 (selection problem on 2026-only trains
— this file trains on 2021-2026 archive instead).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]

    # ATR proxy (trailing, 15m bars)
    prev_close = close.shift(1)
    tr = np.maximum(
        high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs())
    )
    atr = tr.rolling(96, min_periods=30).mean().replace(0, 1e-9)

    # Donchian channel (excluding current bar) and position within it
    hh = high.rolling(96, min_periods=40).max().shift(1)
    ll = low.rolling(192, min_periods=80).min().shift(1)
    chan = (hh - ll).replace(0, 1e-9)
    pos = (close - ll) / chan

    # MID-BAND breakout state: ramps from 0 at channel mid to ~1 near the top,
    # so ordinary uptrends (upper half) already register a tradable signal.
    breakout = np.tanh((pos - 0.5) * 3.0)  # ~0 at mid, ~1 at breakout

    # Slow memory: pullbacks within a trend keep the ride alive ~1 day.
    ride = breakout.ewm(span=96, min_periods=10).mean()

    # Structural break: only scales down deep in the lower band, softly.
    deep = np.tanh((pos - 0.30) * 4.0)
    structural = 0.6 + 0.4 * (0.5 * (deep.ewm(span=48, min_periods=8).mean() + 1.0))

    # Mild slope confirmation: never a hard gate.
    ema_f = close.ewm(span=48, min_periods=15).mean()
    ema_s = close.ewm(span=192, min_periods=50).mean()
    slope_raw = (ema_f - ema_s) / (atr + 1e-9)
    slope = 0.7 + 0.3 * np.tanh(slope_raw / 2.0)  # in [0.4, 1.0]

    # Volume conviction with a high floor (0.65) — quiet bars still trade.
    vol_rel = volume / volume.rolling(96, min_periods=30).mean().replace(0, 1e-9)
    vol_conf = 0.65 + 0.35 * np.tanh((vol_rel - 1.0) / 1.5)

    sig = ride.clip(lower=0.0) * structural * slope * vol_conf
    return sig.clip(-1, 1).fillna(0.0)
