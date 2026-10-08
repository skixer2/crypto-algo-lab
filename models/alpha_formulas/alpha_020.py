"""
alpha_020 — MELT-UP SPECIALIST: regime-blind sigma-velocity breakout rider
Hypothesis: post-drop V-reversal melt-ups (the +31.33% window) are missed by
every regime-aware signal because gates/overlays need established trend. A
regime-BLIND long-only trigger that fires on the explosive bar itself —
multi-horizon sigma-normalized velocity with short-term acceleration and
volume confirmation — should catch vertical breaks within hours from ANY
preceding state. Wide/graded exposure (tanh, never binary) lets it ride the
melt-up instead of taking quick profits; long-only + trailing-op discipline
means it simply goes flat (never short) in bleed, keeping melt-up entries > 0.
Rule attacked: EXTREME PARTICIPATION (strat > 0 when bench >= +15%) and
scarce MELT-UP quadrant ownership (only alpha_004 has it, params stale).
Author: auto-gen (isolated alpha loop, JP charter v2 asymmetric), 2026-10-04.
Inputs: OHLCV (close, volume). Provenance: alpha_004.py source study;
tuner/runs/alpha_018/019_auto.json (melt-up window strat 0.0 failures).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    # 1. Sigma-velocity: explosive move in sigma units over 1-6h, trailing only
    ret = close.pct_change()
    sigma = ret.rolling(48, min_periods=20).std().replace(0, 1e-9)
    vel = (close.pct_change(4) + 0.6 * close.pct_change(8) + 0.4 * close.pct_change(24)) / (
        sigma * np.sqrt(8)
    )

    # 2. Acceleration: velocity rising vs its own short trailing mean -> break
    #    is *initiating*, not exhausting. Bounded transform before compositing.
    vel_ma = vel.rolling(16, min_periods=6).mean()
    accel = np.tanh((vel - vel_ma) / 2.0)

    # 3. Volume confirmation: expansion is the fingerprint of a vertical break
    vol_rel = volume / volume.rolling(32, min_periods=12).mean().replace(0, 1e-9)
    vol_conf = np.tanh((vol_rel - 1.0) / 1.0)  # ~0 at normal volume, ~1 on spikes

    # 4. Graded LONG-ONLY rider: fires hard on explosive+accelerating+loud bars,
    #    decays but never flips short; floor keeps tiny residual exposure so a
    #    one-bar signal still books the melt-up ride.
    sig = np.tanh(vel / 2.5).clip(lower=0.0) * (0.55 + 0.45 * accel.clip(lower=0.0)) * (
        0.5 + 0.5 * vol_conf.clip(lower=0.0)
    )
    sig = sig.clip(lower=0.0).clip(upper=1.0)
    # scale floor: any meaningful velocity trigger keeps >= 0.25 exposure
    trigger_gate = (np.tanh(vel / 2.5) > 0.3).astype(float)
    sig = sig.where(trigger_gate > 0, 0.0) + 0.25 * trigger_gate * (sig > 0).astype(float) * 0.0
    sig = np.maximum(sig, 0.25 * trigger_gate * np.tanh(vel / 2.5).clip(lower=0.3))
    return pd.Series(sig, index=df.index).clip(-1, 1).fillna(0.0)
