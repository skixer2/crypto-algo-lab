# algo_lab — algorithm framework

Reusable engine + pluggable algorithms. The brain changes; the body doesn't.

## Wiring

```
main.py ── backtest │ tune │ paper │ live │ plot
   ├── data/         fetcher + cache      (lib/okx_candle_fetcher.py)
   ├── indicators/   shared features
   ├── model/        base.py contract + algos/  ← THE SWAPPABLE PART
   ├── backtest/     engine + metrics + walk-forward (Optuna TPE, 7/3/3, seed 42)
   ├── execution/    paper.py + okx_exec.py     (lifted from live bot)
   ├── graphs/       3-panel Plotly standard    (equity vs B&H anchored, window returns, volume)
   ├── tuner/        champion/challenger AI loop
   └── runs/         results JSONs: (algo hash + params hash + data range)
```

## Promotion gates (a challenger is promoted ONLY if all pass)

1. **Edge**: OOS return > champion OOS return (MDD not worse by >2pts)
2. **Market beat**: OOS return > ETH/BTC buy&hold on the same window
3. **Capital floor** (JP, 2026-09-20): in OOS windows where BOTH champion and
   B&H lose money, the challenger must return >= 0

HODL is a permanent benchmark line on every graph and every report.

## Rules inherited from crypto-master

- Continuous equity across windows (never reset to 1.0); MTM during holds
- Exact fee formula: `eq * (1 + ret) * (1 - FEE)` on exit
- Verify equity tracker with independent math before accepting results
- One unified runner with `--variant` — never copy-paste model variants
- Graphs generated immediately, never delayed
- Results committed here before any external teardown
