# Crypto Algorithm Framework — Briefing for AI Assistants

> Self-contained brief. You (the AI) are asked to help design, review, or tune a
> trading **model** for this existing framework. The engine is fixed; only the
> model slot changes. Read everything before proposing code.

## 1. Context

- Private project (`skixer2/crypto-algo-lab`). Live trading happens on small real
  accounts (OKX futures, Revolut spot). Goal: maximize equity while respecting
  the capital-preservation rules in §10.
- The framework was battle-tested since 2026-05. Two reference models exist
  (market-structure scalper, CNN pattern model). A **new algorithmic model**
  (rule-based, human-specified) is being added; it will be periodically tuned
  on backtest results with AI assistance.

## 2. Architecture — 7 modules, two categories

**Fixed (never fork, never modify without walk-forward A/B):**

| Module | File | Role |
|---|---|---|
| 1 — Data | `data_loader.py` | `load_candles(symbol, timeframe, ...)` — fetches OKX OHLCV via ccxt (public, no key) + local CSV cache |
| 2 — Runner | `runner.py` | `RunConfig` + `run_strategy(config) -> RunResult`; dispatches to simulation or live |
| 4 — Graphs | `graphing.py` | `generate_graph(result.equity_curve, path)` — 3-panel charts with trade markers |
| 5 — Live exec | `live_executor.py` | `LiveExecutor` — real orders via ccxt (OKX); creds from env vars |
| 7 — Simulation | `simulation.py` | `SimulationEngine` — event loop over candles, fills, fees, equity bookkeeping |

**Interchangeable (this is where work happens):**

| Module | File | Role |
|---|---|---|
| 3 — Model | `model.py` (+ `models/`) | Pure signal generator. Reference: `ScalpingModel`. Also `model_cnn`, `template_matcher`, `wavelet_utils` |
| 6 — Optimizer | `optimizer.py` | Optuna-based: `run_optuna_optimization`, `suggest_params`, `DEFAULT_PARAM_SPACE` |

## 3. How a run works

```python
from framework.data_loader import load_candles
from framework.runner import RunConfig, run_strategy
from framework.graphing import generate_graph

_, path_15m, _ = load_candles(symbol="ETH/USDT", timeframe="15m")
_, path_1h,  _ = load_candles(symbol="ETH/USDT", timeframe="1h")

model = MyModel(MyParams(), execution_tf="15m", bias_tfs=["1h"])
config = RunConfig(
    data_files={"15m": path_15m, "1h": path_1h},   # tf label -> CSV path
    execution_tf="15m",          # drives the tick loop (must be a data_files key)
    model=model,
    initial_capital=10_000.0,
    fee=0.0008,                  # 0.08% per side
    exchange="simulation",       # "simulation" | "okx" | ...
    allow_shorts=True,
    create_graphs=True, graph_output_path="run.png",
    data_start="2026-06-01", data_end="2026-09-01",
)
result = run_strategy(config)
print(result.metadata)           # return_pct, sharpe, max_drawdown_pct, ...
```

`RunResult` wraps a `SimulationResult`: `equity_curve` (DataFrame), `trades`,
`final_equity`, `total_return_pct`, `max_drawdown_pct`, `sharpe_ratio`,
`total_trades`, `win_rate`, `avg_win_pct`, `avg_loss_pct`, `profit_factor`.

## 4. The model contract — what a new algorithm implements

```python
Action = Literal["long", "short", "flat"]   # from framework/model.py

class MyModel:
    def __init__(self, params, execution_tf: str, bias_tfs: list[str]):
        # params: a frozen @dataclass of ALL tunable hyperparameters
        # execution_tf: timeframe whose candles drive entries/SL/TP
        # bias_tfs: higher timeframes for trend/regime context (optional)
    def update(self, candle_row, tf: str) -> None:
        # called for EVERY closed candle of EVERY timeframe in data_files.
        # candle_row: dict with ts/open/high/low/close/volume.
        # This is the ONLY place to mutate internal state.
    def predict(self, allow_shorts: bool = True) -> tuple[Action, float, dict]:
        # called after each execution_tf candle.
        # returns (action, position_size_pct, indicators)
        #   position_size_pct: fraction of equity, 0..max (1.0 = all-in)
        #   indicators: {"entry_price", "stop_loss", "take_profit", ...}
        # "hold"-style behaviour = return current/flat action; do NOT block.
```

Rules for a model implementation:

- **Deterministic**: same input state → same signal. No hidden global state;
  anything persistent goes through explicit state fields updated in `update()`.
- **All tunables in one params dataclass** — the optimizer tunes these; name
  them clearly and give sane defaults with documented ranges.
- Statelessness across runs: a fresh instance must reproduce a backtest.
- Do not import engine internals, do not place orders — signal only.
- Multi-timeframe pattern: use `bias_tfs` for direction/regime filters,
  `execution_tf` for triggers. Reference: `ScalpingModel.predict()`.

## 5. Simulation semantics (know what your signals mean)

- **Close-price fills**: decisions execute at the close of the candle that
  triggered them. No intrabar fills (SL/TP are evaluated on subsequent closes).
- Cash + position bookkeeping: long = buy then sell; short supported when
  `allow_shorts=True`; SL/TP checked every tick against the model-provided
  levels; fee applied per side (`fee=0.0008` default ≈ taker).
- Equity is continuous and marked-to-market every tick; it never resets.
- Date filtering via `data_start`/`data_end` — used to build clean
  train/valid/test windows (walk-forward: 7d train / 3d valid / 3d test,
  slide 3d, no leakage; optimizer sees train only, selection on valid,
  report on test).

## 6. Data access

- `load_candles(symbol="ETH/USDT", timeframe="15m")` → cached CSV path (public
  OKX REST via ccxt, rate-limited, incremental updates). UTC timestamps.
- Backtests should always run from cache; force refresh only deliberately.
- For walk-forward you need enough history (e.g. 60+ days of 15m).

## 7. Optimization

- `run_optuna_optimization(...)`: Optuna TPE, seed 42, multivariate, pruning.
- Parameter space is declared from the model's params dataclass
  (`suggest_params` / `DEFAULT_PARAM_SPACE` pattern).
- ~200-400 trials default; score = validation metrics, never test.
- The AI tuning loop wraps this: optimize → report → human/AI review →
  challenger backtest → promotion gates (§10).

## 8. Live execution (context only — models never touch this)

- `LiveExecutor(exchange="okx", ...)` reads API creds from env vars, uses ccxt.
- ⚠️ Known traps: ccxt swap `amount` is in CONTRACTS (contractSize), not base
  currency — a past bug traded at 4% of intended size; and its "revolut"
  branch is dead code (ccxt lacks Revolut X — a custom client exists instead:
  `lib/revolut_client_new.py`).
- Paper-first policy: exchange="simulation" until a strategy passes the gates
  on out-of-sample windows, then small live size.

## 9. Non-negotiable rules (learned the hard way)

1. Continuous equity across windows — never reset to initial capital.
2. Mark-to-market during holds; fee on every side.
3. Verify reported equity with independent math before believing results.
4. One unified runner with variant flags — no copy-pasted per-strategy forks.
5. Walk-forward with no lookahead: train → validate → test, sliding windows.
6. Graphs generated immediately with every result (equity vs B&H anchored,
   window returns, volume).
7. Compare against **buy & hold** always — a strategy that loses to B&H in its
   own test window is not deployable.

## 10. Promotion gates — THE CHARTER (project owner, 2026-09-30; supersedes 2026-09-20)

MISSION: beat buy & hold SIGNIFICANTLY over the MEDIUM TERM — not every day,
not every window. The edge equation: medium-term excess = (what you keep from
uptrends) − (what you lose in drawdowns). Win by losing less when the market
falls, while riding enough of every rise.

Hard rules per OOS window (ASYMMETRIC, compounding-corrected 2026-10-01 —
a strategy absorbing 50% of drops while capturing 30% of rallies compounds
AGAINST you: −10% then +9% = −1.9% while B&H makes +4%):
1. DOWN-SHIELD: bench ≤ 0 → absorb at most 20% of the drop
   (strategy ≥ 0.2 × bench). Cut the market's losses by 80%+.
2. UPTREND PARTICIPATION: 0 < bench < +15% → capture ≥ 60% of the move.
   The asymmetry (−20% downside / +60% upside) is what makes compounding
   work for you: −4% then +18% = +13.3% while B&H makes +4%.
3. EXTREME MELT-UPS: bench ≥ +15% → participation only (strategy > 0).
   Vertical weeks reward holders, not traders. Don't chase, don't fear.
4. MEDIUM-TERM EDGE (aggregate): OOS mean excess ≥ +2%, consistency t > 0,
   ADAPTIVE ACTIVITY GATE (JP 2026-10-02, delegated): total entries ≥ 8 AND
   mean ≥ 2 entries per active window AND ≥ 25% of windows active — replaces
   the fixed 50-bar, which assumed scalping-like activity; a regime-gated
   system legitimately trades selectively. Parameter-noise stability gate,
   test window obeys its bucket rule, and edge over the incumbent champion
   when one exists.

OWNER'S MISSION STATEMENT (JP, 2026-10-02): the only things that matter are
highest return over ~one year, not losing money, and beating the market.
Entry bars and gate knobs are instruments, not goals — tune them if they
obstruct the mission without adding protection.

Design implication for formulas: ASYMMETRY beats symmetry — fast trend
entries with tight risk. Flat-in-drops + partial-long-in-rallies passes;
beats-rallies-but-bleeds-in-drops fails; trades-everything-captures-nothing
fails. Reports list per-window bucket verdicts: read them as your fix list.

## 11. What you may be asked to do

- Design/implement a model class per §4 from a written algorithm description.
- Propose parameter ranges + Optuna space for a model.
- Review backtest results (equity curve, trade list) and diagnose weaknesses
  (overtrading, regime dependence, fee drag, drawdown clustering).
- Suggest model modifications as diffs, with an explicit hypothesis of WHY the
  change improves OOS performance — every change gets re-validated per §10.

*Repo: github.com/skixer2/crypto-algo-lab (private). Secrets never committed.*
