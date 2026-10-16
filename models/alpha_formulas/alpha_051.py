"""
alpha_051 — TURTLE LATCH v2 (P1a bull seat: crisp binary latch, no graded memory)
Hypothesis (JP + Gemini 2026-10-01, promoted 2026-10-11): the blend owns crash
and shield but misses melt-ups (up-capture 0.06). alpha_026 died because graded
EWM memory dilutes below the exit threshold mid-trend. Fix: BINARY HOLDING.
Signal = +1.0 (pinned) while close > trailing structural level (rolling max of
high shifted 1 bar, long window), 0.0 below. Holding is crisp; only a small
tanh ramp of (close - trail)/ATR near the boundary smooths entry — the latch
itself never decays while price holds above the trail.
Exit: only when close drops below the trail (structural stop), so trends are
ridden to exhaustion instead of being sold by threshold noise.
Volume confirmation: entry requires the breakout bar's volume to be at least a
fraction of its rolling average (bounded tanh gate) — boosts real breakouts,
still latches on marginal volume but with slightly reduced initial magnitude
that instantly pins to 1.0 on continuation.
Bounded transforms before compositing; trailing ops only (rolling/shift(1));
rolling stats replace(0,1e-9) before division; no file/network I/O.
Charter rules attacked: uptrend_participation + extreme_participation (bull
seat, up-capture >= 0.5 target), adaptive_activity (latch gives sustained
activity in trend windows), down_shield (structural trail exits fast).
Author: alpha-generation cron cycle, 2026-10-12.
Provenance: tuner/runs/alpha_049_auto.json (flat in bulls = shield fine,
participation failed), alpha_050_auto.json (down_shield fail — not our lane).
Mechanism guidance: alpha_026.py anti-pattern (graded memory), alpha_040.py
structure, charter P1(a) spec.
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    eps = 1e-9

    # ---------- structural trail (Turtle channel, shifted 1) --------------
    latch_w = 480          # 5 days of 15m bars: trailing structural level
    trail = high.rolling(latch_w, min_periods=latch_w // 2).max().shift(1)

    # ---------- ATR for boundary smoothing -------------------------------
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(96, min_periods=48).mean().replace(0, eps)

    # ---------- volume gate (bounded) -------------------------------------
    vol_ma = volume.rolling(latch_w, min_periods=latch_w // 2).mean().replace(0, eps)
    vol_ratio = (volume / vol_ma).clip(0, 4)          # bounded input
    vol_gate = np.tanh(vol_ratio / 2.0)               # in [0,1)

    # ---------- boundary ramp: smooth entry only --------------------------
    above = ((close - trail) / atr).replace([np.inf, -np.inf], np.nan)
    ramp = np.tanh(above.clip(-2, 2))                 # in (-1, 1)

    # ---------- binary latch ----------------------------------------------
    # pinned while close > trail; crisp 0 below (no graded memory)
    pinned = (close > trail).astype(float)

    # entry smoothness: near the boundary signal scales with ramp * vol_gate;
    # once latched it stays 1.0 via the pinned mask (max, not average)
    entry = (ramp.clip(0, 1) * (0.4 + 0.6 * vol_gate)).where(ramp > 0, 0.0)
    raw = pd.concat([pinned, entry], axis=1).max(axis=1)

    # ---------- guard: hard breakdown speed-bump --------------------------
    # if deep below the trail (crash in progress), keep signal at 0 even if
    # trail window still catching up — prevents buying falling knives
    depth = ((trail - close) / atr).clip(-2, 2).fillna(2.0)
    knife = (depth > 1.5).astype(float)
    sig = raw * (1.0 - knife)

    return sig.clip(0, 1).fillna(0.0)
