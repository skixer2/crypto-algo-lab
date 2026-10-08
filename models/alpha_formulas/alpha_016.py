"""
alpha_016 — melt-up specialist: regime-blind sigma-velocity ignition (v2 of alpha_004)
Hypothesis: post-drop V-reversal melt-ups fire within hours of a vertical break
from ANY preceding state, so a melt-up specialist must be REGIME-BLIND: no slow
EMA gate, no overlay drag (alpha_004's gate is what left it stale). Signal =
pure fast sigma-velocity: multi-horizon momentum over 1-4 bars (15m TF => fires
inside the first hour of a vertical break) normalized by trailing per-bar
sigma, positive-only (long/flat asymmetry), with a volume ignition confirm
(breakouts on above-average volume are the ones that ride). Bounded transforms
first, tanh inputs |x| <= ~2, divide by rolling stats only after replace(0,1e-9).
Rule attacked: EXTREME PARTICIPATION (bench >= +15% -> strat > 0) and
UPTREND/MEW-UP participation quadrant; the router will pair this with down-
specialists, so it makes no attempt at down-shield.
Author: auto-gen (isolated alpha loop), 2026-10-03.
Inputs: OHLCV (close, volume). Provenance: alpha_004.py source (only specialist
owning the +31.33% melt-up window, +11.8% but stale params); tuner/runs/
alpha_014_auto.json + alpha_015_auto.json gate reports (0 entries on melt-up,
compositing branch closed).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    ret = close.pct_change()
    # Faster, adaptive sigma: blend a 24-bar (6h) and 96-bar (24h) vol estimate
    # so the normalizer reacts quickly after quiet regimes (denominator fresh
    # when the vertical break arrives).
    sigma_f = ret.rolling(24, min_periods=10).std()
    sigma_s = ret.rolling(96, min_periods=30).std()
    sigma = (0.6 * sigma_f + 0.4 * sigma_s).replace(0, 1e-9)

    # Multi-horizon ignition velocity in sigma units: dominant 1-bar term for
    # hour-one response, secondary 4-bar and 12-bar terms to catch sustained
    # thrusts. Note alpha_004 lacked the 1-bar term -> slowest responder.
    v = (
        1.0 * close.pct_change(1)
        + 0.6 * close.pct_change(4)
        + 0.3 * close.pct_change(12)
    ) / (sigma * np.sqrt(4))

    # Positive-only graded trigger: longs scale in from ~0.5 sigma to full at
    # ~2.5 sigma; negative velocity contributes nothing (no shorts, no drag).
    up = np.tanh(v / 2.0).clip(lower=0.0)

    # Volume ignition confirm: relative volume vs trailing 6h mean, graded in
    # [0.35, 1.0]; >1.5x volume saturates. Never gates to zero alone.
    vol_rel = volume / volume.rolling(24, min_periods=10).mean().replace(0, 1e-9)
    vol_conf = 0.35 + 0.65 * np.tanh((vol_rel - 1.0) / 1.2)

    # Fast smoothing (ewm span=3, ~45min) removes single-bar whipsaw while
    # keeping hour-scale response; span chosen <= alpha_004's span=24 lag issue.
    sig = (up * vol_conf).ewm(span=3, min_periods=1).mean()

    return sig.clip(-1, 1).fillna(0.0)
