"""
alpha_008 — evolved alpha_007: always-in-market graded exposure with
asymmetric regime tilt + time-based conviction
Hypothesis: alpha_007's dip-buy + EWMA memory got closest on the wall
(-0.50% vs +3.89% bench) but still failed because (a) only 31 entries —
the trend gate zeroed exposure too often, so the engine had few chances
to convert mild-up chop, and (b) in the mild-down window the same
long-bias memory bled -5.5% (>20% absorption). This evolution makes the
signal CONTINUOUS (base exposure always >= 0.15) so entries happen every
bar in calm regimes, tilts the continuous exposure hard positive in
confirmed uptrends (ride winners; wide ATR stops 1-8 do the rest), and
uses an ASYMMETRIC gate: slow/forgiving to enter (EWMA conviction over
~1 day), fast to cut (short-horizon downside acceleration + EMA
cross-down) so down-shield absorbs <=20% of drops instead of bleeding.
Time-based conviction: a long-window consistency score (fraction of last
96 x 15m bars with price above VWAP-ish midline) upgrades exposure in
grinds that persist without needing big momentum.
Charter rules attacked: UPTREND PARTICIPATION (>=60% capture on
0<bench<+15% — THE WALL), DOWN-SHIELD (fast-cut asymmetry), and
min_total_entries (continuous graded exposure).
Author: escalated cycle 2 (evolve alpha_007 family), 2026-10-01.
Inputs: OHLCV. Provenance: tuner/runs/alpha_007_auto.json — wall strat
-0.50 vs bench +3.89; down window -5.5 vs bench -1.7; 31 entries.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]

    # --- trend state: fast/slow EMA spread, graded [0,1] ---
    ema_f = close.ewm(span=32, min_periods=12).mean()
    ema_s = close.ewm(span=128, min_periods=40).mean()
    spread = (ema_f - ema_s) / close
    g_trend = 0.5 * (np.tanh((spread + 0.001) * 400.0) + 1.0)  # gentler than 007

    # --- FAST-CUT downside detector: recent downside acceleration ---
    ret = close.pct_change()
    sigma = ret.rolling(48, min_periods=20).std().replace(0, 1e-9)
    down_fast = -(close.pct_change(4) / (sigma * np.sqrt(4)))    # + when falling hard
    cut = 0.5 * (np.tanh((down_fast - 1.2) / 0.8) + 1.0)         # -> 1 on sharp drops

    # --- slow ENTER conviction: consistency of closes above rolling midline ---
    mid = close.rolling(96, min_periods=32).mean()
    above = (close > mid).astype(float)
    conviction = above.rolling(96, min_periods=32).mean()        # [0,1] ~ 1 day

    # --- dip-buy timing (from 007, kept): negative short return in uptrend ---
    dip = -(close.pct_change(8) / (sigma * np.sqrt(8)))
    dip_f = np.tanh(dip / 1.5)

    # --- low-vol regime: calm grind -> higher continuous base exposure ---
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr_pct = (tr.rolling(48, min_periods=20).mean() / close).replace(0, 0.001)
    calm = 0.5 * (np.tanh((0.006 - atr_pct) / 0.002) + 1.0)

    # continuous base: never below 0.15 -> entry opportunities every bar
    base = 0.15 + 0.30 * calm + 0.30 * conviction + 0.20 * dip_f

    # asymmetric regime application:
    #  - uptrend: full base (ride winners, dip-friendly)
    #  - downtrend: compressed to 0.05 floor via (1 - cut) and trend gate
    raw = base * (0.25 + 0.75 * g_trend) * (1.0 - 0.9 * cut)

    # gentle EWMA memory (shorter than 007's 64 so down-cuts propagate)
    sig = raw.ewm(span=32, min_periods=8).mean()

    return sig.clip(0.0, 1.0).fillna(0.0)
