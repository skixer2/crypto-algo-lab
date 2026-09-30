"""
alpha_003 — adaptive velocity trend inception (fast V-reversal capture)
Hypothesis: the archive's dominant loss window (ETH +31.33% week, Aug 16-23)
punished EMA200-lag bias filters ("Filter Lag Blindness"). This formula drops
slow moving averages entirely: conviction = velocity-in-sigmas x volume
acceleration, both squashed to graded [-1,1] bands BEFORE multiplication so
entry thresholds stay discriminative (scale discipline: tanh input kept in
its linear region, |x| <~ 2).
Regime target: violent trend inception / V-reversal expansions. Longest
lookback: 20 bars — no 200-bar anything.
Author: spec by Gemini (round 5), synthesized with scale corrections by
ZioClaw. The round-5 template (raw sigma-velocity x volume-surge x 1.5)
saturates tanh at +-1 on any decent move; here each factor is squashed first.
Inputs: OHLCV only. Provenance: Gemini round-5 spec + ZioClaw audit.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    # 1. Low-lag momentum velocity, in sigma units (adaptive: divides by
    #    trailing per-bar return std, so the same % move counts more in calm
    #    regimes — exactly the compression->expansion transition)
    mom = close.diff(3) + close.diff(12)
    per_bar_std = close.pct_change().rolling(20, min_periods=10).std().replace(0, 1e-9)
    velocity_sigma = mom / (close * per_bar_std)

    # 2. Squash each factor BEFORE compositing (graded, discriminative)
    v = np.tanh(velocity_sigma / 3.0)      # +-1 at ~3-sigma velocity
    surge = np.tanh(volume / volume.rolling(20, min_periods=10).mean()
                    .replace(0, 1e-9) / 2.0)  # +-1 at ~2x average volume

    # 3. Conviction = velocity x confirmation; product is bounded [-1, 1]
    return (v * surge).fillna(0.0)
