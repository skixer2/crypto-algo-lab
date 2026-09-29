# REVIEW PACK v2 — crypto-algo-lab (2026-09-29, Gemini round 2)

Repo (public): https://github.com/skixer2/crypto-algo-lab — raw files at
https://raw.githubusercontent.com/skixer2/crypto-algo-lab/main/<path>
All commits through 26b914d are pushed. This pack = everything new since pack v1.

## What happened since pack v1 (your audit -> our triage -> new results)

Your audit was triaged; accepted items are implemented and pushed:

| Your point | Outcome |
|---|---|
| Q1 sample size / variance dominance | ACCEPTED — gates now require total OOS entries >= 50; 6-8 windows + 21d test now feasible (Jan-Sep data cached). VALIDATED EMPIRICALLY within 24h (see results) |
| Q2 warmup dead zone | ACCEPTED — run_backtest pads 3 days before each measured window |
| Q3 gate structure | ACCEPTED — per-window floor (-1.0) + mean hurdle (+2.0) + entries gate + consistency t-score + failed_gates list; thresholds CLI-tunable |
| Q4 signal-flip exits | LOGIC ACCEPTED, MECHANISM REPLACED — get_indicators() is never re-read by the engine for SL/TP (engine fields set once at entry), so the proposed zero-engine exit was inert. Implemented as a real engine hook: optional manage_position() (hasattr-gated, backward compatible) + wrapper impl with tunable signal_exit_threshold (now in Optuna space). Verified: off -> 0 model exits; on -> model_exit:signal_flip fires |
| Q5 objective | PARTIAL — excess score stays for Optuna; t-score + entries gate carry anti-luck burden; PF/Sortino reporting deferred |
| Q6 serialization leak | CONCERN VALID FOR GLOBAL OPS (already banned in contract v2), DIAGNOSIS WRONG for rolling rank: rolling(20).rank(pct=True) is trailing/causal (proof: truncated-vs-full equality at row 2500); your .apply() rewrite outputs IDENTICAL values, 97x slower |

## THE RESULT (the headline)

Same formula (alpha_001), same data, same seeds — before vs after your fixes:

                        dryrun3 (old protocol)    gates_v2 (corrected protocol)
OOS mean excess             +4.42%                    -1.40%
Capital floor (3 windows)   PASSED 3/3                FAILED (all 3 down-windows)
Entries                     ~15                       12  (gate: >= 50)
Test excess                 -9.59%                    -7.98%
Verdict                     REJECT                    REJECT (all five gates)

Interpretation: the +4.4% was fragile luck — it flipped sign under corrected
warmup handling and a wider search space. Your variance-dominance warning
manifested within 24 hours. alpha_001 is dead as a candidate; as the pipeline's
first test case it exposed exactly what it needed to.

## Round-2 questions for you

R1. The fragility test: would you require N reruns with different seeds / bootstrapped
    window shuffles as a standard stability gate before ANY future PROMOTE?
R2. Entries >= 50 is hard to hit for 15m mean-reversion with threshold entries.
    Lower-hurdle alternatives (e.g. >= 30) or force more entries via wider param
    ranges, or move exec TF to 5m?
R3. The manage_position hook (code below): any protocol risks you see (e.g. exit
    reason accounting, interaction with SL/TP order of checks)?
R4. Next formulas: alpha_002 (trend-following complement). What regime hypotheses
    would you prioritize for diversity?

================================================================================
FILE: models/wq_alpha_miner.py  (CURRENT — includes manage_position + warmup scaling)
================================================================================

"""WQ Alpha Miner — bridges WorldQuant-style vectorized alpha formulas to the
framework's incremental model contract (Module 3).

Design notes (engine protocol, verified against framework/simulation.py):
  - predict() is ONLY called when FLAT: this is an entry-signal protocol.
    Exits happen exclusively via stop-loss/take-profit (close-price checks).
    Therefore the alpha's exit intelligence lives in ATR-based SL/TP placement.
  - Entries are REJECTED unless indicators carry stop_loss > 0 and take_profit > 0.
  - The engine calls model.get_indicators() on EVERY tick — mandatory.

The formula file contract lives in models/alpha_formulas/README.md:
    calculate_math_signal(df: pd.DataFrame) -> pd.Series   # values in [-1, 1]
    df columns: open, high, low, close, volume (UTC DatetimeIndex). Causal ops only.
"""
from __future__ import annotations

import hashlib
import importlib.util
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.dirname(os.path.abspath(__file__))
FORMULA_DIR = os.path.join(MODELS_DIR, "alpha_formulas")

Action = str  # "long" | "short" | "flat"


@dataclass
class WQAlphaParams:
    """All tunables — the optimizer (Module 6) tunes exactly these."""
    formula_path: str = ""            # absolute, or relative to models/alpha_formulas/
    long_threshold: float = 0.55      # signal >=  this -> long entry
    short_threshold: float = 0.55     # signal <= -this -> short entry
    signal_smoothing: int = 5         # EMA span on raw signal (1 = off)
    atr_period: int = 14
    atr_stop_mult: float = 2.0        # SL distance in ATRs
    atr_take_mult: float = 3.0        # TP distance in ATRs
    max_position_pct: float = 1.0
    warmup_candles: int = 60          # min exec candles before entries are allowed
    buffer_size: int = 1500           # per-TF candle buffer cap (memory bound)
    use_bias_filter: bool = True      # EMA fast/slow on first bias TF gates direction
    bias_fast: int = 50
    bias_slow: int = 200
    signal_exit_threshold: Optional[float] = None  # exit held position when signal flips beyond this (None = off)


class WQAlphaMinerModel:
    """Incremental wrapper around a vectorized alpha formula.

    Deterministic: state = per-TF candle buffers only; a fresh instance
    reproduces any backtest exactly. No lookahead: signals at t are computed
    from candles with timestamp <= t.
    """

    def __init__(
        self,
        params: WQAlphaParams,
        execution_tf: str = "15m",
        bias_tfs: Optional[List[str]] = None,
    ):
        self.p = params
        self.execution_tf = execution_tf
        self.bias_tfs = list(bias_tfs or [])

        path = params.formula_path
        if not os.path.isabs(path):
            path = os.path.join(FORMULA_DIR, path)
        if not os.path.isfile(path) and os.path.isfile(path + ".py"):
            path += ".py"
        if not os.path.isfile(path):
            raise FileNotFoundError(f"alpha formula not found: {path}")
        self.formula_path = path
        self.formula_name = os.path.basename(path)
        with open(path, "rb") as f:
            self.formula_hash = hashlib.sha256(f.read()).hexdigest()[:12]

        spec = importlib.util.spec_from_file_location(
            f"wqalpha_{self.formula_hash}", path
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "calculate_math_signal"):
            raise AttributeError(
                f"{self.formula_name}: missing calculate_math_signal(df)"
            )
        self._mod = mod

        self._buffers: Dict[str, List[dict]] = {tf: [] for tf in [execution_tf] + self.bias_tfs}
        self._last_indicators: Dict = {}
        self._formula_error_logged = False
        # EWM smoothing needs ~3 spans of history to converge — enforce it in warmup
        # so early signals aren't under-smoothed vs long backtests (audit 2026-09-29).
        self._min_history = max(int(self.p.warmup_candles), 3 * int(self.p.signal_smoothing or 1))

    # ── Module 3 contract ──────────────────────────────────────────

    def update(self, candle_row, tf: str) -> None:
        buf = self._buffers.setdefault(tf, [])
        buf.append({
            "timestamp": candle_row.name,
            "open": float(candle_row["open"]),
            "high": float(candle_row["high"]),
            "low": float(candle_row["low"]),
            "close": float(candle_row["close"]),
            "volume": float(candle_row["volume"]),
        })
        if len(buf) > self.p.buffer_size:
            del buf[: len(buf) - self.p.buffer_size]

    def predict(self, allow_shorts: bool = True) -> Tuple[Action, float, Dict]:
        buf = self._buffers[self.execution_tf]
        if len(buf) < self._min_history:
            return "flat", 0.0, self._last_indicators

        df = pd.DataFrame(buf).set_index("timestamp")
        close = float(df["close"].iloc[-1])

        sig = self._compute_signal(df)
        if sig is None:
            return "flat", 0.0, self._last_indicators

        atr = self._compute_atr(df)
        bias_bull = self._bias_trend()  # None if no filter / not enough data

        action: Action = "flat"
        if sig >= self.p.long_threshold and (bias_bull is None or bias_bull):
            action = "long"
        elif (
            allow_shorts
            and sig <= -self.p.short_threshold
            and (bias_bull is None or not bias_bull)
        ):
            action = "short"

        indicators: Dict = {
            "entry_price": close,
            "signal": round(sig, 4),
            "atr": round(atr, 4),
            "bias_bull": bias_bull,
            "formula": self.formula_name,
        }
        if action == "long":
            indicators["stop_loss"] = max(close - self.p.atr_stop_mult * atr, 1e-9)
            indicators["take_profit"] = close + self.p.atr_take_mult * atr
        elif action == "short":
            indicators["stop_loss"] = close + self.p.atr_stop_mult * atr
            indicators["take_profit"] = max(close - self.p.atr_take_mult * atr, 1e-9)

        self._last_indicators = indicators
        return action, self.p.max_position_pct, indicators

    def get_indicators(self) -> Dict:
        return self._last_indicators

    def manage_position(self, position: str, price: float, ts) -> Optional[str]:
        """Engine hook (optional, called every tick while IN POSITION — see
        framework/simulation.py). Returns an exit reason to force an immediate
        close, or None to hold. Implements Gemini's signal-flip exit proposal
        (2026-09-29 audit) through a REAL engine hook: mutating indicator dicts
        has no effect on the engine's own stop_loss/take_profit fields.
        """
        if self.p.signal_exit_threshold is None:
            return None
        buf = self._buffers[self.execution_tf]
        if len(buf) < self._min_history:
            return None
        df = pd.DataFrame(buf).set_index("timestamp")
        sig = self._compute_signal(df)
        if sig is None:
            return None
        self._last_indicators["manage_signal"] = round(sig, 4)
        if position == "long" and sig <= -self.p.signal_exit_threshold:
            return "signal_flip"
        if position == "short" and sig >= self.p.signal_exit_threshold:
            return "signal_flip"
        return None

    # ── internals ──────────────────────────────────────────────────

    def _compute_signal(self, df: pd.DataFrame) -> Optional[float]:
        try:
            s = self._mod.calculate_math_signal(df)
            s = pd.Series(s).astype(float)
            if self.p.signal_smoothing and self.p.signal_smoothing > 1:
                s = s.ewm(span=int(self.p.signal_smoothing), adjust=False).mean()
            s = s.fillna(0.0).clip(-1.0, 1.0)
            if len(s) == 0:
                return None
            return float(s.iloc[-1])
        except Exception as e:
            if not self._formula_error_logged:
                logger.error(f"formula {self.formula_name} raised: {e}")
                self._formula_error_logged = True
            return None

    def _compute_atr(self, df: pd.DataFrame) -> float:
        h, l, c = df["high"], df["low"], df["close"]
        prev_c = c.shift(1)
        tr = pd.concat(
            [h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1
        ).max(axis=1)
        atr = tr.ewm(alpha=1.0 / max(int(self.p.atr_period), 1), adjust=False).mean()
        val = float(atr.iloc[-1])
        return val if val > 0 else float(c.iloc[-1]) * 0.01  # 1% fallback

    def _bias_trend(self) -> Optional[bool]:
        """True=bullish, False=bearish, None=filter off/insufficient data."""
        if not self.p.use_bias_filter or not self.bias_tfs:
            return None
        buf = self._buffers.get(self.bias_tfs[0])
        if not buf or len(buf) < self.p.bias_slow:
            return None
        df = pd.DataFrame(buf).set_index("timestamp")
        fast = df["close"].ewm(span=self.p.bias_fast, adjust=False).mean().iloc[-1]
        slow = df["close"].ewm(span=self.p.bias_slow, adjust=False).mean().iloc[-1]
        return bool(fast > slow)


================================================================================
FILE: framework/simulation.py — run() tick loop (CURRENT — includes manage_position hook)
================================================================================

    def run(
        self,
        data_files: Dict[str, str],
        execution_tf: str,
        data_start: Optional[str] = None,
        data_end: Optional[str] = None,
    ) -> SimulationResult:
        """
        Execute simulation over an arbitrary set of timeframes.

        Args:
            data_files: {"5m": "/path/to/btc_5m.csv", "1h": "/path/to/btc_1h.csv", ...}
                        Must include execution_tf as one key.
            execution_tf: which timeframe's candles drive the tick loop
            data_start, data_end: optional date filters (ISO strings)

        ⚠️ All SL/TP checks use CLOSE price only — never high/low.
        """
        if execution_tf not in data_files:
            raise ValueError(
                f"execution_tf '{execution_tf}' not found in data_files keys: "
                f"{list(data_files.keys())}"
            )

        # ── Load all dataframes ──────────────────────────────────
        dfs: Dict[str, pd.DataFrame] = {}
        timestamps: Dict[str, List[pd.Timestamp]] = {}
        for tf, path in data_files.items():
            df = pd.read_csv(path, parse_dates=["timestamp"], index_col="timestamp")
            df.sort_index(inplace=True)
            if data_start:
                df = df[df.index >= pd.Timestamp(data_start)]
            if data_end:
                df = df[df.index <= pd.Timestamp(data_end)]
            dfs[tf] = df
            timestamps[tf] = list(df.index)

        # ── Execution timeframe drives the loop ──────────────────
        exec_df = dfs[execution_tf]
        bias_tfs = [tf for tf in data_files if tf != execution_tf]

        # Track how far we've fed into each bias TF
        bias_idxs: Dict[str, int] = {tf: 0 for tf in bias_tfs}

        n_bias = len(bias_tfs)
        logger.info(
            f"Sim: {len(exec_df)} candles ({execution_tf}) | "
            f"bias TFs={bias_tfs} ({n_bias}) | "
            f"capital={self.initial_capital} | shorts={'on' if self.allow_shorts else 'off'}"
        )

        # ── Main tick loop ───────────────────────────────────────
        for ts, row in exec_df.iterrows():
            price = float(row["close"])

            # Feed bias TF candles up to current execution timestamp
            for tf in bias_tfs:
                ts_list = timestamps[tf]
                bdf = dfs[tf]
                idx = bias_idxs[tf]
                while idx < len(ts_list) and ts_list[idx] <= ts:
                    self.model.update(bdf.loc[ts_list[idx]], tf)
                    idx += 1
                bias_idxs[tf] = idx

            # Feed execution TF candle
            self.model.update(row, execution_tf)

            # ── Step 1: Check exit conditions if in position ──────
            if self.position is not None:
                # Optional model-managed exit hook (backward compatible:
                # models without manage_position behave exactly as before).
                if hasattr(self.model, "manage_position"):
                    reason = self.model.manage_position(self.position, price, ts)
                    if reason:
                        self._do_exit(price, ts, f"model_exit:{reason}")
                if self.position == "long":
                    if price <= self.stop_loss:
                        self._do_exit(price, ts, "stop_loss")
                    elif price >= self.take_profit:
                        self._do_exit(price, ts, "take_profit")
                elif self.position == "short":
                    if price >= self.stop_loss:
                        self._do_exit(price, ts, "stop_loss")
                    elif price <= self.take_profit:
                        self._do_exit(price, ts, "take_profit")

            # ── Step 2: Check for new entry signal ────────────────
            if self.position is None:
                action, size_pct, indicators = self.model.predict(
                    allow_shorts=self.allow_shorts
                )
                if action != "flat":
                    sl = indicators.get("stop_loss", 0.0)
                    tp = indicators.get("take_profit", 0.0)
                    if sl > 0 and tp > 0:
                        self._do_enter(action, price, size_pct, ts, sl, tp)

            # ── Step 3: Record ────────────────────────────────────
            eq = self._eq(price)
            self.equity_history.append({
                "timestamp": ts,
                "equity": eq,
                "position": self.position,
                "price": price,
                "cash": self.cash,
                "crypto_qty": self.crypto_qty,
            })
            self.indicators_hist.append(self.model.get_indicators())

        # Force-close at end
        if self.position and len(exec_df) > 0:
            close_price = float(exec_df.iloc[-1]["close"])
            self._do_exit(close_price, exec_df.index[-1], "force_close")

        return self._build_result()

    

================================================================================
FILE: tuner/alpha_orchestrator.py  (CURRENT — pad + gates v2 + exit threshold in space)
================================================================================

"""Alpha Orchestrator — walk-forward tuning + promotion gates for LLM-mined alphas.

Corrected rewrite of Gemini's 2026-09-28 design (same name/API shape kept for
review continuity). Fixes over the original:
  1. RunResult access: metrics live in result.metadata / .equity_curve
     (SimulationResult) — the original read non-existent attributes and every
     trial silently scored -inf.
  2. Walk-forward: per-window Optuna on TRAIN, OOS evaluation on VALID, final
     held-out TEST — the original optimized a single fixed window in-sample.
  3. Benchmark alignment: B&H computed on the exact evaluated window
     (the original used the full cached CSV range).
  4. Honest score: excess return over B&H minus an explicit overtrade penalty
     ("JEV" renamed; rf/beta window-unit mismatch dropped).
  5. Paths anchored to repo root; TrialPruned instead of -inf where possible.

Protocol detail that shapes everything: the engine calls predict() only when
FLAT (entry-only), exits are ATR SL/TP. One continuous backtest covers
[train_start, valid_end]; metrics are SLICED per segment so the model's
warm-up isn't paid twice and trading is continuous across the boundary.

Usage:
  python3 tuner/alpha_orchestrator.py --formula alpha_001 --trials 12 --windows 3
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
import time
from dataclasses import asdict
from typing import Dict, List, Optional

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from framework.data_loader import load_candles          # noqa: E402
from framework.runner import RunConfig, run_strategy     # noqa: E402
from models.wq_alpha_miner import WQAlphaMinerModel, WQAlphaParams  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("orchestrator")

RUNS_DIR = os.path.join(REPO_ROOT, "tuner", "runs")
OVERTRADE_PENALTY = 0.001  # per-trade fee-load prior (fees already simulated)


# ── metrics from an equity slice ──────────────────────────────────────

def slice_metrics(eq_df: pd.DataFrame, start: str, end: str, bench_df: pd.DataFrame) -> Dict:
    m = eq_df[(eq_df["timestamp"] >= pd.Timestamp(start)) & (eq_df["timestamp"] <= pd.Timestamp(end))]
    b = bench_df[(bench_df.index >= pd.Timestamp(start)) & (bench_df.index <= pd.Timestamp(end))]
    if len(m) < 2 or len(b) < 2:
        return {"ok": False}
    eq = m["equity"].astype(float)
    ret = eq.iloc[-1] / eq.iloc[0] - 1.0
    peak = eq.cummax()
    mdd = float(((peak - eq) / peak).max())
    entries = int(((m["position"].notna()) & (m["position"].shift(1).isna())).sum())
    bench_ret = float(b["close"].iloc[-1] / b["close"].iloc[0] - 1.0)
    # daily-sharpe from equity samples (exec-tf cadence, annualized 365d)
    steps_per_day = max(len(m) / max((m["timestamp"].iloc[-1] - m["timestamp"].iloc[0]).total_seconds() / 86400.0, 1e-9), 1.0)
    r = eq.pct_change().dropna()
    sharpe = float(r.mean() / r.std() * (365.0 * steps_per_day) ** 0.5) if len(r) > 2 and r.std() > 0 else 0.0
    return {
        "ok": True, "return_pct": round(ret * 100, 3), "bench_pct": round(bench_ret * 100, 3),
        "excess_pct": round((ret - bench_ret) * 100, 3), "mdd_pct": round(mdd * 100, 2),
        "entries": entries, "sharpe": round(sharpe, 2),
        "score": round((ret - bench_ret - OVERTRADE_PENALTY * entries) * 100, 3),
    }


def run_backtest(params: WQAlphaParams, symbol: str, exec_tf: str, bias_tf: str,
                 csv_paths: Dict[str, str], start: str, end: str) -> Optional[pd.DataFrame]:
    model = WQAlphaMinerModel(params, execution_tf=exec_tf, bias_tfs=[bias_tf])
    # 3-day lookback pad: saturate model buffers (warmup, EWM smoothing) BEFORE the
    # measured window starts — removes the 15h+ dead zone at window start (audit Q2).
    padded_start = (pd.Timestamp(start) - pd.Timedelta(days=3)).isoformat()
    cfg = RunConfig(
        data_files={exec_tf: csv_paths[exec_tf], bias_tf: csv_paths[bias_tf]},
        execution_tf=exec_tf, model=model, initial_capital=10_000.0,
        fee=0.0008, exchange="simulation", allow_shorts=True,
        data_start=padded_start, data_end=end,
    )
    res = run_strategy(cfg)
    if not res.success or res.equity_curve is None:
        return None
    return res.equity_curve.equity_curve  # DataFrame(timestamp, equity, position, ...)


# ── walk-forward windows ──────────────────────────────────────────────

def build_windows(data_start: pd.Timestamp, data_end: pd.Timestamp, train_d: int,
                  valid_d: int, slide_d: int, n_windows: int) -> List[Dict]:
    wins: List[Dict] = []
    v_end = data_end
    while True:
        v_start = v_end - pd.Timedelta(days=valid_d)
        t_start = v_start - pd.Timedelta(days=train_d)
        if t_start < data_start:
            break
        wins.append({
            "train": (t_start.isoformat(), v_start.isoformat()),
            "valid": (v_start.isoformat(), v_end.isoformat()),
        })
        v_end = v_end - pd.Timedelta(days=slide_d)
    return list(reversed(wins))[-n_windows:]  # most recent N, chronological


# ── gates ─────────────────────────────────────────────────────────────

def latest_champion(symbol: str, exec_tf: str) -> Optional[Dict]:
    reports = sorted(glob.glob(os.path.join(RUNS_DIR, "*.json")))
    for path in reversed(reports):
        try:
            r = json.load(open(path))
            if r.get("verdict") == "PROMOTE" and r.get("symbol") == symbol \
               and r.get("exec_tf") == exec_tf:
                return r
        except Exception:
            continue
    return None


def evaluate_gates(windows: List[Dict], test: Optional[Dict], champ: Optional[Dict],
                   per_window_floor: float = -1.0, mean_hurdle: float = 2.0,
                   min_total_entries: int = 50) -> Dict:
    valid_metrics = [w["valid"] for w in windows if w["valid"].get("ok")]
    oos_mean_excess = sum(v["excess_pct"] for v in valid_metrics) / max(len(valid_metrics), 1)
    total_entries = sum(v["entries"] for v in valid_metrics)
    if len(valid_metrics) >= 2:
        vals = [v["excess_pct"] for v in valid_metrics]
        mu = sum(vals) / len(vals)
        sd = (sum((x - mu) ** 2 for x in vals) / len(vals)) ** 0.5
        t_score = round(mu / sd, 2) if sd > 0 else (99.0 if mu > 0 else 0.0)
    else:
        t_score = None
    floor_windows = [v for v in valid_metrics if v["bench_pct"] < 0]
    floor_ok = all(v["return_pct"] >= 0 for v in floor_windows) if floor_windows else True
    per_window_ok = bool(valid_metrics) and all(v["excess_pct"] > per_window_floor for v in valid_metrics)
    mean_ok = oos_mean_excess > mean_hurdle
    entries_ok = total_entries >= min_total_entries
    test_ok = test is not None and test.get("ok")
    test_beat = test_ok and test["excess_pct"] > 0
    test_floor_ok = (not test_ok) or (test["bench_pct"] >= 0 or test["return_pct"] >= 0)
    edge = {"champion": champ["label"] if champ else None,
            "champion_oos_mean_excess": champ["oos"]["mean_excess_pct"] if champ else None,
            "passed": None}
    if champ is not None:
        edge["passed"] = oos_mean_excess > champ["oos"]["mean_excess_pct"]
    failed = []
    if not per_window_ok: failed.append(f"per_window_floor({per_window_floor})")
    if not mean_ok: failed.append(f"mean_hurdle({mean_hurdle})")
    if not entries_ok: failed.append(f"min_total_entries({min_total_entries}, got {total_entries})")
    if not floor_ok: failed.append("capital_floor")
    if not test_beat: failed.append("test_market_beat")
    if not test_floor_ok: failed.append("test_floor")
    if edge["passed"] is False: failed.append("edge_vs_champion")
    verdict = "PROMOTE" if not failed else "REJECT"
    return {"oos_mean_excess_pct": round(oos_mean_excess, 3),
            "oos_total_entries": total_entries, "consistency_t_score": t_score,
            "floor_windows": len(floor_windows), "capital_floor_passed": floor_ok,
            "per_window_floor_passed": per_window_ok, "mean_hurdle_passed": mean_ok,
            "entries_gate_passed": entries_ok,
            "market_beat_passed": per_window_ok and mean_ok and test_beat,
            "test_floor_passed": test_floor_ok,
            "edge": edge, "failed_gates": failed, "verdict": verdict}


# ── main ──────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--formula", default="alpha_001")
    ap.add_argument("--symbol", default="ETH/USDT")
    ap.add_argument("--exec-tf", default="15m")
    ap.add_argument("--bias-tf", default="1h")
    ap.add_argument("--start", default="2026-06-15")
    ap.add_argument("--end", default="2026-09-28")
    ap.add_argument("--windows", type=int, default=3)
    ap.add_argument("--trials", type=int, default=40)
    ap.add_argument("--train-days", type=int, default=14)
    ap.add_argument("--valid-days", type=int, default=7)
    ap.add_argument("--slide-days", type=int, default=7)
    ap.add_argument("--test-days", type=int, default=10)
    ap.add_argument("--per-window-floor", type=float, default=-1.0)
    ap.add_argument("--mean-hurdle", type=float, default=2.0)
    ap.add_argument("--min-total-entries", type=int, default=50)
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    os.makedirs(RUNS_DIR, exist_ok=True)
    label = args.label or f"{args.formula}_{args.symbol.replace('/', '')}_{pd.Timestamp.now('UTC').strftime('%Y%m%d_%H%M%S')}"

    # 1) data
    csv_paths: Dict[str, str] = {}
    start_utc = pd.Timestamp(args.start, tz="UTC").isoformat()
    end_utc = pd.Timestamp(args.end, tz="UTC").isoformat()
    for tf in (args.exec_tf, args.bias_tf):
        log.warning(f"loading {args.symbol} {tf} {args.start}..{args.end}")
        _, path, n = load_candles(symbol=args.symbol, timeframe=tf,
                                  start=start_utc, end=end_utc)
        csv_paths[tf] = path
        log.warning(f"  -> {n} candles: {path}")
    exec_df = pd.read_csv(csv_paths[args.exec_tf], parse_dates=["timestamp"], index_col="timestamp")
    exec_df = exec_df[(exec_df.index >= args.start) & (exec_df.index <= args.end)]

    data_start, data_end = exec_df.index[0], exec_df.index[-1]
    test_end = data_end
    test_start = test_end - pd.Timedelta(days=args.test_days)
    wf_end = test_start - pd.Timedelta(minutes=1)
    windows = build_windows(data_start, wf_end, args.train_days, args.valid_days,
                            args.slide_days, args.windows)
    log.warning(f"windows: {len(windows)} | test: {test_start.date()}..{test_end.date()}")

    # 2) per-window Optuna on TRAIN, OOS slice on VALID (same continuous run)
    def make_params(trial) -> WQAlphaParams:
        return WQAlphaParams(
            formula_path=args.formula,
            long_threshold=trial.suggest_float("long_threshold", 0.30, 0.90),
            short_threshold=trial.suggest_float("short_threshold", 0.30, 0.90),
            signal_smoothing=trial.suggest_int("signal_smoothing", 3, 21),
            atr_stop_mult=trial.suggest_float("atr_stop_mult", 1.0, 4.0),
            atr_take_mult=trial.suggest_float("atr_take_mult", 1.0, 5.0),
            use_bias_filter=trial.suggest_categorical("use_bias_filter", [True, False]),
            signal_exit_threshold=trial.suggest_categorical(
                "signal_exit_threshold", [None, 0.3, 0.4, 0.5]),
        )

    results: List[Dict] = []
    for wi, w in enumerate(windows):
        t0 = time.time()

        def objective(trial):
            p = make_params(trial)
            eq = run_backtest(p, args.symbol, args.exec_tf, args.bias_tf, csv_paths,
                              w["train"][0], w["valid"][1])
            if eq is None:
                raise optuna.TrialPruned()
            tm = slice_metrics(eq, *w["train"], exec_df)
            if not tm.get("ok"):
                raise optuna.TrialPruned()
            return tm["score"]

        study = optuna.create_study(direction="maximize",
                                    sampler=optuna.samplers.TPESampler(seed=42 + wi))
        study.optimize(objective, n_trials=args.trials, show_progress_bar=False)

        best = WQAlphaParams(formula_path=args.formula, **study.best_params)
        eq = run_backtest(best, args.symbol, args.exec_tf, args.bias_tf, csv_paths,
                          w["train"][0], w["valid"][1])
        tm = slice_metrics(eq, *w["train"], exec_df)
        vm = slice_metrics(eq, *w["valid"], exec_df)
        results.append({"train_span": w["train"], "valid_span": w["valid"],
                        "best_params": study.best_params,
                        "train": tm, "valid": vm,
                        "sec": round(time.time() - t0, 1)})
        log.warning(f"w{wi}: train score={tm.get('score')} valid excess={vm.get('excess_pct')}% ({results[-1]['sec']}s)")

    # 3) OOS-champion params -> final TEST holdout
    scored = [r for r in results if r["valid"].get("ok")]
    best_row = max(scored, key=lambda r: r["valid"]["score"]) if scored else None
    test: Optional[Dict] = None
    if best_row:
        p = WQAlphaParams(formula_path=args.formula, **best_row["best_params"])
        test_backtest_start = pd.Timestamp(best_row["valid_span"][1]) - pd.Timedelta(days=2)
        eq = run_backtest(p, args.symbol, args.exec_tf, args.bias_tf, csv_paths,
                          test_backtest_start.isoformat(), test_end.isoformat())
        test = slice_metrics(eq, test_start.isoformat(), test_end.isoformat(), exec_df)

    # 4) gates + report
    champ = latest_champion(args.symbol, args.exec_tf)
    gates = evaluate_gates(results, test, champ,
                           per_window_floor=args.per_window_floor,
                           mean_hurdle=args.mean_hurdle,
                           min_total_entries=args.min_total_entries)
    report = {
        "label": label, "formula": args.formula,
        "formula_hash": WQAlphaMinerModel(
            WQAlphaParams(formula_path=args.formula), args.exec_tf, [args.bias_tf]
        ).formula_hash,
        "symbol": args.symbol, "exec_tf": args.exec_tf, "bias_tf": args.bias_tf,
        "data": {"start": str(data_start), "end": str(data_end), "candles": len(exec_df)},
        "windows": results, "test": test, "gates": gates,
        "oos": {"mean_excess_pct": gates["oos_mean_excess_pct"]},
        "overtrade_penalty_per_entry": OVERTRADE_PENALTY,
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
    }
    out = os.path.join(RUNS_DIR, f"{label}.json")
    with open(out, "w") as f:
        json.dump(report, f, indent=1, default=str)
    log.warning(f"VERDICT {gates['verdict']} | OOS mean excess {gates['oos_mean_excess_pct']}% | report: {out}")
    return 0 if gates["verdict"] == "PROMOTE" else 1


if __name__ == "__main__":
    sys.exit(main())


================================================================================
FILE: models/alpha_formulas/README.md  (contract v2)
================================================================================

# alpha_formulas/ — LLM-generated alpha formulas

## Contract (mandatory)

Each file `alpha_NNN.py` exposes exactly:

```python
def calculate_math_signal(df: pd.DataFrame) -> pd.Series
```

- `df`: UTC-indexed OHLCV DataFrame (`open, high, low, close, volume`), ascending.
- Returns a Series aligned with `df.index`, values **clipped to [-1, 1]**
  (`>= 0` = bullish pressure, `<= 0` = bearish pressure; magnitude = conviction).
- **Causal operations only** — a signal at time t may use data with
  timestamp <= t. No `shift(-n)`, no centered windows, no future leakage.
- **No full-sample operators**: no global `df.rank()` / `df.mean()` /
  `df.max()` etc. Every statistic must be trailing (`.rolling(w, min_periods=y)`).
- **Bounded transforms recommended**: prefer `np.tanh(...)` or rank/z-score
  scaling INSIDE the formula so thresholds are comparable across formulas.
  (The wrapper hard-clips to [-1, 1] as the final guarantee regardless.)
- Imports: `pandas` / `numpy` only. No I/O, no network, no heavy work at
  import time. Deterministic: same df -> same output.
- NaN/Inf handling is centralized in the wrapper (fillna(0) + clip); formulas
  do NOT need their own fallback code — keep them mathematically pure.

## Semantics (important)

The engine calls `predict()` ONLY when flat: your signal triggers ENTRIES.
Exits are handled by ATR-based stop-loss/take-profit (wrapper-managed).
So: make the signal fire at entry-worthy extremes, not as a continuous rating.

## Header template

```python
"""
alpha_001 — <short name>
Hypothesis: <one paragraph: WHY this should have edge, what regime it targets>
Author: <AI model / human>   Date: <YYYY-MM-DD>
Inputs: OHLCV only   Provenance: <inspired by WQ #NNN / original>
"""
```

The wrapper records the file's sha256 in every run report for provenance.


================================================================================
EVIDENCE: empirical proofs run 2026-09-29 (verbatim output)
================================================================================

A) EQUIVALENCE: IDENTICAL | rolling.rank: 3ms vs .apply: 329ms -> 97x slower
B) CAUSALITY: truncated == full at row 2500: True
C) GLOBAL rank trunc-vs-full delta: 0.0003 (non-zero = uses future data -> banned)

exit hook OFF:      ret=-0.03% trades=19 reasons={'stop_loss': 11, 'take_profit': 8}
exit hook ON (0.3): ret=-0.03% trades=22 reasons={'stop_loss': 10, 'take_profit': 5, 'model_exit:signal_flip': 7}
HOOK VERIFIED: inert when off, fires signal_flip when on

================================================================================
FILE: tuner/runs/alpha_001_dryrun3.json  (old-protocol report)
================================================================================

{
 "label": "alpha_001_dryrun3",
 "formula": "alpha_001",
 "formula_hash": "d85a6f569c16",
 "symbol": "ETH/USDT",
 "exec_tf": "15m",
 "bias_tf": "1h",
 "data": {
  "start": "2026-06-15 00:00:00+00:00",
  "end": "2026-09-28 00:00:00+00:00",
  "candles": 10081
 },
 "windows": [
  {
   "train_span": [
    "2026-08-13T23:59:00+00:00",
    "2026-08-27T23:59:00+00:00"
   ],
   "valid_span": [
    "2026-08-27T23:59:00+00:00",
    "2026-09-03T23:59:00+00:00"
   ],
   "best_params": {
    "long_threshold": 0.4109126733153162,
    "short_threshold": 0.8817507766587351,
    "signal_smoothing": 17,
    "atr_stop_mult": 3.8184968246925672,
    "atr_take_mult": 4.579309401710596,
    "use_bias_filter": false
   },
   "train": {
    "ok": true,
    "return_pct": 12.89,
    "bench_pct": 33.125,
    "excess_pct": -20.235,
    "mdd_pct": 3.93,
    "entries": 5,
    "sharpe": 9.08,
    "score": -20.735
   },
   "valid": {
    "ok": true,
    "return_pct": 5.685,
    "bench_pct": -0.028,
    "excess_pct": 5.713,
    "mdd_pct": 4.87,
    "entries": 2,
    "sharpe": 8.08,
    "score": 5.513
   },
   "sec": 63.8
  },
  {
   "train_span": [
    "2026-08-20T23:59:00+00:00",
    "2026-09-03T23:59:00+00:00"
   ],
   "valid_span": [
    "2026-09-03T23:59:00+00:00",
    "2026-09-10T23:59:00+00:00"
   ],
   "best_params": {
    "long_threshold": 0.3730372837941419,
    "short_threshold": 0.43693563828929816,
    "signal_smoothing": 8,
    "atr_stop_mult": 2.681875031881698,
    "atr_take_mult": 2.717824804991709,
    "use_bias_filter": false
   },
   "train": {
    "ok": true,
    "return_pct": 10.451,
    "bench_pct": 7.275,
    "excess_pct": 3.176,
    "mdd_pct": 6.59,
    "entries": 19,
    "sharpe": 5.65,
    "score": 1.276
   },
   "valid": {
    "ok": true,
    "return_pct": 2.919,
    "bench_pct": -2.777,
    "excess_pct": 5.696,
    "mdd_pct": 3.23,
    "entries": 10,
    "sharpe": 4.17,
    "score": 4.696
   },
   "sec": 95.0
  },
  {
   "train_span": [
    "2026-08-27T23:59:00+00:00",
    "2026-09-10T23:59:00+00:00"
   ],
   "valid_span": [
    "2026-09-10T23:59:00+00:00",
    "2026-09-17T23:59:00+00:00"
   ],
   "best_params": {
    "long_threshold": 0.4307393216079145,
    "short_threshold": 0.8744832414407504,
    "signal_smoothing": 20,
    "atr_stop_mult": 3.645472843469493,
    "atr_take_mult": 3.585642249613574,
    "use_bias_filter": false
   },
   "train": {
    "ok": true,
    "return_pct": 3.361,
    "bench_pct": -2.791,
    "excess_pct": 6.153,
    "mdd_pct": 2.97,
    "entries": 6,
    "sharpe": 3.7,
    "score": 5.553
   },
   "valid": {
    "ok": true,
    "return_pct": 1.801,
    "bench_pct": -0.058,
    "excess_pct": 1.859,
    "mdd_pct": 5.53,
    "entries": 3,
    "sharpe": 2.54,
    "score": 1.559
   },
   "sec": 109.3
  }
 ],
 "test": {
  "ok": true,
  "return_pct": 0.326,
  "bench_pct": 9.917,
  "excess_pct": -9.59,
  "mdd_pct": 3.61,
  "entries": 5,
  "sharpe": 0.57,
  "score": -10.09
 },
 "gates": {
  "oos_mean_excess_pct": 4.423,
  "floor_windows": 3,
  "capital_floor_passed": true,
  "market_beat_passed": "False",
  "test_floor_passed": true,
  "edge": {
   "champion": null,
   "champion_oos_mean_excess": null,
   "passed": null
  },
  "verdict": "REJECT"
 },
 "oos": {
  "mean_excess_pct": 4.423
 },
 "overtrade_penalty_per_entry": 0.001,
 "generated_at": "2026-09-28T19:59:29.522297+00:00"
}

================================================================================
FILE: tuner/runs/alpha_001_gates_v2.json  (corrected-protocol report)
================================================================================

{
 "label": "alpha_001_gates_v2",
 "formula": "alpha_001",
 "formula_hash": "d85a6f569c16",
 "symbol": "ETH/USDT",
 "exec_tf": "15m",
 "bias_tf": "1h",
 "data": {
  "start": "2026-06-15 00:00:00+00:00",
  "end": "2026-09-28 00:00:00+00:00",
  "candles": 10081
 },
 "windows": [
  {
   "train_span": [
    "2026-08-13T23:59:00+00:00",
    "2026-08-27T23:59:00+00:00"
   ],
   "valid_span": [
    "2026-08-27T23:59:00+00:00",
    "2026-09-03T23:59:00+00:00"
   ],
   "best_params": {
    "long_threshold": 0.3845545349848576,
    "short_threshold": 0.7813181884524238,
    "signal_smoothing": 4,
    "atr_stop_mult": 3.960660809801552,
    "atr_take_mult": 4.08897907718663,
    "use_bias_filter": true,
    "signal_exit_threshold": null
   },
   "train": {
    "ok": true,
    "return_pct": 11.89,
    "bench_pct": 33.125,
    "excess_pct": -21.235,
    "mdd_pct": 6.13,
    "entries": 8,
    "sharpe": 6.96,
    "score": -22.035
   },
   "valid": {
    "ok": true,
    "return_pct": -3.97,
    "bench_pct": -0.028,
    "excess_pct": -3.942,
    "mdd_pct": 5.88,
    "entries": 6,
    "sharpe": -4.98,
    "score": -4.542
   },
   "sec": 140.6
  },
  {
   "train_span": [
    "2026-08-20T23:59:00+00:00",
    "2026-09-03T23:59:00+00:00"
   ],
   "valid_span": [
    "2026-09-03T23:59:00+00:00",
    "2026-09-10T23:59:00+00:00"
   ],
   "best_params": {
    "long_threshold": 0.536364335894424,
    "short_threshold": 0.8007332058048127,
    "signal_smoothing": 12,
    "atr_stop_mult": 2.84560063149084,
    "atr_take_mult": 3.9523379282169473,
    "use_bias_filter": true,
    "signal_exit_threshold": null
   },
   "train": {
    "ok": true,
    "return_pct": 7.631,
    "bench_pct": 7.275,
    "excess_pct": 0.356,
    "mdd_pct": 2.97,
    "entries": 6,
    "sharpe": 6.57,
    "score": -0.244
   },
   "valid": {
    "ok": true,
    "return_pct": -1.406,
    "bench_pct": -2.777,
    "excess_pct": 1.37,
    "mdd_pct": 3.04,
    "entries": 3,
    "sharpe": -5.32,
    "score": 1.07
   },
   "sec": 162.5
  },
  {
   "train_span": [
    "2026-08-27T23:59:00+00:00",
    "2026-09-10T23:59:00+00:00"
   ],
   "valid_span": [
    "2026-09-10T23:59:00+00:00",
    "2026-09-17T23:59:00+00:00"
   ],
   "best_params": {
    "long_threshold": 0.8009052891993897,
    "short_threshold": 0.36287766262192184,
    "signal_smoothing": 17,
    "atr_stop_mult": 2.0815025087688572,
    "atr_take_mult": 2.4372433512322877,
    "use_bias_filter": true,
    "signal_exit_threshold": 0.5
   },
   "train": {
    "ok": true,
    "return_pct": 0.61,
    "bench_pct": -2.791,
    "excess_pct": 3.401,
    "mdd_pct": 4.31,
    "entries": 5,
    "sharpe": 0.72,
    "score": 2.901
   },
   "valid": {
    "ok": true,
    "return_pct": -1.673,
    "bench_pct": -0.058,
    "excess_pct": -1.615,
    "mdd_pct": 3.23,
    "entries": 3,
    "sharpe": -5.36,
    "score": -1.915
   },
   "sec": 156.8
  }
 ],
 "test": {
  "ok": true,
  "return_pct": 1.939,
  "bench_pct": 9.917,
  "excess_pct": -7.978,
  "mdd_pct": 2.04,
  "entries": 4,
  "sharpe": 5.21,
  "score": -8.378
 },
 "gates": {
  "oos_mean_excess_pct": -1.396,
  "oos_total_entries": 12,
  "consistency_t_score": -0.64,
  "floor_windows": 3,
  "capital_floor_passed": false,
  "per_window_floor_passed": false,
  "mean_hurdle_passed": "False",
  "entries_gate_passed": false,
  "market_beat_passed": false,
  "test_floor_passed": true,
  "edge": {
   "champion": null,
   "champion_oos_mean_excess": null,
   "passed": null
  },
  "failed_gates": [
   "per_window_floor(-1.0)",
   "mean_hurdle(2.0)",
   "min_total_entries(50, got 12)",
   "capital_floor",
   "test_market_beat"
  ],
  "verdict": "REJECT"
 },
 "oos": {
  "mean_excess_pct": -1.396
 },
 "overtrade_penalty_per_entry": 0.001,
 "generated_at": "2026-09-29T05:56:05.000730+00:00"
}

================================================================================
END OF PACK v2
================================================================================
