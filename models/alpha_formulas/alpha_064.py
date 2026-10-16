import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    """alpha_064 — RECOVERY-START DETECTOR (V-bottom buyer, P1 bull seat).

    Hypothesis: melt-up/recovery windows start from DEEP DRAWDOWN plus a
    FIRST STRUCTURAL RECLAIM. Buy the turn, not the trend: (1) deep
    drawdown state — close >15% below the trailing 30-day (2880-bar) high;
    (2) first reclaim — close crosses above the short Donchian mid (N=96);
    (3) post-spike vol compression — fast true-range ratio falling below
    its median (panic exhausting). While all three hold, emit a crisp
    binary +1.0 (no graded memory, no EWM decay — alpha_026 death mode);
    hold the full leg while close stays above the Donchian mid.

    Rule attacked: extreme_participation (bench>=15% -> strat>0; 063 was
    0.0 vs +56.95 bench in the 2022-07-15..08-14 V-recovery) and
    uptrend_participation (063 -3.45 vs +14.1 bench in 2023-10). Unlike
    the turtle latch (which needs a fresh N-bar-high breakout and latches
    too late / never in V-turns), this detector fires exactly at the turn.

    Author: alpha-generation-loop (JP charter v2 asymmetric, 2026-10-15)
    Provenance: tuner/runs/alpha_063_auto.json failed gates; JP P1(b)
    design 2026-10-11; 2022-08-style +62% recovery months as target.
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    eps = 1e-9

    # (1) Deep drawdown state vs trailing 30d high (trailing-only).
    rolling_high = high.rolling(2880, min_periods=288).max().shift(1)
    dd = (close / rolling_high.replace(0, eps) - 1.0).clip(-1.0, 0.0)
    deep_dd = (dd < -0.15).astype(float)

    # (2) Short Donchian mid and reclaim test (trailing-only via shift).
    dh = high.rolling(96, min_periods=24).max().shift(1)
    dl = low.rolling(96, min_periods=24).min().shift(1)
    mid = (dh + dl) / 2.0
    reclaim = (close > mid).astype(float)
    # "first": reclaim now but not 48 bars ago -> fresh turn, not old trend.
    fresh = (reclaim - reclaim.shift(48).fillna(0.0)).clip(0, 1)

    # (3) Post-spike vol compression: fast TR ratio below its own median.
    pc = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - pc).abs(),
        (low - pc).abs(),
    ], axis=1).max(axis=1)
    tr_fast = tr.rolling(8, min_periods=4).mean()
    tr_slow = tr.rolling(96, min_periods=24).mean().replace(0, eps)
    tr_ratio = (tr_fast / tr_slow).clip(0, 2)
    compress = (tr_ratio < 1.2).astype(float)

    # Crisp binary trigger: all three conditions on the same bar.
    trig = (deep_dd * reclaim * fresh * compress)

    # HOLD: once triggered, stay +1.0 while close holds above Donchian mid.
    raw = trig.values.astype(float)
    hold = np.zeros_like(raw)
    on = 0.0
    for i in range(len(raw)):
        if raw[i] > 0:
            on = 1.0
        elif close.values[i] <= mid.values[i]:
            on = 0.0
        hold[i] = on

    sig = pd.Series(hold, index=df.index)

    # Bounded volume confirmation at entry quality only (never exceeds 1).
    vma = volume.rolling(288, min_periods=48).mean().replace(0, eps)
    relv = (volume / vma).clip(0, 2)
    vol_conf = 0.85 + 0.075 * relv  # in [0.85, 1.0]
    sig = sig * vol_conf

    return pd.Series(np.clip(sig.values, 0.0, 1.0), index=df.index)
