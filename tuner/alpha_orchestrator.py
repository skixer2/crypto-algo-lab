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
