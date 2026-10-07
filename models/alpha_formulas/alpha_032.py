"""
alpha_032 — trend-riding v3b: amplified low-gate Donchian ride (031 postmortem)
Hypothesis: same as alpha_031 (sustained-uptrend RIDING) but with the failure
mode fixed: alpha_031 produced 0 entries in ALL 4 windows — the multiplicative
gate chain (ride * regime * vol_conf * ewm-averaged persist) shrank the signal
below the tuner's minimum entry threshold. Fix: (i) additive/saturating gate
structure — take min(persist, regime) instead of multiplying all gates, so the
ride amplitude survives; (ii) explicit x2 amplification so mid-trend signal
sits near 0.6-1.0, well inside the tuner's trigger range; (iii) entry
threshold still soft (pos-0.45 on 1-day channel), chandelier trail persistence
for pullback-tolerant exits. All tanh inputs bounded; divisions guarded.
Rule attacked: UPTREND PARTICIPATION (strat >= 0.6*bench) + EXTREME (bench
>= +15% -> strat > 0) on the 4.5-year archive.
Author: auto-gen (isolated alpha loop), 2026-10-07. Priority 1, cycle 3 retry.
Provenance: alpha_031_auto.json (4/4 windows 0 entries, signal too weak);
alpha_025/026 (entry-threshold and harness lessons).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]

    # ATR (trailing, 15m bars)
    prev_close = close.shift(1)
    tr = np.maximum(
        high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs())
    )
    atr = tr.rolling(96, min_periods=30).mean().replace(0, 1e-9)

    # 1. Breakout state, soft threshold at mid-channel of a 1-day window
    hh = high.rolling(96, min_periods=40).max().shift(1)
    ll = low.rolling(96, min_periods=40).min().shift(1)
    chan = (hh - ll).replace(0, 1e-9)
    pos = (close - ll) / chan
    breakout = np.tanh((pos - 0.45) * 3.0).clip(lower=0.0)

    # 2. Chandelier persistence: trail = 1-day high - 2.5*ATR
    trail = high.rolling(96, min_periods=30).max() - 2.5 * atr
    above = np.tanh((close - trail) / atr)
    persist = 0.5 * (above.ewm(span=48, min_periods=10).mean() + 1.0)  # [0,1]

    # 3. Ride = fast memory of breakout while price holds above the trail
    ride = breakout.ewm(span=48, min_periods=10).mean()

    # 4. Down-shield as a MIN-gate (additive structure, not multiplicative)
    ema_f = close.ewm(span=96, min_periods=30).mean()
    ema_s = close.ewm(span=384, min_periods=100).mean()
    slope = (ema_f - ema_s) / atr
    regime = 0.6 + 0.4 * np.tanh(slope / 2.0)  # [0.2, 1.0]

    # 5. Volume conviction, saturating
    vol_rel = volume / volume.rolling(96, min_periods=30).mean().replace(0, 1e-9)
    vol_conf = 0.55 + 0.45 * np.tanh((vol_rel - 1.0) / 1.5)  # [0.1, 1.0]

    # Composite: min-gating preserves amplitude; x2 boost puts typical
    # mid-trend signal at 0.5-1.0 so the tuner can actually trigger entries.
    gate = np.minimum(np.minimum(persist, regime), vol_conf)
    sig = 2.0 * ride * gate
    return sig.clip(-1, 1).fillna(0.0)
