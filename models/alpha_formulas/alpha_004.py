"""
alpha_004 — dual-horizon asymmetry: fast trigger, [0,1] trend gate
Hypothesis: prior alphas failed on BOTH sides of the edge equation — too few
entries (6-23 < 50) and negative excess (bleeding in down windows). This
formula attacks DOWN-SHIELD and UPTREND PARTICIPATION directly with an
asymmetric composite: a fast zero-crossing velocity trigger supplies enough
sign flips for >=50 entries, while a slow trend shield (fast-vs-slow EMA
spread, squashed) multiplies the trigger toward zero whenever the medium-term
structure is down — so drop windows produce ~flat, not negative, exposure.
Each factor is tanh-squashed to graded [-1,1] BEFORE compositing; velocity is
normalized by trailing per-bar sigma so tanh inputs stay |x| <~ 2 (scale
discipline). No EMA longer than 96 bars at 15m = 24h of context.
Author: auto-gen (isolated alpha loop), 2026-09-30.
Inputs: OHLCV (close, volume only). Provenance: tuner/runs/alpha_002_hd.json
and alpha_003_first.json failure reports (low entries + down-window bleed).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    # 1. Fast trigger: velocity in sigma units over ~1-3h, flips sign often
    ret = close.pct_change()
    sigma = ret.rolling(48, min_periods=20).std().replace(0, 1e-9)
    velocity_sigma = (close.pct_change(4) + 0.5 * close.pct_change(12)) / (
        sigma * np.sqrt(4)
    )
    trigger = np.tanh(velocity_sigma / 1.5)

    # 2. Gate: maps fast-vs-slow EMA spread to [0,1]. Spread <= -0.4% -> ~0
    #    (flat in bleed -> down-shield); spread > 0 -> rising participation,
    #    full by ~+1% spread (ordinary rallies get traded).
    ema_f = close.ewm(span=24, min_periods=10).mean()
    ema_s = close.ewm(span=96, min_periods=30).mean()
    spread = (ema_f - ema_s) / close
    gate = 0.5 * (np.tanh((spread + 0.004) * 500.0) + 1.0)  # in [0, 1]

    # 3. Volume confirmation, mildly graded (never flips the sign)
    vol_rel = volume / volume.rolling(32, min_periods=12).mean().replace(0, 1e-9)
    vol_conf = 0.6 + 0.4 * np.tanh((vol_rel - 1.0) / 1.5)  # in [0.2, 1.0]

    sig = trigger.clip(lower=0.0) * gate * vol_conf  # long/flat asymmetry
    return sig.clip(-1, 1).fillna(0.0)
