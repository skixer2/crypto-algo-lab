"""
Scalping Rules — Modular Crypto Trading Framework

Fixed modules (reusable across any model/optimizer):
  Module 1 — data_loader    : Fetch & cache candles from OKX (coin-agnostic, any TF)
  Module 2 — runner         : Orchestrator — dispatch to simulation (7) or live (5)
  Module 4 — graphing       : 3-panel performance charts with trade markers on all panels
  Module 5 — live_executor  : Real trade execution on OKX/Revolut (coin-agnostic)
  Module 7 — simulation     : Continuous simulation engine (close-price only)

Interchangeable modules (swap for different strategies):
  Module 3 — model          : Pure signal generator — market-structure scalping
  Module 6 — optimizer      : Optuna-based parameter optimization with pruning

Architecture:
  model = ScalpingModel(ModelParams())    # stateless signal generator
  config = RunConfig(data_file=path, model=model, exchange="simulation")
  result = run_strategy(config)           # dispatches to simulation or live
  generate_graph(result.equity_curve, "output.png")

Quick start:
    from code.data_loader import load_candles
    from code.model import ScalpingModel, ModelParams
    from code.runner import RunConfig, run_strategy
    from code.graphing import generate_graph

    _, path_5m, _ = load_candles(symbol="BTC/USDT", timeframe="5m")
    _, path_1h, _ = load_candles(symbol="BTC/USDT", timeframe="1h")
    _, path_2h, _ = load_candles(symbol="BTC/USDT", timeframe="2h")
    model = ScalpingModel(ModelParams(), execution_tf="5m", bias_tfs=["1h", "2h"])
    config = RunConfig(
        data_files={"5m": path_5m, "1h": path_1h, "2h": path_2h},
        execution_tf="5m",
        model=model, create_graphs=True, graph_output_path="output.png",
    )
    result = run_strategy(config)
    print(f"Return: {result.metadata['return_pct']:.2%} | Sharpe: {result.metadata['sharpe']:.2f}")
"""

from .data_loader import DataLoader, load_candles
from .model import ScalpingModel, ModelParams, Action, SwingPoint
from .runner import RunConfig, RunResult, run_strategy, quick_sim
from .simulation import SimulationEngine, SimulationResult, Trade, run_simulation
from .graphing import generate_graph
from .live_executor import LiveExecutor, OrderResult
from .optimizer import (
    run_optuna_optimization,
    suggest_params,
    DEFAULT_PARAM_SPACE,
)

__all__ = [
    # Module 1 — Data
    "DataLoader", "load_candles",
    # Module 2 — Runner
    "RunConfig", "RunResult", "run_strategy", "quick_sim",
    # Module 3 — Model
    "ScalpingModel", "ModelParams", "Action", "SwingPoint",
    # Module 4 — Graphing
    "generate_graph",
    # Module 5 — Live
    "LiveExecutor", "OrderResult",
    # Module 6 — Optimizer
    "run_optuna_optimization", "suggest_params", "DEFAULT_PARAM_SPACE",
    # Module 7 — Simulation
    "SimulationEngine", "SimulationResult", "Trade", "run_simulation",
]
