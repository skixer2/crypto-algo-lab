"""
Module 3 — Market Structure Scalping Model (INTERCHANGEABLE)

Pure signal generator — NO position tracking, NO cash/equity state.
All state management belongs to Module 2 (simulation) or Module 5 (live).

Based on:
  - scraping_method_01.md
  - The Beginner's Blueprint to Crypto Scalping

Logic:
  1. Identify swing highs & lows on bias TFs (trend) and execution TF (entry)
  2. Classify trend via HH/HL (bullish) or LL/LH (bearish) on bias TFs
  3. Detect Market Structure Shift (MSS) on execution TF
  4. Only signal in direction of bias
  5. Entry: execution TF MSS aligning with bias + rejection zone
  6. Exit parameters (SL/TP) returned as part of indicators — simulation applies them

Usage — fully generic, any timeframes:
    model = ScalpingModel(ModelParams(), execution_tf="5m", bias_tfs=["1h", "2h"])
    model.update(row_5m, "5m")
    model.update(row_1h, "1h")
    model.update(row_2h, "2h")
    action, size_pct, ind = model.predict()
    # action ∈ {"long", "short", "flat"}
    # ind["stop_loss"], ind["take_profit"] → simulation uses these
"""

import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Literal
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

Action = Literal["long", "short", "flat"]


@dataclass
class SwingPoint:
    """A detected local extremum."""
    idx: int
    timestamp: pd.Timestamp
    price: float
    kind: str  # "high" or "low"


@dataclass
class ModelParams:
    """All tunable parameters. The optimizer (module 6) tunes these."""
    swing_lookback: int = 5
    min_swing_distance: int = 3
    mss_confirm_candles: int = 1
    rr_ratio: float = 2.0               # risk:reward target
    rejection_zone_pct: float = 0.005    # 0.5% proximity to a level
    atr_stop_multiplier: float = 1.5     # tighter default → fewer false entries
    atr_period: int = 14
    use_three_candle_trigger: bool = True
    min_candles_for_bias: int = 20
    # Position sizing (used by simulation, tuned by optimizer)
    max_position_pct: float = 1.0        # max fraction of equity per trade
    leverage: int = 1                    # placeholder — will be used later


class ScalpingModel:
    """
    Pure signal generator. Stateless beyond candle history.

    Accepts an arbitrary number of timeframes. All candle data is stored
    in self.candles[tf] and swings in self.swings[tf].

    Parameters
    ----------
    params : ModelParams
        Tunable strategy parameters.
    execution_tf : str
        Timeframe label for entry signals, MSS, triggers, SL/TP (e.g. "5m").
    bias_tfs : List[str] or None
        Timeframe labels for trend bias and rejection zones (e.g. ["1h", "2h"]).
        Defaults to ["1h"] if not provided.
    """

    def __init__(
        self,
        params: Optional[ModelParams] = None,
        execution_tf: str = "5m",
        bias_tfs: Optional[List[str]] = None,
    ):
        self.params = params or ModelParams()
        self.p = self.params

        # ── Timeframe configuration ──────────────────────────────
        self.execution_tf = execution_tf
        self.bias_tfs = bias_tfs or ["1h"]

        # ── Storage: dict[tf] -> list ────────────────────────────
        self.candles: Dict[str, list] = defaultdict(list)
        self.swings: Dict[str, list] = defaultdict(list)

        # Cached signals
        self._last_bias: str = "neutral"
        self._last_indicators: Dict = {}
        self._active_signal: Optional[str] = None  # "long" or "short" or None
        self._last_entry_price: float = 0.0
        self._last_sl: float = 0.0
        self._last_tp: float = 0.0

    # ── Data ingestion ──────────────────────────────────────────────

    def update(self, candle_row, tf: str) -> None:
        """
        Feed one candle for a given timeframe.

        Args:
            candle_row: pd.Series, pd.DataFrame, or dict with
                        timestamp/open/high/low/close/volume
            tf: timeframe label, e.g. "5m", "1h", "2h"
        """
        self.candles[tf].append(self._to_dict(candle_row))
        self._detect_swings(tf)

    def _to_dict(self, row) -> dict:
        if isinstance(row, pd.Series):
            return {
                "timestamp": row.name,
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": float(row.get("volume", 0)),
            }
        if isinstance(row, pd.DataFrame):
            return {
                "timestamp": row.index[0],
                "open": float(row["open"].iloc[0]), "high": float(row["high"].iloc[0]),
                "low": float(row["low"].iloc[0]), "close": float(row["close"].iloc[0]),
                "volume": float(row.get("volume", pd.Series([0])).iloc[0]),
            }
        return {
            "timestamp": row.get("timestamp"),
            "open": float(row.get("open", 0)), "high": float(row.get("high", 0)),
            "low": float(row.get("low", 0)), "close": float(row.get("close", 0)),
            "volume": float(row.get("volume", 0)),
        }

    # ── Swing point detection ───────────────────────────────────────

    def _detect_swings(self, tf: str) -> None:
        candles = self.candles[tf]
        swings = self.swings[tf]
        lb = self.p.swing_lookback

        if len(candles) < 2 * lb + 1:
            return

        last_checked = swings[-1].idx if swings else lb - 1
        start = max(lb, last_checked - lb)
        end = len(candles) - lb

        for i in range(start, end):
            ch, cl = candles[i]["high"], candles[i]["low"]

            is_high = all(candles[j]["high"] <= ch for j in range(i - lb, i + lb + 1))
            if is_high:
                sp = SwingPoint(idx=i, timestamp=candles[i]["timestamp"],
                                price=ch, kind="high")
                if not self._too_close(sp, swings):
                    swings.append(sp)

            is_low = all(candles[j]["low"] >= cl for j in range(i - lb, i + lb + 1))
            if is_low:
                sp = SwingPoint(idx=i, timestamp=candles[i]["timestamp"],
                                price=cl, kind="low")
                if not self._too_close(sp, swings):
                    swings.append(sp)

        swings.sort(key=lambda s: s.idx)

    def _too_close(self, sp: SwingPoint, swings: List[SwingPoint]) -> bool:
        count = 0
        for prev in reversed(swings):
            if prev.kind == sp.kind:
                count += 1
                if abs(sp.idx - prev.idx) < self.p.min_swing_distance:
                    return True
                if count >= 3:
                    break
        return False

    # ── Market structure analysis ────────────────────────────────────

    @staticmethod
    def _get_alternating_swings(swings: List[SwingPoint], n: int = 4) -> List[SwingPoint]:
        """Return last n alternating swing points."""
        if len(swings) < 2:
            return []
        result = [swings[-1]]
        for s in reversed(swings[:-1]):
            if s.kind != result[-1].kind:
                result.append(s)
            if len(result) >= n:
                break
        result.reverse()
        return result

    def _analyze_structure(self, swings: List[SwingPoint]) -> Tuple[str, bool]:
        """
        Returns: (trend, mss_detected)
          trend: "bullish" | "bearish" | "neutral"
          mss_detected: True if structure just broke prior pattern
        """
        recent = self._get_alternating_swings(swings, n=4)
        if len(recent) < 3:
            return "neutral", False

        highs = [s.price for s in recent if s.kind == "high"]
        lows = [s.price for s in recent if s.kind == "low"]

        if len(highs) >= 2 and len(lows) >= 2:
            h1, h2 = highs[-2], highs[-1]
            l1, l2 = lows[-2], lows[-1]
            if h2 > h1 and l2 > l1:
                return "bullish", False
            if h2 < h1 and l2 < l1:
                return "bearish", False

        if len(recent) >= 3:
            a, b, c = recent[-3], recent[-2], recent[-1]
            if a.kind == "high" and b.kind == "low" and c.kind == "high":
                if c.price > a.price:
                    return "bullish", True
            if a.kind == "low" and b.kind == "high" and c.kind == "low":
                if c.price < a.price:
                    return "bearish", True

        return "neutral", False

    # ── Rejection zone ───────────────────────────────────────────────

    def _in_rejection_zone(self) -> Tuple[bool, str]:
        """
        Check if execution TF price is near a bias-TF swing level.
        Uses the primary bias TF (first in bias_tfs).
        """
        bias_tf = self.bias_tfs[0] if self.bias_tfs else None
        exec_tf = self.execution_tf

        if not bias_tf:
            return False, ""
        if len(self.swings.get(bias_tf, [])) < 2:
            return False, ""
        if not self.candles.get(exec_tf):
            return False, ""

        price = self.candles[exec_tf][-1]["close"]
        t = self.p.rejection_zone_pct

        bias_swings = self.swings[bias_tf]
        highs = [s for s in bias_swings if s.kind == "high"]
        lows = [s for s in bias_swings if s.kind == "low"]

        if highs:
            last_high = highs[-1]
            if abs(price - last_high.price) / last_high.price < t:
                return True, "resistance"
        if lows:
            last_low = lows[-1]
            if abs(price - last_low.price) / last_low.price < t:
                return True, "support"
        return False, ""

    # ── Three-candle trigger ─────────────────────────────────────────

    def _three_candle_trigger(self, direction: str) -> bool:
        exec_candles = self.candles.get(self.execution_tf, [])
        if len(exec_candles) < 3:
            return False
        closes = [c["close"] for c in exec_candles[-3:]]
        if direction == "short":
            return closes[0] > closes[1] > closes[2]
        if direction == "long":
            return closes[0] < closes[1] < closes[2]
        return False

    # ── ATR ──────────────────────────────────────────────────────────

    def _compute_atr(self, candles: List[dict]) -> float:
        n = self.p.atr_period
        if len(candles) < n + 1:
            return 0.0
        trs = []
        for i in range(-n, 0):
            h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        return float(np.mean(trs))

    # ── Predict (pure signal) ────────────────────────────────────────

    def predict(self, allow_shorts: bool = True) -> Tuple[Action, float, Dict]:
        """
        Generate a trading signal based on current state.

        Uses execution_tf for entry triggers / SL/TP and bias_tfs for
        trend direction and rejection zones.

        Args:
            allow_shorts: if False, never signal "short" (spot-only mode)

        Returns:
            (action, position_size_pct, indicators)
            indicators contains "entry_price", "stop_loss", "take_profit"
              for the simulation to use if action != "flat"
        """
        exec_tf = self.execution_tf
        primary_bias = self.bias_tfs[0] if self.bias_tfs else None

        # ── Build indicators dict dynamically ────────────────────
        indicators: Dict = {
            "bias": "neutral",
            "exec_tf": exec_tf,
            "bias_tfs": list(self.bias_tfs),
            "signal": "none",
            "entry_price": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
        }
        # Per-tf trend / MSS fields
        for tf in set([exec_tf] + self.bias_tfs):
            indicators[f"trend_{tf}"] = "neutral"
            indicators[f"mss_{tf}"] = False

        indicators.setdefault("in_rejection_zone", False)
        indicators.setdefault("zone_type", "")

        # ── Guard: enough data? ──────────────────────────────────
        exec_candles = self.candles.get(exec_tf, [])
        if len(exec_candles) < self.p.swing_lookback * 2:
            return "flat", 0.0, indicators

        if primary_bias:
            bias_candles = self.candles.get(primary_bias, [])
            if len(bias_candles) < self.p.min_candles_for_bias:
                return "flat", 0.0, indicators

        # ── 1. Bias trend ────────────────────────────────────────
        bias = "neutral"
        if primary_bias:
            bias, _ = self._analyze_structure(self.swings.get(primary_bias, []))
            indicators[f"trend_{primary_bias}"] = bias
        self._last_bias = bias
        indicators["bias"] = bias

        # ── 2. Execution structure ───────────────────────────────
        exec_trend, exec_mss = self._analyze_structure(
            self.swings.get(exec_tf, [])
        )
        indicators[f"trend_{exec_tf}"] = exec_trend
        indicators[f"mss_{exec_tf}"] = exec_mss

        # ── 3. Rejection zone ────────────────────────────────────
        in_zone, zone_type = self._in_rejection_zone()
        indicators["in_rejection_zone"] = in_zone
        indicators["zone_type"] = zone_type

        # ── 4. Entry logic ───────────────────────────────────────
        entry_signal: Optional[str] = None
        price = exec_candles[-1]["close"]

        if bias == "bullish":
            if exec_mss and exec_trend == "bullish":
                entry_signal = "long"
            elif self.p.use_three_candle_trigger and in_zone and zone_type == "support":
                if self._three_candle_trigger("long"):
                    entry_signal = "long"

        elif bias == "bearish":
            if allow_shorts:
                if exec_mss and exec_trend == "bearish":
                    entry_signal = "short"
                elif self.p.use_three_candle_trigger and in_zone and zone_type == "resistance":
                    if self._three_candle_trigger("short"):
                        entry_signal = "short"

        # ── 5. Compute SL / TP ───────────────────────────────────
        if entry_signal:
            atr = self._compute_atr(exec_candles)
            stop_dist = self.p.atr_stop_multiplier * atr if atr > 0 else price * 0.01

            if entry_signal == "long":
                sl = price - stop_dist
                tp = price + stop_dist * self.p.rr_ratio
            else:
                sl = price + stop_dist
                tp = price - stop_dist * self.p.rr_ratio

            size_pct = self.p.max_position_pct
            indicators.update({
                "signal": entry_signal,
                "entry_price": price,
                "stop_loss": sl,
                "take_profit": tp,
            })
            self._last_indicators = indicators
            self._active_signal = entry_signal
            return entry_signal, size_pct, indicators

        indicators["signal"] = "none"
        indicators["entry_price"] = price
        self._active_signal = None

        # ── Swing points for graphing (dynamic per-tf keys) ─────
        for tf in set([exec_tf] + self.bias_tfs):
            swings = self.swings.get(tf, [])
            indicators[f"swings_{tf}_highs"] = [
                (s.timestamp, s.price) for s in swings if s.kind == "high"
            ]
            indicators[f"swings_{tf}_lows"] = [
                (s.timestamp, s.price) for s in swings if s.kind == "low"
            ]

        self._last_indicators = indicators
        return "flat", 0.0, indicators

    # ── Accessors (read-only) ────────────────────────────────────────

    def get_bias(self) -> str:
        return self._last_bias

    def get_indicators(self) -> Dict:
        return self._last_indicators
