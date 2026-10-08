"""
alpha_029 — trend-riding specialist v3: low-threshold breakout + persistent memory
Hypothesis: alpha_026 failed because its entry gate tanh((pos-0.75)*4) only
meaningfully activated at the top ~10% of the channel, and the EWM of an
already-rare activation never crossed the tuned signal threshold -> 2 entries.
Fix: activation at pos>0.5 (upper half), steeper effective memory via
sum-of-decays (capped EWMA that saturates at repeated upper-half closes),
so pullbacks preserve the position but fresh upper-half closes re-arm it.
Down-shield: graded slow-slope softener scales to ~0 in deep downtrends
rather than a hard gate, preserving participation in bull windows.
Scale discipline: |tanh inputs| <= 2 (pos in [0,1], ratios normalized by
channel width / sigma); divisions guarded with .replace(0, 1e-9).
Rule attacked: UPTREND PARTICIPATION (60%), EXTREME (bench>=15% -> >0),
ADAPTIVE ACTIVITY (>=8 total entries).
Author: auto-gen (isolated alpha loop), 2026-10-07. Priority 1 attack.
Provenance: alpha_026 (threshold never crossed); alpha_025 (chandelier sound,
harness-limited); tuner/runs/alpha_027/028 (extreme bucket 0 entries on +31%).
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    # Channel position over trailing 24h (excl. current bar): 0=bottom, 1=top
    hh = close.rolling(96, min_periods=40).max().shift(1)
    ll = close.rolling(192, min_periods=80).min().shift(1)
    chan = (hh - ll).replace(0, 1e-9)
    pos = (close - ll) / chan

    # LOW-threshold breakout activation: fires in the upper half of channel
    breakout = np.tanh((pos - 0.5) * 2.0).clip(lower=0.0)  # 0 at mid, ~0.76 near top

    # Persistent memory: capped fast+slow decay mix — re-arms on every
    # upper-half close but decays over ~1-2 days, so pullbacks don't kill it.
    fast_mem = breakout.ewm(span=96, min_periods=10).mean()   # ~24h
    slow_mem = breakout.ewm(span=384, min_periods=30).mean()  # ~4d anchor
    ride = (0.6 * fast_mem + 0.4 * slow_mem).clip(upper=1.0)

    # Structural exit: only if price sinks to lower third of channel
    deep_break = np.tanh((pos - 0.33) * 2.0)                  # -1 if falling apart
    structural = 0.5 * (deep_break.ewm(span=96, min_periods=10).mean() + 1.0)

    # Soft regime: slow EMA slope in ATR units; ~0 exposure only in deep downtrend
    prev_close = close.shift(1)
    tr = np.maximum(
        high_low := df["high"] - df["low"],
        np.maximum((df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()),
    )
    atr = tr.rolling(96, min_periods=30).mean().replace(0, 1e-9)
    ema_f = close.ewm(span=96, min_periods=30).mean()
    ema_s = close.ewm(span=384, min_periods=100).mean()
    slope = (ema_f - ema_s) / atr
    regime = 0.5 * (np.tanh((slope + 1.0) / 1.0) + 1.0)  # in [0,1], loose

    # Volume conviction: surge boosts, quiet fades gently (floor keeps active)
    vol_rel = volume / volume.rolling(96, min_periods=30).mean().replace(0, 1e-9)
    vol_conf = 0.55 + 0.45 * np.tanh((vol_rel - 1.0) / 1.5)

    sig = ride * structural * (0.3 + 0.7 * regime) * vol_conf
    return sig.clip(-1, 1).fillna(0.0)
