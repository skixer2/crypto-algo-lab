"""
alpha_013 — ADDITIVE composite v3: "momentum-floor core + graded short sink"
Hypothesis: alpha_012's additive v2 fixed the gating catastrophe but still
failed because (a) the core signal sat BELOW the tuner's long_threshold
during the +31.3% melt-up (0 entries — a bounded-tanh core plateaus near
its cap and triggers almost no threshold crossings), (b) down-windows
still bled -1.07/-1.705 because a fixed w_short=0.25 weight is too weak to
offset a long core that stays ~0.15-0.3 alive in confirmed drops (capital
floor needs strat >= 0.2*bench), and (c) a smooth ewm-smoothed core
produced only 5 entries total (adaptive_activity 5/1.7, noise stability
fail from near-constant signal).
Fix, all additive/bounded, no gating:
  CORE (always on, always >= small positive floor): alpha_008-style graded
  engine PLUS a breakout-momentum term (Donchian-upper proximity x volume
  surge) so melt-ups push the core decisively ABOVE tunable thresholds,
  and light re-excitation (7d-high pullback re-entry kicker) so entries
  keep firing in trends instead of one smooth ride.
  SHORT SINK (graded, not binary): net = clip(w_core*core + w_short*sink)
  with w_core=0.7 fixed, w_sink=0.3 fixed, but the SINK magnitude itself
  is graded by confirmation depth (velocity z AND slope z both deeply
  negative => sink approaches -1) while reclaim (Donchian mid + volume
  surge OR ema slope flip) instantly zeroes ONLY the sink term. In
  confirmed drops the sink can drag net below -0.5 => the executor's
  short_threshold becomes reachable and down-windows go flat/short instead
  of bleeding a half-long core (capital floor).
  Bound both components with tanh BEFORE weighting; |all raw inputs| <= 2.
Charter rules attacked: extreme_participation (+31.3% window needs
entries>0), down_shield(capital_floor) on BOTH drop windows,
adaptive_activity (total>=8, mean>=2/active), medium_term_edge,
noise_stability (signal variance from re-excitation, not from smoothing).
Author: escalation cycle 7 (post alpha_012 post-mortem), 2026-10-03.
Provenance: tuner/runs/alpha_012_auto.json (failed_gates), alpha_008.py,
alpha_010.py, alpha_012.py mechanisms inlined.
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]
    high, low = df["high"], df["low"]
    eps = 1e-9

    w = 48 * 4  # 48h of 15m bars
    minp = w // 2

    ret = close.pct_change()
    sigma = ret.rolling(48, min_periods=20).std().replace(0, eps)

    # ---------------- CORE: graded engine (alpha_008) ----------------------
    ema_f = close.ewm(span=32, min_periods=12).mean()
    ema_s = close.ewm(span=128, min_periods=40).mean()
    spread = (ema_f - ema_s) / close.replace(0, eps)
    g_trend = 0.5 * (np.tanh((spread + 0.001) * 400.0) + 1.0)  # [0,1]

    mid96 = close.rolling(96, min_periods=32).mean()
    conviction = (close > mid96).astype(float).rolling(96, min_periods=32).mean()

    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    atr_pct = tr.rolling(48, min_periods=20).mean() / close.replace(0, eps)
    atr_pct = atr_pct.replace(0, 0.001)
    calm = 0.5 * (np.tanh((0.006 - atr_pct) / 0.002) + 1.0)

    dip = np.tanh(-(close.pct_change(8) / (sigma * np.sqrt(8))).fillna(0) / 1.5)
    base = 0.20 + 0.25 * calm + 0.30 * conviction + 0.25 * dip

    down_fast = -(close.pct_change(4) / (sigma * np.sqrt(4))).fillna(0)
    cut = 0.5 * (np.tanh((down_fast - 1.2) / 0.8) + 1.0)
    raw_core = base * (0.35 + 0.65 * g_trend) * (1.0 - 0.5 * cut)

    # ---- NEW: breakout-momentum term (drives core past thresholds) --------
    hh_w = high.rolling(w, min_periods=minp).max()
    ll_w = low.rolling(w, min_periods=minp).min()
    pos = ((close - ll_w) / (hh_w - ll_w).replace(0, eps)).clip(0, 1).fillna(0)
    v_mu = volume.rolling(w, min_periods=minp).mean().replace(0, eps)
    v_rel = (volume / v_mu).clip(0, 2).fillna(1)
    breakout = np.tanh((pos - 0.7) * 6.0) * np.tanh((v_rel - 1.2) * 2.0)
    breakout = breakout.clip(lower=0)  # only upside breakouts add

    # ---- NEW: re-excitation kicker (pullback-resume entries) --------------
    hh7 = high.rolling(w * 3, min_periods=w * 2).max()
    near_high = (close / hh7.replace(0, eps)).clip(0, 1.05).fillna(0)
    pullback_ok = (near_high > 0.92).astype(float) * (close > ema_f).astype(float)
    resume = pullback_ok * np.tanh((spread) * 500.0).clip(lower=0)

    core_raw = raw_core + 0.45 * breakout + 0.30 * resume
    core = np.tanh(core_raw.ewm(span=16, min_periods=4).mean().fillna(0))
    core = core.clip(0.0, 1.0)  # long core never negative; floor of participation

    # ---------------- REGIME SCORE (confirmed breakdown) -------------------
    mean48 = close.rolling(w, min_periods=minp).mean()
    vel = ((close - mean48) / close.replace(0, eps)).clip(-0.5, 0.5).fillna(0)
    vel_mu = vel.rolling(w, min_periods=minp).mean()
    vel_sd = vel.rolling(w, min_periods=minp).std().replace(0, eps)
    vel_z = ((vel - vel_mu) / vel_sd).clip(-2, 2).fillna(0)

    slope = (close - close.shift(w * 3)) / close.shift(w * 3).replace(0, eps)
    slope = slope.clip(-0.5, 0.5).fillna(0)
    sl_mu = slope.rolling(w * 2, min_periods=w).mean()
    sl_sd = slope.rolling(w * 2, min_periods=w).std().replace(0, eps)
    sl_z = ((slope - sl_mu) / sl_sd).clip(-2, 2).fillna(0)

    score = (0.5 * np.tanh(vel_z * 1.5) + 0.5 * np.tanh(sl_z * 1.5))
    score = score.ewm(span=12, min_periods=3).mean()

    # graded confirmation: 2 consecutive negative evaluations, deeper = bigger
    neg = (score < 0).astype(float)
    confirm = neg.rolling(2, min_periods=2).mean()  # 0, 0.5, 1
    depth = np.tanh((-score - 0.3) * 2.0).clip(0, 1)  # graded magnitude

    # ---------------- RECLAIM (suspends ONLY the sink) ---------------------
    donch_mid = 0.5 * (hh_w + ll_w)
    above_mid = (close > donch_mid).astype(float)
    v_surge = (v_rel > 1.5).astype(float)
    ema_f_slope = (ema_f - ema_f.shift(4)).fillna(0)
    slope_flip = (ema_f_slope > 0).astype(float)
    reclaim = np.clip(above_mid * (v_surge + slope_flip), 0.0, 1.0)

    # ---------------- GRADED SHORT SINK (additive) -------------------------
    sink = confirm * depth * (1.0 - reclaim)
    sink = np.tanh(sink.ewm(span=6, min_periods=2).mean().fillna(0))

    # ---------------- ADDITIVE COMPOSITE ------------------------------------
    signal = 0.70 * core - 0.30 * sink
    return signal.clip(-1.0, 1.0).fillna(0.0)
