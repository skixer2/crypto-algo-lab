"""
alpha_049 — RECOVERY-START DETECTOR: V-bottom first-reclaim buyer
Hypothesis (P1b, JP 2026-10-11): the pool lacks BULL SURFING. Alpha_048
(turtle latch) bought breakouts but was flat in the 2022-07 melt-up
(bench +57%, strat 0.0, 2 entries) because a 5-day Donchian high needs a
fresh high that V-bottoms never print early. Different skill: buy the FIRST
STRUCTURAL RECLAIM after a DEEP drawdown. Conditions (all trailing):
  (1) drawdown = close / rolling-max(close,30d) - 1 <= -15%  (deep hole)
  (2) FIRST reclaim: close crosses above short Donchian mid (2d) —
      latch ON while above; reset only when a NEW 30d-low regime prints
  (3) vol compression: fast TR (1d mean) < slow TR (5d mean) * 0.9 —
      post-spike calm confirms the capitulation is over
  (4) volume confirmation: reclaim bar volume > 1.2x rolling mean volume
Signal = +tanh(depth/10%) * gate, positive only; exactly 0 otherwise.
Amplitude scales with hole depth (deeper hole => stronger rebound).
Charter rules attacked: extreme_participation (bench >= +15% => strat > 0;
2022-08 style +62% recovery months) and uptrend_participation.
What NOT to do (alpha_026): no graded EWM memory; crisp regime latch.
Author: auto-gen (isolated alpha loop), 2026-10-11. P1b bull seat.
Provenance: tuner/runs/alpha_048_auto.json (extreme gate failed, strat 0.0
in +57% window); blender_v1b up-capture 0.06 lesson; alpha_035 (2-bar
confirmation structure lineage).
Inputs: OHLCV. Trailing ops only; bounded transforms; guarded divisions.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    eps = 1e-9

    # --- True range and ATR-like stats (trailing, guarded) ---
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    tr_fast = tr.rolling(96, min_periods=30).mean()            # 1 day of 15m bars
    tr_slow = tr.rolling(480, min_periods=120).mean()          # 5 days
    atr = tr_slow.replace(0, eps)

    # --- (1) Deep drawdown from 30d high ---
    hi_30d = close.rolling(2880, min_periods=720).max()
    dd = close / hi_30d.replace(0, eps) - 1.0                  # <= 0
    deep = (dd <= -0.15).astype(float)                          # hole >= 15%
    # Hole depth amplitude, bounded: deeper hole -> stronger expected rebound
    depth_amp = np.tanh((-dd / 0.10).clip(-2, 2))               # in [0, 1]

    # --- (2) First structural reclaim: 2d Donchian mid ---
    dc_hi = high.rolling(192, min_periods=60).max()
    dc_lo = low.rolling(192, min_periods=60).min()
    dc_mid = (dc_hi + dc_lo) / 2.0
    above_mid = (close > dc_mid).astype(float)
    # Latch: ON from first reclaim after a deep hole; stays on while above mid.
    # Reset when price prints a fresh 30d low (new leg down, V invalid).
    fresh_low = (close <= low.rolling(2880, min_periods=720).min().shift(1)).astype(float)
    latch = 0.0
    latches = []
    for a, d, f in zip(above_mid.values, deep.values, fresh_low.values):
        if f == 1.0:
            latch = 0.0
        elif d == 1.0 and a == 1.0:
            latch = 1.0
        elif latch == 1.0 and a == 1.0:
            latch = 1.0
        else:
            latch = 0.0
        latches.append(latch)
    latch = pd.Series(latches, index=close.index)

    # --- (3) Vol compression: post-spike calm ---
    calm = (tr_fast < tr_slow * 0.9).astype(float)

    # --- (4) Volume confirmation on the reclaim ---
    vol_ma = volume.rolling(960, min_periods=240).mean().replace(0, eps)
    vol_ok = (volume > 1.2 * vol_ma).astype(float)

    gate = latch * calm
    # Volume is confirmation, not a hard veto (thin holidays would kill entries)
    amp = (depth_amp * (0.7 + 0.3 * vol_ok)).clip(0, 1)

    sig = (gate * amp).clip(-1.0, 1.5)
    return sig.fillna(0.0)
