"""
Module 2 — Strategy Runner / Orchestrator (FIXED)

Takes trading strategy parameters and dispatches execution to either
Module 7 (simulation) or Module 5 (live_executor), depending on the
configured exchange.

Fully timeframe-agnostic: data_files is a dict of tf_label → CSV path.

Saves returned data and — when a graph is requested — delegates to
Module 4 (graphing) with:
  - positions (base + quote)
  - total equity
  - running PnL

Never uses hardcoded crypto symbols or candle periods.
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class RunConfig:
    """All parameters for a trading run — timeframe-agnostic."""
    # Data — dict mapping timeframe label → CSV path
    # e.g. {"5m": "btc_5m.csv", "1h": "btc_1h.csv", "2h": "btc_2h.csv"}
    data_files: Dict[str, str] = field(default_factory=dict)

    # Which timeframe drives the tick loop (must be a key in data_files)
    execution_tf: str = "5m"

    # Model
    model: Any = None                                 # Module 3 instance

    # Trading parameters
    initial_capital: float = 10000.0
    fee: float = 0.0008
    exchange: str = "simulation"                      # "simulation" or exchange name
    allow_shorts: bool = False

    # Graphing
    create_graphs: bool = False
    graph_output_path: Optional[str] = None
    graph_title: Optional[str] = None

    # Date filters
    data_start: Optional[str] = None
    data_end: Optional[str] = None

    # Live trading
    leverage: float = 1.0
    dry_run: bool = False
    symbol: Optional[str] = None                      # required for live trading


@dataclass
class RunResult:
    """Unified result regardless of simulation or live execution."""
    success: bool
    execution_mode: str                               # "simulation" | "live" | "live_dry_run"
    equity_curve: Any = None                          # SimulationResult or live P&L log
    final_equity: Optional[float] = None
    initial_capital: float = 0.0
    graph_path: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


def run_strategy(config: RunConfig) -> RunResult:
    """
    Execute a trading strategy — simulation or live.

    Dispatches to:
      - Module 7 (SimulationEngine) when exchange="simulation"
      - Module 5 (LiveExecutor) when exchange is a real exchange name

    Args:
        config: RunConfig with data_files dict and execution_tf

    Returns:
        RunResult with equity data and optional graph path
    """
    from .simulation import SimulationEngine

    # ── Validate ──────────────────────────────────────────────────
    if config.model is None:
        return RunResult(
            success=False, execution_mode="error",
            error="No model provided in RunConfig",
        )
    if not config.data_files:
        return RunResult(
            success=False, execution_mode="error",
            error="No data_files provided in RunConfig",
        )
    if config.execution_tf not in config.data_files:
        return RunResult(
            success=False, execution_mode="error",
            error=f"execution_tf '{config.execution_tf}' not in data_files keys: "
                  f"{list(config.data_files.keys())}",
        )

    if config.exchange == "simulation":
        return _run_simulation(config)

    # ── Live trading ──────────────────────────────────────────────
    if config.symbol is None:
        return RunResult(
            success=False, execution_mode="error",
            error="symbol is required for live trading",
        )

    from .live_executor import LiveExecutor

    executor = LiveExecutor(
        exchange=config.exchange,
        leverage=config.leverage,
        allow_shorts=config.allow_shorts,
        dry_run=config.dry_run,
    )

    result = executor.execute(
        action="long",  # placeholder — real loop calls model.predict() per candle
        position_pct=1.0,
        symbol=config.symbol,
    )

    return RunResult(
        success=result.success,
        execution_mode="live_dry_run" if config.dry_run else "live",
        initial_capital=config.initial_capital,
        final_equity=None,  # live P&L tracked externally
        metadata={"order": result},
    )


def _run_simulation(config: RunConfig) -> RunResult:
    """Run via Module 7 — continuous simulation, close-only prices."""
    from .simulation import SimulationEngine

    engine = SimulationEngine(
        model=config.model,
        initial_capital=config.initial_capital,
        fee=config.fee,
        exchange="simulation",
        create_graphs=config.create_graphs,
        allow_shorts=config.allow_shorts,
    )

    result = engine.run(
        data_files=config.data_files,
        execution_tf=config.execution_tf,
        data_start=config.data_start,
        data_end=config.data_end,
    )

    graph_path = None
    if config.create_graphs:
        from .graphing import generate_graph
        out = config.graph_output_path or "simulation_output.png"
        title = config.graph_title or f"Simulation — {config.execution_tf}"
        graph_path = generate_graph(result, out, title=title)

    return RunResult(
        success=True,
        execution_mode="simulation",
        equity_curve=result,
        final_equity=result.final_equity,
        initial_capital=config.initial_capital,
        graph_path=graph_path,
        metadata={
            "return_pct": result.total_return_pct,
            "sharpe": result.sharpe_ratio,
            "max_dd": result.max_drawdown_pct,
            "trades": result.total_trades,
            "win_rate": result.win_rate,
        },
    )


# ─── Convenience ─────────────────────────────────────────────────────

def quick_sim(
    model,
    data_files: Dict[str, str],
    execution_tf: str = "5m",
    initial_capital: float = 10000.0,
    fee: float = 0.0008,
    graph_output: Optional[str] = None,
    allow_shorts: bool = False,
) -> RunResult:
    """
    One-liner for a quick simulation run.

    Args:
        model: ScalpingModel instance
        data_files: {"5m": "btc_5m.csv", "1h": "btc_1h.csv", ...}
        execution_tf: which TF drives the tick loop
        initial_capital, fee: trading params
        graph_output: if set, saves graph to this path
        allow_shorts: enable short positions
    """
    config = RunConfig(
        data_files=data_files,
        execution_tf=execution_tf,
        model=model,
        initial_capital=initial_capital,
        fee=fee,
        create_graphs=graph_output is not None,
        graph_output_path=graph_output,
        allow_shorts=allow_shorts,
    )
    return run_strategy(config)
