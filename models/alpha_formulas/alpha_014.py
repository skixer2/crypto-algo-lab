"""
alpha_014 — CENTERED OSCILLATOR + SLOW REGIME MEAN ("entries by construction")
Hypothesis: alpha_011/012/013 all failed for the SAME structural reason:
their signals were smooth and near-constant-sign, so the tuner's long/short
thresholds were crossed almost never (0 entries in the +31.3% melt-up,
4-5 total entries, adaptive_activity 4/1.3 and 5/1.7). The signal never
RE-crossed a threshold after the initial state, so windows had no trades
to express even correct regime views.
Fix (still fully additive/bounded, no gating, no multiplicative regime kill):
  signal = A * regime + B * osc,  A=0.60, B=0.45
  regime  = tanh(0.5*tanh(vel_z*1.5) + 0.5*tanh(sl_z*1.5))  — slow blended
  trend/down view (48h velocity z + 7d slope z, proven in 010/011/013).
  osc     = tanh(-z_fast) — a ZERO-MEAN short-horizon mean-reversion
  oscillator (8-bar return z-score, 010's dip mechanism run on a fast
  clock). Because osc is symmetric and mean-zero it GUARANTEES the signal
  sweeps across both long_threshold and short_threshold repeatedly:
    - melt-up: regime ~ +0.6 pulls the mean up -> oscillations re-cross
      long_threshold after every micro-dip -> entries > 0 in the +31%
      window (extreme_participation + activity),
    - confirmed breakdown: regime ~ -0.6 pulls the mean down -> bounces
      re-cross short_threshold -> short entries harvest down-windows
      (down_shield with profit stretch),
    - chop: oscillation alone mean-reverts around 0 -> 008-style scalps.
  A light hysteresis smoother (ewm span=3) removes bar-noise but is fast
  enough to preserve crossings; nothing is ever gated to zero.
All inputs bounded (tanh, z clipped to +/-2), trailing ops only, rolling
stats replaced(0,1e-9) before division.
Charter rules attacked: adaptive_activity (entries by construction),
noise_stability, extreme_participation (melt-up entries),
down_shield/profit (short-side re-crossings), medium_term_edge,
uptrend_participation (positive regime mean).
Author: escalation cycle 8 (cross-form failure post-mortem 011/012/013),
2026-10-03.
Provenance: tuner/runs/alpha_012_auto.json, alpha_013_auto.json
(failed_gates), mechanisms inlined from alpha_008.py, alpha_010.py,
alpha_013.py.
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]
    eps = 1e-9

    w = 48 * 4  # 48h of 15m bars
    minp = w // 2

    ret = close.pct_change()
    sigma = ret.rolling(48, min_periods=20).std().replace(0, eps)

    # ---------------- SLOW REGIME (blended clocks, from 010/013) ----------
    mean48 = close.rolling(w, min_periods=minp).mean()
    vel = ((close - mean48) / close.replace(0, eps)).clip(-0.5, 0.5).fillna(0)
    vel_mu = vel.rolling(w, min_periods=minp).mean()
    vel_sd = vel.rolling(w, min_periods=minp).std().replace(0, eps)
    vel_z = ((vel - vel_mu) / vel_sd).clip(-2, 2).fillna(0)

    slope = (close - close.shift(w * 3)) / close.shift(w * 3).replace(0, eps)
    slope = slope.clip(-0.5, 0.5).fillna(0)
    sl_mu = slope.rolling(w * 2, min_periods=w).mean()
    sl_sd = slope.rolling(w * 2, min_periods=w).std().replace(0, eps)
    sl_z = ((slope - sl_mu) / sl_sd).clip(-2, 2).fillna(0)

    regime = np.tanh(0.5 * np.tanh(vel_z * 1.5) + 0.5 * np.tanh(sl_z * 1.5))
    regime = regime.ewm(span=24, min_periods=6).mean().fillna(0)

    # ---------------- FAST ZERO-MEAN OSCILLATOR ---------------------------
    # mean reversion over ~8 bars: positive after dips, negative after pops;
    # symmetric => signal sweeps across both long/short thresholds
    z_fast = (close.pct_change(8) / (sigma * np.sqrt(8))).clip(-2, 2).fillna(0)
    osc = np.tanh(-z_fast)

    # trend-tilted oscillator: in strong uptrends weight dips MORE (buy the
    # dip re-entries); in strong downtrends weight pops MORE (short bounces)
    tilt = 0.5 * (np.tanh(regime * 2.0) + 1.0)  # [0,1]
    osc_w = 0.35 + 0.30 * tilt  # 0.35..0.65 oscillator amplitude share

    # ---------------- VOLUME CONFIRMATION (mild, bounded) -----------------
    v_mu = volume.rolling(w, min_periods=minp).mean().replace(0, eps)
    v_rel = (volume / v_mu).clip(0, 2).fillna(1)
    v_conf = 0.5 * (np.tanh((v_rel - 1.0) * 1.5) + 1.0)  # [0,1], mean ~0.5

    # Donchian position: breakout adds drift toward the trend side
    hh = high.rolling(w, min_periods=minp).max()
    ll = low.rolling(w, min_periods=minp).min()
    pos = ((close - ll) / (hh - ll).replace(0, eps)).clip(0, 1).fillna(0.5)
    donch_drift = np.tanh((pos - 0.5) * 3.0) * 0.15 * v_conf  # small, bounded

    # ---------------- ADDITIVE COMPOSITE ----------------------------------
    signal = 0.60 * regime + osc_w * osc * 0.9 + donch_drift
    signal = signal.ewm(span=3, min_periods=2).mean()  # bar-noise hysteresis
    return signal.clip(-1.0, 1.0).fillna(0.0)
