"""CompositeRouterModel — hard-switching mixture-of-experts (the conductor).

Routes between validated specialist formulas by trailing regime state:
  confirmed_bearish  -> DOWN specialist   (shorts allowed, the only state with them)
  vol_compressed      -> CHOP specialist   (range survival core)
  otherwise           -> MELT-UP specialist (regime-BLIND fast trigger — default
                         lane so post-drop V-reversals are caught at inception)

Design lessons baked in (each paid for by an alpha family):
- SWITCH, never blend: additive/multiplicative composites suppressed melt-up
  entries 4 different ways (alpha_011-014, 0 entries in the +31.33% week).
- Breakdown needs CONFIRMATION (price below Donchian mid sustained ~24h);
  reclaim is INSTANT (single cross above mid) — the asymmetry alpha_009/010
  taught: slow to short, fast to re-long.
- Full engine contract on every entry: stop_loss/take_profit > 0, ATR-based.
- Precompute per RUN-SLICE at anchor (the equivalence-verified fast-path
  trick): each specialist's signal + TR computed ONCE, O(1) lookups per tick.
  No phantom columns: precompute lives here, not in stored CSVs.

The engine sees an ordinary Model. Router params go through the same Optuna
walk-forward and charter gates as any formula — no special treatment.
"""
from __future__ import annotations

import hashlib
import importlib.util
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMULA_DIR = os.path.join(REPO_ROOT, "models", "alpha_formulas")

Action = str  # "long" | "short" | "flat"


@dataclass
class RouterParams:
    """All tunables — the optimizer tunes exactly these."""
    meltup_formula: str = "alpha_004"     # regime-blind fast-velocity long
    chop_formula: str = "alpha_008"       # always-in graded core
    down_formula: str = "alpha_014"       # confirmed-breakdown short specialist
    # regime detection (trailing, causal)
    donchian_bars: int = 192              # mid-band window (48h @ 15m)
    confirm_bars: int = 96                # sustained-below-mid confirmation (24h)
    vol_compression: float = 0.75         # TR ratio below this = compressed
    vol_fast: int = 14
    vol_slow: int = 96
    grind_slope_bars: int = 96        # 4th state: slow grind-down detector (24h @ 15m)
    # per-specialist entry thresholds
    meltup_threshold: float = 0.35
    chop_threshold: float = 0.35
    down_threshold: float = 0.35
    # shared signal smoothing
    signal_smoothing: int = 8
    # risk (ATR-based, engine contract)
    atr_period: int = 14
    atr_stop_mult: float = 6.0
    atr_take_mult: float = 6.0
    max_position_pct: float = 1.0
    warmup_candles: int = 300             # >= donchian + confirm + specialist needs


def _load_signal_fn(name: str):
    path = os.path.join(FORMULA_DIR, name if name.endswith(".py") else name + ".py")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"specialist formula not found: {path}")
    with open(path, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()[:10]
    spec = importlib.util.spec_from_file_location(f"router_spec_{name}_{h}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "calculate_math_signal"):
        raise AttributeError(f"{name}: missing calculate_math_signal")
    return mod.calculate_math_signal, h


class CompositeRouterModel:
    """Hard-switching router over three specialist signal streams."""

    def __init__(self, params: RouterParams, execution_tf: str = "15m",
                 bias_tfs: Optional[List[str]] = None):
        self.p = params
        self.execution_tf = execution_tf
        self.bias_tfs = list(bias_tfs or [])
        self._fns = {}
        self._hashes = {}
        for role, name in (("meltup", params.meltup_formula),
                           ("chop", params.chop_formula),
                           ("down", params.down_formula)):
            fn, h = _load_signal_fn(name)
            self._fns[role] = fn
            self._hashes[role] = h
        # per-run anchored state
        self._sig: Dict[str, Optional[pd.Series]] = {"meltup": None, "chop": None, "down": None}
        self._atr: Optional[pd.Series] = None
        self._mid: Optional[pd.Series] = None     # trailing Donchian mid-band
        self._volratio: Optional[pd.Series] = None
        self._below_sustained: Optional[pd.Series] = None
        self._tick = 0
        self._base = None
        self._last_indicators: Dict = {}

    # ── Module 3 contract ──────────────────────────────────────────

    def update(self, candle_row, tf: str) -> None:
        if tf != self.execution_tf:
            return
        if self._base is None:
            self._anchor(candle_row)
        else:
            expected = self._ctx_index[self._base + self._tick]
            if candle_row.name != expected:
                raise ValueError(
                    f"router desync at {candle_row.name}: expected {expected}")
        self._tick += 1

    def predict(self, allow_shorts: bool = True) -> Tuple[Action, float, Dict]:
        need = max(self.p.warmup_candles,
                   self.p.donchian_bars + self.p.confirm_bars,
                   3 * self.p.signal_smoothing)
        if self._base is None or self._tick < need:
            return "flat", 0.0, self._last_indicators
        i = self._tick - 1  # run-relative position in anchored series

        price = float(self._ctx_close.iat[i])
        mid = float(self._mid.iat[i])
        volr = float(self._volratio.iat[i])
        bearish = bool(self._below_sustained.iat[i]) and price < mid
        slope = float(self._slope.iat[i])
        atr = float(self._atr.iat[i])
        if not (atr > 0):
            atr = price * 0.01

        if bearish:
            role, threshold, regime = "down", self.p.down_threshold, "confirmed_bearish"
        elif price < mid and slope < 0:
            # 4th state (v2): slow grind-down — below mid, not confirmed bearish,
            # negative slow slope. w08 lesson (2025-01, -42.8%): melt-up default lane
            # must NOT try longs into a grind. Stand aside entirely.
            self._last_indicators = {"entry_price": price, "regime": "grind_down",
                                     "routed": "cash", "signal": 0.0, "atr": round(atr, 4)}
            return "flat", 0.0, self._last_indicators
        elif volr < self.p.vol_compression:
            role, threshold, regime = "chop", self.p.chop_threshold, "vol_compressed"
        else:
            role, threshold, regime = "meltup", self.p.meltup_threshold, "expansion"

        sig = float(self._sig[role].iat[i])

        action: Action = "flat"
        if sig >= threshold:
            action = "long"
        elif allow_shorts and regime == "confirmed_bearish" and sig <= -threshold:
            action = "short"  # shorts ONLY in the confirmed-bearish lane

        indicators = {"entry_price": price, "regime": regime, "routed": role,
                      "signal": round(sig, 4), "atr": round(atr, 4)}
        if action == "long":
            indicators["stop_loss"] = max(price - self.p.atr_stop_mult * atr, 1e-9)
            indicators["take_profit"] = price + self.p.atr_take_mult * atr
        elif action == "short":
            indicators["stop_loss"] = price + self.p.atr_stop_mult * atr
            indicators["take_profit"] = max(price - self.p.atr_take_mult * atr, 1e-9)
        self._last_indicators = indicators
        return action, self.p.max_position_pct, indicators

    def get_indicators(self) -> Dict:
        return self._last_indicators

    # ── anchored precompute (fast-path trick, once per run) ────────

    def _anchor(self, first_row):
        # The engine feeds candles from the (padded) run start; we anchor to the
        # context CSV at that timestamp and precompute every series ONCE on the
        # remaining slice — exact reference semantics, O(1) per tick after.
        self._ctx = pd.read_csv(self._ctx_csv, parse_dates=["timestamp"],
                                index_col="timestamp").sort_index()
        self._ctx_index = self._ctx.index
        pos = self._ctx_index.get_loc(first_row.name)
        self._base = pos
        df = self._ctx.iloc[pos:]

        span = max(int(self.p.signal_smoothing), 1)
        for role, fn in self._fns.items():
            s = pd.Series(fn(df)).astype(float)
            self._sig[role] = s.ewm(span=span, adjust=False).mean() \
                .fillna(0.0).clip(-1.0, 1.0)

        h, l, c = df["high"], df["low"], df["close"]
        prev = c.shift(1)
        tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
        self._atr = tr.ewm(alpha=1.0 / max(self.p.atr_period, 1), adjust=False).mean().bfill()
        self._ctx_close = c

        hh = h.rolling(self.p.donchian_bars, min_periods=self.p.donchian_bars // 2).max()
        ll = l.rolling(self.p.donchian_bars, min_periods=self.p.donchian_bars // 2).min()
        self._mid = ((hh + ll) / 2.0)
        tr_fast = tr.rolling(self.p.vol_fast, min_periods=5).mean()
        tr_slow = tr.rolling(self.p.vol_slow, min_periods=24).mean().replace(0, 1e-9)
        self._volratio = (tr_fast / tr_slow).fillna(1.0)
        below = (c < self._mid).astype(float)
        self._below_sustained = below.rolling(self.p.confirm_bars,
                                              min_periods=self.p.confirm_bars).mean() >= 0.9
        gb = max(int(self.p.grind_slope_bars), 8)
        self._slope = c - c.rolling(gb, min_periods=gb // 2).mean()

    # context CSV injection (orchestrator wires this; keeps model file-clean)
    ctx_csv: Optional[str] = None

    def bind_context(self, csv_path: str) -> None:
        self._ctx_csv = csv_path
