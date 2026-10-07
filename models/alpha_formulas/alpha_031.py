"""
alpha_031 — trend-riding specialist v3: low-bar Donchian breakout, chandelier trail memory
Hypothesis: the missing quadrant is sustained-uptrend RIDING (+40-60% months,
2021/2024-style). alpha_026's entry gate tanh((pos-0.75)*4) required price in
the top 25% of a 2-day channel — too high, the tuner never crossed it. Fix:
(i) entry threshold at pos-0.45 (price above mid-channel counts), (ii) shorter
breakout lookback (1 day) so breakouts register sooner, (iii) chandelier-style
persistence: signal stays on while close > trailing Donchian-high - k*ATR, a
pullback-tolerant structural exit rather than a noise flip. Volume surge on
breakout adds conviction; mild slow-slope softener keeps some down-shield
without gating ordinary chop. All inputs bounded via tanh after ATR/channel
normalization; divisions guarded with .replace(0, 1e-9).
Rule attacked: UPTREND PARTICIPATION (strat >= 0.6*bench) + EXTREME (bench
>= +15% -> strat > 0) on the 4.5-year archive (valid months 2021-07, 2022-10,
2024-01, 2025-04, 2026-07 — 2021/2024 should give ride-configs winning trains).
Author: auto-gen (isolated alpha loop), 2026-10-07. Priority 1 attack, cycle 3.
Provenance: alpha_025 (chandelier, sound but harness-limited), alpha_026
(memory decay, entry threshold too high); tuner/runs/router_45y_v1/v2
(down 4/4 positive, bull windows 0/6 — this attacks the bull zero).
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

    # 1. Breakout state on a 1-day channel, entry threshold at mid-channel
    #    (026 used 0.75 on a 2-day channel — never fired).
    hh = high.rolling(96, min_periods=40).max().shift(1)
    ll = low.rolling(96, min_periods=40).min().shift(1)
    chan = (hh - ll).replace(0, 1e-9)
    pos = (close - ll) / chan
    breakout = np.tanh((pos - 0.45) * 3.0)  # ~0 at mid, ~1 in upper quartile

    # 2. Chandelier persistence: trail = 1-day high - 2.5*ATR; price above
    #    trail keeps the ride alive through pullbacks (structural exit only).
    trail = high.rolling(96, min_periods=30).max() - 2.5 * atr
    above = np.tanh((close - trail) / atr)  # >0 comfortably above trail
    persist = 0.5 * (above.ewm(span=48, min_periods=10).mean() + 1.0)  # [0,1]

    # 3. Slow memory so a single dip below trail doesn't kill the position
    ride = (breakout.clip(lower=0.0) * persist).ewm(span=96, min_periods=10).mean()

    # 4. Mild down-shield: slow EMA spread in ATR units; never a hard gate
    ema_f = close.ewm(span=96, min_periods=30).mean()
    ema_s = close.ewm(span=384, min_periods=100).mean()
    slope = (ema_f - ema_s) / atr
    regime = 0.6 + 0.4 * np.tanh(slope / 2.0)  # in [0.2, 1.0]

    # 5. Volume conviction at breakout, graded
    vol_rel = volume / volume.rolling(96, min_periods=30).mean().replace(0, 1e-9)
    vol_conf = 0.55 + 0.45 * np.tanh((vol_rel - 1.0) / 1.5)  # in [0.1, 1.0]

    sig = ride.clip(lower=0.0) * regime * vol_conf
    return sig.clip(-1, 1).fillna(0.0)
