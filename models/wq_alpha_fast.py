"""FastWQAlphaMiner — precomputed fast path for WQAlphaMinerModel.

The incremental reference (models/wq_alpha_miner.py) recomputes the formula on
a trailing buffer every tick: O(N) per tick -> O(N^2) per window (~140s).
This module precomputes the formula ONCE per dataset; per-trial work is two
vectorized EWMs; predict()/manage_position() are O(1) lookups.

EQUIVALENCE ARGUMENT (verified empirically by tuner/verify_fast_equivalence.py):
1. Formula rolling ops are window-local: identical values whether computed on
   the trailing buffer or the full series (windows << buffer_size).
2. EWM smoothing / Wilder ATR initialized at different points converge: the
   difference decays as (1-1/span)^distance. Warmup >= 3*span on BOTH paths
   guarantees convergence before any entry decision is possible.
3. Leading-NaN/fillna(0) divergence is confined to pre-warmup candles, which
   are gated flat on both paths identically.

FastContext is built ONCE per (formula, data range) and shared across trials.
"""
from __future__ import annotations

import hashlib
import importlib.util
import logging
import os
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .wq_alpha_miner import FORMULA_DIR, WQAlphaParams

logger = logging.getLogger(__name__)

Action = str  # "long" | "short" | "flat"


class FastContext:
    """Immutable per-dataset precomputation shared across all trials."""

    def __init__(self, exec_df: pd.DataFrame, bias_df: Optional[pd.DataFrame],
                 formula_path: str):
        self.exec_df = exec_df
        self.bias_df = bias_df
        self.exec_index = exec_df.index
        self.formula_path = formula_path
        self.formula_name = os.path.basename(formula_path)
        with open(formula_path, "rb") as f:
            self.formula_hash = hashlib.sha256(f.read()).hexdigest()[:12]

        spec = importlib.util.spec_from_file_location(
            f"wqfast_{self.formula_hash}", formula_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "calculate_math_signal"):
            raise AttributeError(f"{self.formula_name}: missing calculate_math_signal")
        self.mod = mod


def prepare_fast_context(exec_csv: str, bias_csv: Optional[str],
                         formula: str) -> FastContext:
    exec_df = pd.read_csv(exec_csv, parse_dates=["timestamp"], index_col="timestamp")
    exec_df.sort_index(inplace=True)
    bias_df = None
    if bias_csv:
        bias_df = pd.read_csv(bias_csv, parse_dates=["timestamp"], index_col="timestamp")
        bias_df.sort_index(inplace=True)
    path = formula
    if not os.path.isabs(path):
        path = os.path.join(FORMULA_DIR, path)
    if not os.path.isfile(path) and os.path.isfile(path + ".py"):
        path += ".py"
    return FastContext(exec_df, bias_df, path)


class FastWQAlphaMinerModel:
    """O(1)-per-tick mirror of WQAlphaMinerModel's decision logic."""

    def __init__(self, params: WQAlphaParams, ctx: FastContext,
                 execution_tf: str = "15m", bias_tfs: Optional[List[str]] = None):
        self.p = params
        self.ctx = ctx
        self.execution_tf = execution_tf
        self.bias_tfs = list(bias_tfs or [])

        self._span = int(self.p.signal_smoothing or 1)
        self._min_history = max(int(self.p.warmup_candles), 3 * self._span)
        # Per-trial transforms are derived LAZILY at the run anchor (first
        # update()), so the EWM/ATR initialization point matches the reference
        # wrapper EXACTLY (its buffer starts at the run's first candle too).
        # For runs longer than the reference's buffer (1500), both paths are
        # converged to the same filter fixed point -> float-identical.
        self._sig: Optional[pd.Series] = None
        self._atr: Optional[pd.Series] = None
        # Bias EMAs are derived LAZILY at the bias anchor (first bias candle
        # of the run) so their initialization matches the reference buffer
        # exactly — full-CSV EMAs diverge on short runs (caught by case 4).
        self._bias_bull: Optional[pd.Series] = None
        self._bias_ready = ctx.bias_df is not None and self.p.use_bias_filter

        self._tick = 0        # exec candles fed this run
        self._bias_tick = 0   # bias candles fed this run
        self._base = None      # CSV position of this run's first exec candle
        self._bias_base = None # CSV position of this run's first bias candle
        self._last_indicators: Dict = {}

    # ── Module 3 contract (same as the incremental reference) ───────

    def update(self, candle_row, tf: str) -> None:
        if tf == self.execution_tf:
            if self._base is None:
                # Anchor this run's start inside the context (runs begin at the
                # padded window start, not necessarily the CSV start), and
                # derive the per-trial series from the SAME anchor the
                # reference buffer would use.
                self._base = self.ctx.exec_index.get_loc(candle_row.name)
                # Compute the formula ONCE on the run slice — EXACTLY the series
                # the reference evolves tick-by-tick (same values, same leading-NaN
                # structure; full-CSV slices diverge on the first ~33 candles,
                # which survives long-span EWM warmup — verifier case 4).
                run_df = self.ctx.exec_df.iloc[self._base:]
                raw = pd.Series(self.ctx.mod.calculate_math_signal(run_df)).astype(float)
                self._sig = raw.ewm(span=self._span, adjust=False) \
                    .mean().fillna(0.0).clip(-1.0, 1.0)
                h, l, c = run_df["high"], run_df["low"], run_df["close"]
                prev = c.shift(1)
                tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()],
                               axis=1).max(axis=1)
                self._atr = tr.ewm(alpha=1.0 / max(int(self.p.atr_period), 1),
                                   adjust=False).mean().bfill()
            else:
                expected = self.ctx.exec_index[self._base + self._tick]
                if candle_row.name != expected:
                    raise ValueError(
                        f"fast model desync at {candle_row.name}: expected {expected} "
                        f"— context must cover the run range")
            self._tick += 1
        elif tf in self.bias_tfs:
            if self._bias_base is None:
                self._bias_base = self.ctx.bias_df.index.get_loc(candle_row.name)
                if self._bias_ready:
                    c = self.ctx.bias_df["close"].iloc[self._bias_base:]
                    f = c.ewm(span=int(self.p.bias_fast), adjust=False).mean()
                    sl = c.ewm(span=int(self.p.bias_slow), adjust=False).mean()
                    self._bias_bull = f > sl
            self._bias_tick += 1

    def _idx(self) -> int:
        return self._base + self._tick - 1

    def predict(self, allow_shorts: bool = True) -> Tuple[Action, float, Dict]:
        if self._base is None or self._tick < self._min_history:
            return "flat", 0.0, self._last_indicators
        idx = self._idx()
        ts = self.ctx.exec_index[idx]
        close = float(self.ctx.exec_df["close"].iat[idx])
        sig = float(self._sig.iat[self._tick - 1])   # sliced series: run-relative
        atr = float(self._atr.iat[self._tick - 1])
        if not (atr > 0):  # NaN or <=0 -> reference's 1%-of-close fallback
            atr = close * 0.01

        bias_bull = None
        if self._bias_bull is not None:
            if self._bias_tick >= self.p.bias_slow:
                bias_bull = bool(self._bias_bull.iat[self._bias_tick - 1])

        action: Action = "flat"
        if sig >= self.p.long_threshold and (bias_bull is None or bias_bull):
            action = "long"
        elif (allow_shorts and sig <= -self.p.short_threshold
              and (bias_bull is None or not bias_bull)):
            action = "short"

        indicators: Dict = {
            "entry_price": close, "signal": round(sig, 4), "atr": round(atr, 4),
            "bias_bull": bias_bull, "formula": self.ctx.formula_name,
        }
        if action == "long":
            indicators["stop_loss"] = max(close - self.p.atr_stop_mult * atr, 1e-9)
            indicators["take_profit"] = close + self.p.atr_take_mult * atr
        elif action == "short":
            indicators["stop_loss"] = close + self.p.atr_stop_mult * atr
            indicators["take_profit"] = max(close - self.p.atr_take_mult * atr, 1e-9)

        self._last_indicators = indicators
        return action, self.p.max_position_pct, indicators

    def manage_position(self, position: str, price: float, ts) -> Optional[str]:
        if self.p.signal_exit_threshold is None:
            return None
        if self._base is None or self._tick < self._min_history:
            return None
        sig = float(self._sig.iat[self._tick - 1])   # sliced series: run-relative
        self._last_indicators["manage_signal"] = round(sig, 4)
        if position == "long" and sig <= -self.p.signal_exit_threshold:
            return "signal_flip"
        if position == "short" and sig >= self.p.signal_exit_threshold:
            return "signal_flip"
        return None

    def get_indicators(self) -> Dict:
        return self._last_indicators
