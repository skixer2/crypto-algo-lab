"""
alpha_012 — ADDITIVE composite: always-on graded long core + bounded
confirmed-breakdown SHORT overlay (composite v2 per JP directive 2026-10-02).
Hypothesis: alpha_011 failed all four buckets (-11.80%) because its
MULTIPLICATIVE layering — signal = core*(1-0.6*overlay) - 0.9*overlay —
let the regime gate strangle the core exactly at inflection points: the
+31.3% melt-up window got 0 entries (suppression muted participation)
and down-windows traded a half-dead core (-7.07 vs bench -1.71). The fix
is structural, not parametric: ADDITIVE blending with tanh-bounded
components —
  net = clip( 0.75*core + 0.25*short_overlay , -1, 1 )
The core (alpha_008 graded wide-stop engine: EWMA trend spread, price-vs-
mid conviction, calm-ATR tilt, dip bonus, fast-cut on 4h down-shock) is
ALWAYS on and can never be muted, so chop capture (008's 100%) and
uptrend/extreme participation are preserved by construction.
The short overlay only ADDS negative exposure after a CONFIRMED
breakdown: blended regime score (48h velocity z + 7d slope z, EWM
smoothed) negative on 2 consecutive evaluations. A structural reclaim
(close above 48h Donchian mid with 1.5x volume surge, or fast-EMA slope
flip above the mid) SUSPENDS the overlay instantly — but suspension only
removes the short contribution, never the core.
Both components are bounded by tanh BEFORE weighting so the net stays in
[-1, 1] and no component can gate the other.
Charter rules attacked: DOWN-SHIELD (overlay turns drops into reduced/
positive exposure), uptrend_participation & extreme_participation
(core never gated), medium_term_edge/consistency, min_total_entries
(always-in core).
Author: escalation cycle 6 (additive compositing v2), 2026-10-02.
Provenance: tuner/runs/alpha_011_auto.json (failure post-mortem),
alpha_008.py, alpha_010.py sources.
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]

    w = 48 * 4  # 48h of 15m bars
    minp = w // 2
    eps = 1e-9

    # ================= CORE (alpha_008 graded wide-stop engine) ==========
    ret = close.pct_change()
    sigma = ret.rolling(48, min_periods=20).std().replace(0, eps)

    ema_f = close.ewm(span=32, min_periods=12).mean()
    ema_s = close.ewm(span=128, min_periods=40).mean()
    spread = (ema_f - ema_s) / close.replace(0, eps)
    g_trend = 0.5 * (np.tanh((spread + 0.001) * 400.0) + 1.0)  # [0,1]

    mid = close.rolling(96, min_periods=32).mean()
    conviction = (close > mid).astype(float).rolling(96, min_periods=32).mean()

    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    atr_pct = tr.rolling(48, min_periods=20).mean() / close.replace(0, eps)
    atr_pct = atr_pct.replace(0, 0.001)
    calm = 0.5 * (np.tanh((0.006 - atr_pct) / 0.002) + 1.0)

    dip = np.tanh(-(close.pct_change(8) / (sigma * np.sqrt(8))).fillna(0) / 1.5)
    base = 0.15 + 0.30 * calm + 0.30 * conviction + 0.20 * dip

    # fast-cut: soften (not gate) the core in sharp drops
    down_fast = -(close.pct_change(4) / (sigma * np.sqrt(4))).fillna(0)
    cut = 0.5 * (np.tanh((down_fast - 1.2) / 0.8) + 1.0)
    raw_core = base * (0.35 + 0.65 * g_trend) * (1.0 - 0.5 * cut)
    # bounded long core in [0, 1]
    core = np.tanh(raw_core.ewm(span=32, min_periods=8).mean().fillna(0))

    # ============ CONFIRMED-BREAKDOWN REGIME SCORE ========================
    vol48 = ret.rolling(w, min_periods=minp).std().replace(0, eps)
    mean48 = close.rolling(w, min_periods=minp).mean()
    vel = ((close - mean48) / close.replace(0, eps)).clip(-0.5, 0.5).fillna(0)
    vel_mu = vel.rolling(w, min_periods=minp).mean()
    vel_sd = vel.rolling(w, min_periods=minp).std().replace(0, eps)
    vel_z = ((vel - vel_mu) / vel_sd).clip(-2, 2).fillna(0)

    slope = ((close - close.shift(w * 3)) / close.shift(w * 3).replace(0, eps))
    slope = slope.clip(-0.5, 0.5).fillna(0)
    sl_mu = slope.rolling(w * 2, min_periods=w).mean()
    sl_sd = slope.rolling(w * 2, min_periods=w).std().replace(0, eps)
    sl_z = ((slope - sl_mu) / sl_sd).clip(-2, 2).fillna(0)

    score = (0.5 * np.tanh(vel_z * 1.5) + 0.5 * np.tanh(sl_z * 1.5))
    score = score.ewm(span=16, min_periods=4).mean()
    neg = (score < 0).astype(float)
    confirmed = neg.rolling(2, min_periods=2).sum() >= 2

    # ============ RECLAIM SUPPRESSION (overlay-only, never the core) ======
    hh = high.rolling(w, min_periods=minp).max()
    ll = low.rolling(w, min_periods=minp).min()
    donch_mid = 0.5 * (hh + ll)
    above_mid = (close > donch_mid).astype(float)
    v_mu = volume.rolling(w, min_periods=minp).mean().replace(0, eps)
    v_surge = (volume / v_mu > 1.5).astype(float)
    breakout = above_mid * v_surge
    ema_f_slope = (ema_f - ema_f.shift(4)).fillna(0)
    slope_flip = (ema_f_slope > 0).astype(float)
    reclaim = np.clip(breakout + slope_flip * above_mid, 0.0, 1.0)

    # ============ SHORT OVERLAY (additive, bounded) =======================
    short_mag = 0.5 * (np.tanh((-score - 0.5) * 2.0) + 1.0)  # [0,1]
    overlay = (short_mag * confirmed.astype(float) * (1.0 - reclaim))
    overlay = np.tanh(overlay.ewm(span=8, min_periods=2).mean().fillna(0))

    # ============ ADDITIVE COMPOSITE (never gating) =======================
    signal = 0.75 * core + 0.25 * (-overlay)
    return signal.clip(-1.0, 1.0).fillna(0.0)
