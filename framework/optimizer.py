"""
Module 6 — Optimizer (INTERCHANGEABLE)

Wraps simulation (module 2) + Optuna to optimize model (module 3) params.
Includes median pruning and early stopping.

Input:  data_files dict, model class, param ranges
Output: best params, best result, study object

Timeframe-agnostic: accepts data_files dict + execution_tf.
"""

import logging
from typing import Any, Callable, Dict, Optional, Type

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─── Parameter search space ──────────────────────────────────────────

DEFAULT_PARAM_SPACE = {
    "swing_lookback":          {"type": "int",     "low": 3,  "high": 15},
    "min_swing_distance":      {"type": "int",     "low": 2,  "high": 10},
    "mss_confirm_candles":     {"type": "int",     "low": 1,  "high": 5},
    "rr_ratio":                {"type": "float",   "low": 1.0, "high": 4.0},
    "rejection_zone_pct":      {"type": "float",   "low": 0.001, "high": 0.02},
    "atr_stop_multiplier":     {"type": "float",   "low": 0.5, "high": 3.0},
    "atr_period":              {"type": "int",     "low": 7,  "high": 50},
    "use_three_candle_trigger":{"type": "categorical", "choices": [True, False]},
    "min_candles_for_bias":    {"type": "int",     "low": 10, "high": 50},
    "max_position_pct":        {"type": "float",   "low": 0.1, "high": 1.0},
    "leverage":                {"type": "int",     "low": 1,  "high": 1},  # placeholder
}


def suggest_params(trial, param_space: Dict = None) -> Dict:
    """Optuna trial → model param dict."""
    space = param_space or DEFAULT_PARAM_SPACE
    params = {}
    for name, spec in space.items():
        if spec["type"] == "int":
            params[name] = trial.suggest_int(name, spec["low"], spec["high"])
        elif spec["type"] == "float":
            params[name] = trial.suggest_float(name, spec["low"], spec["high"])
        elif spec["type"] == "categorical":
            params[name] = trial.suggest_categorical(name, spec["choices"])
    return params


def run_optuna_optimization(
    model_class: Type,
    data_files: Dict[str, str],
    execution_tf: str = "5m",
    n_trials: int = 100,
    initial_capital: float = 10000.0,
    fee: float = 0.0008,
    data_start: Optional[str] = None,
    data_end: Optional[str] = None,
    param_space: Optional[Dict] = None,
    objective_metric: str = "sharpe_ratio",
    study_name: str = "scalping_optimization",
    storage: Optional[str] = None,
    direction: str = "maximize",
    seed: int = 42,
    n_jobs: int = 1,
    allow_shorts: bool = False,
    n_startup_trials: int = 10,     # random exploration before TPE
    n_prune_warmup_steps: int = 5,  # trials before pruning kicks in
    prune_percentile: int = 25,     # prune bottom 25% at each step
) -> Dict[str, Any]:
    """
    Run Optuna optimization with median pruning.

    Args:
        model_class: ScalpingModel or compatible
        data_files: {"5m": "/path/btc_5m.csv", "1h": "/path/btc_1h.csv", ...}
        execution_tf: which TF drives the tick loop
        n_trials: max trials
        initial_capital, fee, data_start, data_end: forwarded to simulation
        param_space: search space dict
        objective_metric: SimulationResult field to optimize
        study_name: Optuna study name
        storage: Optuna DB URL (None = in-memory)
        direction: "maximize" or "minimize"
        seed: random seed
        n_jobs: parallel workers
        allow_shorts: pass to simulation
        n_startup_trials: random trials before TPE sampler
        n_prune_warmup_steps: trials before pruning begins
        prune_percentile: bottom percentile to prune

    Returns:
        {best_params, best_value, best_result, study, trials_df}
    """
    try:
        import optuna
    except ImportError:
        raise ImportError("pip install optuna")

    from .simulation import SimulationEngine
    from .model import ModelParams

    space = param_space or DEFAULT_PARAM_SPACE

    # Infer bias_tfs from data_files (everything except execution_tf)
    bias_tfs = [tf for tf in data_files if tf != execution_tf]

    def objective(trial: optuna.Trial) -> float:
        params_dict = suggest_params(trial, space)
        model_params = ModelParams(**params_dict)
        model = model_class(
            params=model_params,
            execution_tf=execution_tf,
            bias_tfs=bias_tfs,
        )

        engine = SimulationEngine(
            model=model, initial_capital=initial_capital, fee=fee,
            allow_shorts=allow_shorts,
        )
        result = engine.run(data_files, execution_tf, data_start, data_end)

        # Store trial attributes
        trial.set_user_attr("total_return_pct", result.total_return_pct)
        trial.set_user_attr("max_drawdown_pct", result.max_drawdown_pct)
        trial.set_user_attr("sharpe_ratio", result.sharpe_ratio)
        trial.set_user_attr("total_trades", result.total_trades)
        trial.set_user_attr("win_rate", result.win_rate)
        trial.set_user_attr("profit_factor", result.profit_factor)
        trial.set_user_attr("final_equity", result.final_equity)

        value = getattr(result, objective_metric)
        if np.isnan(value) or np.isinf(value):
            value = -1e9 if direction == "maximize" else 1e9

        # Penalize zero-trade runs
        if result.total_trades == 0:
            value = -1e9 if direction == "maximize" else 1e9

        trial.report(value, step=0)

        if trial.number >= n_prune_warmup_steps:
            completed = [
                t for t in trial.study.trials
                if t.state == optuna.trial.TrialState.COMPLETE
            ]
            if len(completed) >= n_prune_warmup_steps:
                values = sorted(
                    [t.value for t in completed if t.value is not None],
                    reverse=(direction == "maximize"),
                )
                cutoff_idx = int(len(values) * prune_percentile / 100)
                if cutoff_idx > 0 and value <= values[cutoff_idx]:
                    raise optuna.TrialPruned()

        return float(value)

    sampler = optuna.samplers.TPESampler(
        seed=seed, n_startup_trials=n_startup_trials,
    )
    pruner = optuna.pruners.MedianPruner(
        n_startup_trials=n_prune_warmup_steps,
        n_warmup_steps=0,
        interval_steps=1,
    )

    study = optuna.create_study(
        study_name=study_name, storage=storage,
        direction=direction, sampler=sampler, pruner=pruner,
        load_if_exists=True,
    )

    logger.info(
        f"Optuna: {n_trials} trials, metric={objective_metric}, "
        f"direction={direction}, prune_pct={prune_percentile}%"
    )
    study.optimize(objective, n_trials=n_trials, n_jobs=n_jobs,
                   catch=(Exception,))

    # ── Re-run best ──────────────────────────────────────────────
    best_params_dict = study.best_params
    best_model = model_class(
        params=ModelParams(**best_params_dict),
        execution_tf=execution_tf,
        bias_tfs=bias_tfs,
    )
    best_engine = SimulationEngine(
        model=best_model, initial_capital=initial_capital, fee=fee,
        allow_shorts=allow_shorts,
    )
    best_result = best_engine.run(data_files, execution_tf, data_start, data_end)

    # ── Trials dataframe ─────────────────────────────────────────
    trials_data = []
    for t in study.trials:
        if t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED):
            trials_data.append({
                "number": t.number,
                "value": t.value,
                "state": str(t.state),
                **{k: v for k, v in t.params.items()},
                **{k: v for k, v in (t.user_attrs or {}).items()},
            })
    trials_df = pd.DataFrame(trials_data)

    logger.info(
        f"Best {objective_metric}: {study.best_value:.4f} | "
        f"Params: {best_params_dict}"
    )

    return {
        "best_params": best_params_dict,
        "best_value": study.best_value,
        "best_result": best_result,
        "study": study,
        "trials_df": trials_df,
    }
