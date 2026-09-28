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
- Imports: `pandas` / `numpy` only. No I/O, no network, no heavy work at
  import time. Deterministic: same df -> same output.
- NaN handling is done by the wrapper (fillna(0)); early-window NaNs are fine.

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
