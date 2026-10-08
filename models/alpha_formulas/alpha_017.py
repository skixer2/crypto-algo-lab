"""
alpha_017 — MELT-UP SPECIALIST v2 (regime-blind vertical-break velocity)
Hypothesis: post-drop V-reversal melt-ups are structurally incompatible with
regime-gated signals (proven 4 ways, alpha_011..014). The only proven
melt-up owner is alpha_004 (+11.8% on the +31.33% window) — a regime-BLIND
fast sigma-velocity long trigger. This formula evolves 004 per the charter's
design requirements: (a) FASTER trigger — pure 2-bar and 4-bar velocity in
trailing sigma units so it fires within hours of a vertical break from any
preceding state (no EMA gate, no overlay drag, no preceding-state memory
beyond trailing vol); (b) VOLUME CONFIRMATION as a graded multiplier, not a
gate — high relative volume amplifies the break, but low volume only damps,
never zeroes it (004-style never blocks a genuine gap); (c) WIDE-RIDING
shape — signal saturates at tanh(±2 sigma) and stays saturated while
momentum persists (multi-horizon blend: short spike + slower follow-through
term), matching 'wide take so it rides' rather than fast mean-reversion
exits; (d) LONG/FLAT asymmetry retained: shorts are clipped at a small
residual so the formula spends melt-up windows fully long and down windows
near flat (a DOWN-PROFIT specialist already exists as a sibling; this is the
scarcest-quadrant specialist).
Scale discipline: velocity terms divided by trailing per-bar sigma only
after .replace(0,1e-9); all tanh inputs bounded |x| <~ 2; volume z-scored
by trailing mean with epsilon. Trailing ops only (pct_change, rolling, ewm).
Rule attacked: EXTREME PARTICIPATION (bench >= +15% -> strat > 0) and the
melt-up specialist scarcity quadrant; secondary: ADAPTIVE ACTIVITY via the
high flip rate of the fast velocity trigger.
Author: auto-gen (isolated alpha generation loop), 2026-10-04.
Provenance: models/alpha_formulas/alpha_004.py (reference, immutable),
tuner/runs/alpha_015_auto.json and alpha_016_auto.json failure reports
(extreme_participation + noise_stability failures), charter v2.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, volume = df["close"], df["volume"]

    # Trailing per-bar volatility (2-day at 15m), epsilon-guarded
    ret = close.pct_change()
    sigma = ret.rolling(96, min_periods=24).std().replace(0, 1e-9)

    # --- Fast vertical-break velocity, in sigma units ---
    # Short spike term: 2-bar break, weighted by close position in bar range
    # (strong-close bars are genuine breakouts, not upper-wick fakes).
    rng = (df["high"] - df["low"]).replace(0, 1e-9)
    close_pos = ((close - df["low"]) / rng - 0.5) * 2.0  # in [-1, 1]
    spike = close.pct_change(2) / (sigma * np.sqrt(2))

    # Follow-through term: 4-bar + 8-bar blend, confirms the break persists
    follow = 0.7 * close.pct_change(4) / (sigma * np.sqrt(4)) + 0.3 * close.pct_change(8) / (sigma * np.sqrt(8))

    # Composite velocity, each term tanh-squashed before blending (bounded)
    v = 0.6 * np.tanh(spike / 1.5) + 0.25 * np.tanh(follow / 2.0) + 0.15 * np.tanh(close_pos * 1.5)

    # --- Graded volume confirmation (amplifier, never a hard gate) ---
    vol_rel = volume / volume.rolling(64, min_periods=16).mean().replace(0, 1e-9)
    vol_conf = 0.55 + 0.45 * np.tanh((vol_rel - 1.0) / 1.0)  # in [0.1, 1.0]

    sig = v * vol_conf

    # Long/flat asymmetry: melt-up specialist — full long on upside breaks,
    # small residual short (bounded to 35%) so down windows bleed minimally
    # while participation stays non-trivial for activity counting.
    sig = sig.clip(-0.35, 1.0)
    return sig.clip(-1, 1).fillna(0.0)
