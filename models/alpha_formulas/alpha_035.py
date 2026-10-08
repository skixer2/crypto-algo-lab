"""
alpha_035 — DOWN-LEG EARNER: 2-bar confirmed breakdown short with instant reclaim exit
Hypothesis (P1, JP promotion 2026-10-07): convert down-shield knowledge into
RETURNS by shorting ONLY on a 2-day CONFIRMED breakdown (close below Donchian
mid of a 2-day window for 2 consecutive bias-bars) and exiting INSTANTLY on
structural reclaim (close back above the 2-day mid). Never short during
reclaim conditions — this is the bear-rally trap protection (2022-01: +14.4%
rally inside bear killed unconditioned shorts). Structure mirrors the
alpha_010/014 lineage (velocity + slope negative regime) but the signal is a
bounded NEGATIVE value only while the confirmed breakdown persists, and
exactly 0 otherwise, so the tuner's short_threshold triggers only in genuine
down-legs. Amplitude scales with breakdown depth z, tanh-bounded <= 1.5, so
deeper confirmed breakdowns produce stronger shorts (profit, not just flat).
All ops trailing (rolling/ewm only), inputs tanh-bounded, divisions guarded
with .replace(0,1e-9) on rolling stats.
Charter rules attacked: down_shield (strat >= 0.2*bench when bench <= 0),
down-leg RETURN > 0 (P1 acceptance), medium_term_edge, consistency(t>0),
adaptive_activity (shorts re-arm on every new breakdown episode).
Author: auto-gen (isolated alpha loop), 2026-10-08. P1 down-leg earner.
Provenance: tuner/runs/alpha_033_auto.json, alpha_034_auto.json (failed_gates:
shield-passive variants, no down-leg returns); alpha_010/014 (down regime
mechanisms); alpha_032 (min-gate amplitude lesson).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    eps = 1e-9

    # ATR for normalization (15m bars, trailing)
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    atr = tr.rolling(96, min_periods=30).mean().replace(0, eps)

    # --- Structure: Donchian mid of a 2-day window (trailing) -------------
    hh = high.rolling(192, min_periods=80).max().shift(1)
    ll = low.rolling(192, min_periods=80).min().shift(1)
    mid = 0.5 * (hh + ll)
    chan = (hh - ll).replace(0, eps)

    below = (close < mid).astype(float)

    # --- 2-bar CONFIRMED breakdown: below mid for 2 consecutive 1h blocks -
    # bias-tf is 1h (4 x 15m bars); require 2 consecutive 1h closes below mid
    h1_below = below.rolling(4, min_periods=4).mean()  # fraction of 15m bars below in last hour
    confirmed_1 = (h1_below >= 0.75).astype(float)     # this hour closed below
    confirmed_2 = confirmed_1.shift(1).fillna(0.0)     # prior hour also closed below
    confirmed = ((confirmed_1 + confirmed_2) >= 2.0).astype(float)

    # --- Instant reclaim: any 15m close back above mid kills the short ----
    reclaim = (close > mid).astype(float)
    # reclaim latch: once reclaimed, stay neutral until a NEW confirmation
    # rebuilds. Trailing-only implementation: rolling max of reclaim over a
    # short window resets state quickly after a reclaim bar.
    recent_reclaim = reclaim.rolling(4, min_periods=1).max()

    # --- Breakdown depth z: how far below mid, ATR-normalized, bounded ----
    depth = (mid - close) / atr.replace(0, eps)
    depth_b = np.tanh(depth / 2.0).clip(-1, 1).fillna(0.0)  # in [0,1] while below

    # --- Down-regime confirmation (010 lineage): fast EMA below slow EMA --
    ema_f = close.ewm(span=96, min_periods=30).mean()
    ema_s = close.ewm(span=384, min_periods=100).mean()
    slope = (ema_f - ema_s) / atr.replace(0, eps)
    down_regime = np.tanh(-slope / 2.0).clip(0, 1).fillna(0.0)

    # --- Volume conviction on the breakdown (sellers active) --------------
    vol_rel = volume / volume.rolling(96, min_periods=30).mean().replace(0, eps)
    vol_conf = 0.5 + 0.5 * np.tanh((vol_rel - 1.0) / 1.5).fillna(0.0)

    # --- Composite short signal ------------------------------------------
    # gate = confirmed AND no recent reclaim AND down regime agrees
    gate = confirmed * (1.0 - recent_reclaim) * (0.5 + 0.5 * down_regime)
    # amplitude: depth-driven, amplified so the tuner short_threshold triggers
    amp = 1.5 * (0.4 + 0.6 * depth_b.abs()) * vol_conf

    sig = -amp * gate
    return sig.clip(-1.5, 1.5).fillna(0.0)
