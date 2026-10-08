#!/usr/bin/env python3
"""Walk-forward study for the CompositeRouter (deployment-candidate path).

Usage:
  python3 tuner/study_router.py --label router_45y_v1 \
      --start 2021-01-01 --end 2026-07-28 --windows 12 \
      --train-days 90 --test-days 30 --trials 15 [--final-run]

- Each window: Optuna (TPE, seed) tunes RouterParams on the TRAIN slice,
  frozen best params evaluated on the TEST slice. No leakage: test data is
  never seen during tuning; holdout.py seal enforced on --end.
- Reports mean OOS excess vs B&H across test slices + per-window table;
  writes tuner/runs/<label>.json (same runs dir as alpha studies).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from models.composite_router import CompositeRouterModel, RouterParams
from tuner.holdout import guard_data_end

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import argparse as _ap
_pre = _ap.ArgumentParser(add_help=False)
_pre.add_argument("--symbol", default="ETH/USDT")
_args, _ = _pre.parse_known_args()
_sym = _args.symbol.replace("/", "_")
EXEC = os.path.join(REPO, "framework", "data_cache", f"okx_{_sym}_15m_20210101_20260928.csv")
BIAS = os.path.join(REPO, "framework", "data_cache", f"okx_{_sym}_1h_20210101_20260928.csv")
PAD_DAYS = 7  # warmup pad: 7d = 672 bars > max(donchian 288 + confirm 96, warmup 400)


def _run_sim(params: RouterParams, start, end):
    from framework.runner import RunConfig, run_strategy

    pad = (start - timedelta(days=PAD_DAYS)).isoformat()
    end_i = (end - timedelta(minutes=1)).isoformat()
    m = CompositeRouterModel(params, execution_tf="15m", bias_tfs=["1h"])
    m.bind_context(EXEC)
    cfg = RunConfig(data_files={"15m": EXEC, "1h": BIAS}, execution_tf="15m",
                    model=m, initial_capital=10_000.0, fee=0.0008,
                    exchange="simulation", allow_shorts=True,
                    data_start=pad, data_end=end_i)
    res = run_strategy(cfg)
    sim = res.equity_curve
    eq = sim.equity_curve
    m_slice = eq[eq["timestamp"] >= pd.Timestamp(start)]
    first = float(m_slice["equity"].iloc[0]) if len(m_slice) else float(eq["equity"].iloc[0])
    strat = (float(eq["equity"].iloc[-1]) / first - 1) * 100
    return strat, sim.total_trades


def _bench(start, end, bench_df):
    b = bench_df[(bench_df.index >= pd.Timestamp(start)) & (bench_df.index < pd.Timestamp(end))]
    return (float(b["close"].iloc[-1]) / float(b["close"].iloc[0]) - 1) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--symbol", default="ETH/USDT")
    ap.add_argument("--start", default="2021-01-01")
    ap.add_argument("--end", default="2026-07-28")
    ap.add_argument("--windows", type=int, default=12)
    ap.add_argument("--train-days", type=int, default=90)
    ap.add_argument("--test-days", type=int, default=30)
    ap.add_argument("--trials", type=int, default=15)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--final-run", action="store_true")
    args = ap.parse_args()

    end_ts = guard_data_end(args.end, final_run=args.final_run)
    s0 = pd.Timestamp(args.start, tz="UTC")
    e0 = end_ts
    span_days = (e0 - s0).days
    slide = (span_days - args.train_days - args.test_days) / max(args.windows - 1, 1)

    bench_df = pd.read_csv(EXEC, parse_dates=["timestamp"], index_col="timestamp").sort_index()

    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    results = []
    for w in range(args.windows):
        w_start = s0 + timedelta(days=slide * w)
        tr_end = w_start + timedelta(days=args.train_days)
        te_end = tr_end + timedelta(days=args.test_days)

        def objective(trial):
            p = RouterParams(
                donchian_bars=trial.suggest_int("donchian_bars", 96, 288, step=24),
                confirm_bars=trial.suggest_int("confirm_bars", 24, 96, step=24),
                grind_slope_bars=trial.suggest_int("grind_slope_bars", 48, 288, step=24),
                vol_compression=trial.suggest_float("vol_compression", 0.60, 0.95),
                meltup_threshold=trial.suggest_float("meltup_threshold", 0.20, 0.60),
                chop_threshold=trial.suggest_float("chop_threshold", 0.20, 0.60),
                down_threshold=trial.suggest_float("down_threshold", 0.20, 0.60),
                signal_smoothing=trial.suggest_int("signal_smoothing", 4, 16),
                atr_stop_mult=trial.suggest_float("atr_stop_mult", 3.0, 9.0),
                atr_take_mult=trial.suggest_float("atr_take_mult", 3.0, 12.0),
            )
            strat, trades = _run_sim(p, w_start, tr_end)
            bench = _bench(w_start, tr_end, bench_df)
            return strat - bench  # train excess

        study = optuna.create_study(direction="maximize",
                                     sampler=optuna.samplers.TPESampler(seed=args.seed + w))
        study.optimize(objective, n_trials=args.trials, show_progress_bar=False)
        bp = study.best_params

        p = RouterParams(
            donchian_bars=bp["donchian_bars"], confirm_bars=bp["confirm_bars"], grind_slope_bars=bp["grind_slope_bars"],
            vol_compression=bp["vol_compression"],
            meltup_threshold=bp["meltup_threshold"], chop_threshold=bp["chop_threshold"],
            down_threshold=bp["down_threshold"],
            signal_smoothing=bp["signal_smoothing"],
            atr_stop_mult=bp["atr_stop_mult"], atr_take_mult=bp["atr_take_mult"],
        )
        strat, trades = _run_sim(p, tr_end, te_end)
        bench = _bench(tr_end, te_end, bench_df)
        results.append({
            "train": [str(w_start.date()), str(tr_end.date())],
            "test": [str(tr_end.date()), str(te_end.date())],
            "strat_pct": round(strat, 3), "bench_pct": round(bench, 3),
            "excess": round(strat - bench, 3), "test_trades": trades,
            "best_params": bp,
        })
        print(f"[w{w:02d}] test {tr_end.date()}→{te_end.date()}: strat={strat:+.2f} "
              f"bench={bench:+.2f} excess={strat - bench:+.2f} trades={trades}", flush=True)

    mean_excess = sum(r["excess"] for r in results) / len(results)
    n_pos = sum(1 for r in results if r["excess"] > 0)
    out = {"label": args.label, "mean_test_excess": round(mean_excess, 3),
           "windows_positive": n_pos, "windows": len(results),
           "results": results}
    path = os.path.join(REPO, "tuner", "runs", f"{args.label}.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"\n{args.label}: mean test excess {mean_excess:+.2f}% "
          f"({n_pos}/{len(results)} windows positive)\n-> {path}", flush=True)


if __name__ == "__main__":
    main()
