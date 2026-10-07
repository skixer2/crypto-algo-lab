"""Phase 2: regime-stratified walk-forward study.

Reuses alpha_orchestrator's backtest/metrics. Reads custom windows from
tuner/runs/phase2_windows.json (each: regime, train[s,e], valid[s,e]).
Per window: Optuna on TRAIN, honest OOS on VALID (same protocol as main loop).
Output: tuner/runs/phase2_<formula>.json
"""
from __future__ import annotations
import argparse, json, logging, os, sys, time
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from framework.data_loader import load_candles          # noqa: E402
from tuner.alpha_orchestrator import run_backtest, slice_metrics, OVERTRADE_PENALTY, RUNS_DIR  # noqa: E402
from models.wq_alpha_miner import WQAlphaParams          # noqa: E402
from models.wq_alpha_fast import prepare_fast_context    # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("phase2")

ap = argparse.ArgumentParser()
ap.add_argument("--formula", required=True)
ap.add_argument("--windows-file", default="tuner/runs/phase2_windows.json")
ap.add_argument("--trials", type=int, default=40)
ap.add_argument("--no-shorts", action="store_true")
ap.add_argument("--fee", type=float, default=0.0008)
ap.add_argument("--regimes", default="bear,bull,neutral", help="comma list of regimes to run")
args = ap.parse_args()

windows = json.load(open(args.windows_file))
want = set(args.regimes.split(","))
windows = [w for w in windows if w["regime"] in want]

from tuner.holdout import SEAL_DATE
def _aware(ts):
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
_seal = _aware(SEAL_DATE)
for w in windows:
    for k in ("train", "valid"):
        if _aware(w[k][1]) > _seal:
            raise SystemExit(f"HOLDOUT BREACH: {w['regime']} window {w[k]} crosses {_seal}")
csv_paths = {
    "15m": os.path.join(REPO, "framework", "data_cache", "okx_ETH_USDT_15m_20210101_20260928.csv"),
    "1h":  os.path.join(REPO, "framework", "data_cache", "okx_ETH_USDT_1h_20210101_20260928.csv"),
}
log.warning(f"using archive CSVs directly: {csv_paths}")
exec_df = pd.read_csv(csv_paths["15m"], parse_dates=["timestamp"], index_col="timestamp")
ctx = prepare_fast_context(csv_paths["15m"], csv_paths["1h"], args.formula)

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

def make_params(trial):
    return WQAlphaParams(
        formula_path=args.formula,
        long_threshold=trial.suggest_float("long_threshold", 0.15, 0.90),
        short_threshold=trial.suggest_float("short_threshold", 0.15, 0.90),
        signal_smoothing=trial.suggest_int("signal_smoothing", 3, 21),
        atr_stop_mult=trial.suggest_float("atr_stop_mult", 1.0, 8.0),
        atr_take_mult=trial.suggest_float("atr_take_mult", 1.0, 15.0),
        use_bias_filter=trial.suggest_categorical("use_bias_filter", [True, False]),
        signal_exit_threshold=trial.suggest_categorical(
            "signal_exit_threshold", [None, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5]),
    )

out = {"formula": args.formula, "protocol": "phase2-stratified", "windows": []}
for wi, w in enumerate(windows):
    t0 = time.time()

    def objective(trial):
        p = make_params(trial)
        eq = run_backtest(p, "ETH/USDT", "15m", "1h", csv_paths,
                          w["train"][0], w["valid"][1], ctx=ctx,
                          allow_shorts=not args.no_shorts, fee=args.fee)
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
    eq = run_backtest(best, "ETH/USDT", "15m", "1h", csv_paths,
                      w["train"][0], w["valid"][1], ctx=ctx,
                      allow_shorts=not args.no_shorts, fee=args.fee)
    rec = {"regime": w["regime"], "valid_span": w["valid"], "sec": round(time.time() - t0, 1)}
    if eq is not None:
        rec["train"] = slice_metrics(eq, *w["train"], exec_df)
        rec["valid"] = slice_metrics(eq, *w["valid"], exec_df)
        rec["best_params"] = study.best_params
    out["windows"].append(rec)
    v = rec.get("valid", {})
    log.warning(f"[{args.formula}] w{wi} {w['regime']:7s} valid {w['valid'][0][:10]}: "
                f"ret {v.get('return_pct','?')}% bench {v.get('bench_pct','?')}% "
                f"excess {v.get('excess_pct','?')}% ({rec['sec']}s)")

path = os.path.join(RUNS_DIR, f"phase2_{args.formula}.json")
json.dump(out, open(path, "w"), indent=1, default=str)
print("SAVED", path)
