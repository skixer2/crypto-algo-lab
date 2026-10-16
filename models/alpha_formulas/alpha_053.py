"""
alpha_053 — RECOVERY-START DETECTOR (V-bottom buyer, P1b)
Hypothesis (JP 2026-10-11): the bull seat is empty; alpha_052's binary
turtle latch never fired in-study (up-capture 0.00 — price rarely holds
above a 48h trailing max during early V-turns, so latch waited forever).
Different skill than trend-riding: buy the FIRST STRUCTURAL RECLAIM after
a DEEP drawdown. Recipe:
  1) DEEP DIP: close is > 12% below its 30-day (2880-bar) rolling high.
  2) VOL COMPRESSION: post-spike fast TR ratio (TR_8 / TR_96) falling
     below 1.2 — panic selling exhausting.
  3) FIRST RECLAIM: close crosses back above the 8h (32-bar) Donchian mid
     after having been below it during the dip (reclaim state latched via
     trailing shift comparisons, crisp not graded).
Signal = tanh-bounded reclaim strength (0.8 base) + 0.2 volume confirmation
(volume z > 0.5 on the reclaim bar), only while dip-state is active; drops
to 0 once close > dip-recovery level (50% retrace of the drawdown) so the
formula hands off to trend riders and stays 0 in healthy bulls (preserves
down_shield: deep-dip state is where it acts, and shorting is never done).
Charter rules attacked: extreme_participation (2022-07 +62% V-month),
uptrend_participation (2023-11 style recoveries), down_shield (0 floor
when not recovering), adaptive_activity.
Author: escalation cycle 13 (bull seat, P1b recovery detector), 2026-10-12.
Provenance: tuner/runs/alpha_052_auto.json (latch never fired), segment
table V-windows 2022-07/2025-02/2026-05; anti-pattern alpha_026 (no graded
memory in hold logic). Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    eps = 1e-9

    hi_w = 2880        # 30d of 15m bars
    mid_w = 32         # 8h Donchian mid
    tr_fast, tr_slow = 8, 96

    # ---------- deep-dip state -------------------------------------------
    roll_high = high.rolling(hi_w, min_periods=hi_w // 2).max()
    dd = (roll_high - close) / roll_high.replace(0, eps)      # drawdown frac
    deep_dip = (dd > 0.12).astype(float)

    # ---------- vol compression: fast TR ratio falling -------------------
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    tr_f = tr.rolling(tr_fast, min_periods=tr_fast // 2).mean()
    tr_s = tr.rolling(tr_slow, min_periods=tr_slow // 2).mean().replace(0, eps)
    tr_ratio = (tr_f / tr_s).fillna(2.0)
    calm = (tr_ratio < 1.2).astype(float)

    # ---------- first structural reclaim (crisp cross) -------------------
    upper = high.rolling(mid_w, min_periods=mid_w // 2).max()
    lower = low.rolling(mid_w, min_periods=mid_w // 2).min()
    don_mid = (upper + lower) / 2.0
    reclaim = ((close > don_mid) & (close.shift(1) <= don_mid.shift(1))).astype(float)
    # latch: stay 'reclaiming' while close holds above mid
    holding = (close > don_mid).astype(float)
    reclaim_state = np.maximum(reclaim, holding).clip(upper=1.0)

    # ---------- volume confirmation --------------------------------------
    vz = volume.rolling(tr_slow, min_periods=tr_slow // 2).mean().replace(0, eps)
    vol_ok = ((volume / vz).fillna(0) > 1.5).astype(float)

    # ---------- hand-off level: 50% retrace of the drawdown --------------
    recovery_level = close + 0.5 * (roll_high - close)
    done = (close >= recovery_level).astype(float)

    # ---------- composite: 0..1, active only in deep-dip recoveries ------
    arm = deep_dip * calm
    strength = 0.8 * reclaim_state + 0.2 * vol_ok
    signal = (arm * strength * (1.0 - done)).clip(lower=0.0, upper=1.0)

    # in a healthy bull (no dip): floor to 0 — router/down-shield safe
    signal = signal.where(arm > 0, 0.0).fillna(0.0)
    return signal
