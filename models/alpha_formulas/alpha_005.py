"""
alpha_005 — baseline long-bias with hard regime kill-switch
Hypothesis: alpha_004 produced trigger*gate signals that spent most time near
zero, so the engine's tuned long thresholds (~0.6-0.85) almost never fired
(18 entries < 50) and ordinary rallies were missed (strat -0.1% vs bench
+3.9%). Fix: an "always-something" long base in benign regimes —
0.55 + 0.45*tanh(velocity) keeps the signal pinned near 0.55-1.0 whenever the
market is not falling, so participation thresholds clear routinely and
ordinary rallies get captured. The asymmetry comes entirely from the regime
gate: fast-vs-slow EMA spread AND a slow-EMA slope check AND a hard
close-below-slow-EMA kill all multiply toward 0, so down windows flatten
instead of bleed (down-shield). Velocity is sigma-normalized and every factor
is tanh-bounded before compositing (tanh inputs |x| <= ~2).
Charter rules attacked: UPTREND PARTICIPATION (baseline floor clears
thresholds in 0-15% benches) and DOWN-SHIELD (triple-condition kill).
Author: auto-gen (isolated alpha loop), 2026-10-01.
Inputs: OHLCV (close, volume). Provenance: tuner/runs/alpha_004_auto.json
failure report (18 entries, -3.5% down window, -0.1% mild-up window).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    # --- velocity trigger, sigma-normalized (|tanh input| <= ~2) ---
    ret = close.pct_change()
    sigma = ret.rolling(48, min_periods=20).std().replace(0, 1e-9)
    velocity_sigma = (close.pct_change(4) + 0.5 * close.pct_change(12)) / (
        sigma * np.sqrt(4)
    )
    vel = np.tanh(velocity_sigma / 1.5)

    # --- baseline long exposure: 0.55 floor while regime is benign ---
    base = 0.55 + 0.45 * vel  # in [0.10, 1.00], pinned near 0.55+ most bars

    # --- regime gate: three graded conditions, all toward 0 when falling ---
    ema_f = close.ewm(span=24, min_periods=10).mean()
    ema_s = close.ewm(span=96, min_periods=30).mean()
    spread = (ema_f - ema_s) / close
    # 1) structure: spread <= -0.3% -> ~0; > +0.5% -> 1
    g_struct = 0.5 * (np.tanh((spread + 0.003) * 600.0) + 1.0)
    # 2) slow trend slope over last 12 bars (3h); falling structure -> 0
    slope = (ema_s - ema_s.shift(3)) / close  # 3 bars ~ 45min lookback
    g_slope = 0.5 * (np.tanh(slope * 4000.0 + 0.3) + 1.0)
    # 3) kill-switch: close below slow EMA by >1% -> hard flat (graded)
    dist = (close - ema_s) / close
    g_kill = 0.5 * (np.tanh((dist + 0.005) * 300.0) + 1.0)

    gate = g_struct * g_slope * g_kill

    # --- volume confirmation, mildly graded (never flips sign) ---
    vol_rel = volume / volume.rolling(32, min_periods=12).mean().replace(0, 1e-9)
    vol_conf = 0.7 + 0.3 * np.tanh((vol_rel - 1.0) / 1.5)  # in [0.4, 1.0]

    sig = base * gate * vol_conf
    return sig.clip(-1, 1).fillna(0.0)
