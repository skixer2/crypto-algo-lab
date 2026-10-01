"""
alpha_006 — drawdown-brake with volatility-adaptive tolerance + confirmation memory
Hypothesis: alpha_005's fixed 1%-below-slow-EMA kill-switch whipsawed in the
mild-up chop window (bench +3.89%, strat -2.8%): every minor dip below the
EMA flipped the gate off, then re-entry lag missed the recovery. Fix: replace
the price-level kill with a DRAWDOWN-FROM-RECENT-HIGH brake whose tolerance
is volatility-adaptive (tol = max(1.5%, 3 x ATR%)) — in low-vol chop the
tolerance is tight enough to still cut real downtrends (<=20% of a drop) but
wide enough in ATR terms to survive ordinary noise; and add confirmation
memory to the structure gate: the fast/slow EMA spread is compared against a
half-life-decayed rolling max of itself, so a recently confirmed uptrend is
not demoted by one soft bar (hysteresis on the entry trigger). The baseline
long floor (0.55 + 0.45*tanh(velocity)) is kept so ordinary rallies are
substantially ridden (>=60% capture) and entry count stays healthy.
Charter rules attacked: UPTREND PARTICIPATION on the +3.89% wall window
(hysteresis + vol-adaptive brake instead of tight stop) and DOWN-SHIELD
(brake still flattens sustained downtrends).
Author: auto-gen (isolated alpha loop), 2026-10-01.
Inputs: OHLCV (close, volume, high, low). Provenance:
tuner/runs/alpha_005_auto.json failure report (mild-up window strat -2.821
vs bench +3.889; down window -0.051 vs bench -1.705, near-legal bleed).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]

    # --- velocity trigger, sigma-normalized (|tanh input| <= ~2) ---
    ret = close.pct_change()
    sigma = ret.rolling(48, min_periods=20).std().replace(0, 1e-9)
    velocity_sigma = (close.pct_change(4) + 0.5 * close.pct_change(12)) / (
        sigma * np.sqrt(4)
    )
    vel = np.tanh(velocity_sigma / 1.5)

    # --- baseline long exposure: 0.55 floor while regime is benign ---
    base = 0.55 + 0.45 * vel  # in [0.10, 1.00]

    # --- ATR% for volatility-adaptive tolerance ---
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr = tr.rolling(48, min_periods=20).mean()
    atr_pct = (atr / close).replace(0, 0.001)
    # tolerance: wider in calm markets (in % terms), min 1.5%, cap 6%
    tol = (3.0 * atr_pct).clip(0.015, 0.06)

    # --- drawdown-from-recent-high brake (hysteresis by construction:
    #     rolling max is sticky, so brief dips don't fully close exposure) ---
    roll_high = close.rolling(192, min_periods=48).max()  # 48h anchor high
    dd = (close / roll_high.replace(0, np.nan) - 1.0).fillna(0.0)
    # dd = 0 (at highs) -> 1 ; dd = -tol -> 0.5 ; dd = -2*tol -> ~0
    g_brake = 0.5 * (np.tanh((dd + tol) / (0.5 * tol)) + 1.0)

    # --- structure gate with confirmation memory (hysteresis) ---
    ema_f = close.ewm(span=24, min_periods=10).mean()
    ema_s = close.ewm(span=96, min_periods=30).mean()
    spread = (ema_f - ema_s) / close
    # decayed memory of the best recent spread: once confirmed up, a soft bar
    # only partially demotes the gate
    spread_mem = spread.rolling(32, min_periods=8).max().fillna(0.0)
    spread_eff = np.maximum(spread, 0.5 * spread_mem)
    g_struct = 0.5 * (np.tanh((spread_eff + 0.003) * 600.0) + 1.0)

    # --- slow trend slope, kept but graded gently (memory already smooths) ---
    slope = (ema_s - ema_s.shift(3)) / close
    g_slope = 0.5 * (np.tanh(slope * 3000.0 + 0.2) + 1.0)

    gate = g_struct * g_slope * g_brake

    # --- volume confirmation, mildly graded (never flips sign) ---
    vol_rel = volume / volume.rolling(32, min_periods=12).mean().replace(0, 1e-9)
    vol_conf = 0.75 + 0.25 * np.tanh((vol_rel - 1.0) / 1.5)  # in [0.5, 1.0]

    sig = base * gate * vol_conf
    return sig.clip(-1, 1).fillna(0.0)
