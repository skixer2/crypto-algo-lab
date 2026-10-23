# AGENT CONTRACT — Operational limits for every proposing agent (DS, auto-loop, JEV-derived, human)

*Binding from 2026-10-23 (JP directive after the BTC-gate four-number incident:
+4.18 / +3.16 / +2.41 / +3.05 for one idea — pure implementation-convention sprawl).
Included by reference in EVERY agent brief. Numbers produced outside this contract
are discarded unread.*

## The one law

**You propose. The infrastructure disposes.** Your deliverable is a mechanism story
and a declarative spec — never a performance number. The canonical engine runs it;
`tools/stats_canonical.py` grades it; THAT number is the only number that exists.
If you implement anything, you implement the spec against the canonical interface —
you do not build measurement machinery.

## Fixed conventions (not yours to choose — ever)

| Dimension | The ONE way |
|---|---|
| Data | `framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv` (primary); `okx_BTC_USDT_15m_20210101_20260928.csv` (conditioning), reindex-ffill to ETH index; named OI/funding caches only. No external fetch, no other venues, no resampling except canonical patterns. |
| Engine | Formula file at `models/alpha_formulas/alpha_XXX.py` (076a pattern); conditioning columns ONLY via the injection pattern (`fund_pct`, `btc_mom`) in `models/wq_alpha_fast.py` / `wq_alpha_miner.py`. Decide @ close, fill @ next open, 2× intrabar rails. |
| Costs | Fee 0.0008 netted on |Δpos|; funding averaged at 8h boundaries. No other cost model. |
| Warmup | CLOSED (no trading during indicator warmup). |
| Ruler | `tools/stats_canonical.py` `grade()` — `mean_excess_pct_mo`, `t`, `continuous_dd_pct`, `worst_absolute_month_pct`. Quote nothing else as a headline. |
| Reporting | One number per candidate, from the ruler, verbatim. No convention variants, no best-of-N, no "under my assumptions." |

## Proposal format (the idea card)

1. **Mechanism story** — why should this extract money? (falsifiable, ≤10 lines)
2. **Exact declarative spec** — which bars, which condition, applied WHERE in the
   state machine (entry/exit/sizing), warmup, parent alpha if a variant.
3. **Params** — suggested values + any grid, declared BEFORE any run.
4. Optional: code implementing the canonical interface. No engine, no grader, no plots of PnL.

For variants of an existing alpha: declare the parent and state what the conditioning
changes; the exam compares you to the parent, and the parent wins ties (simplicity law).

## Forbidden (instant discard)

- Any own backtest engine, cost model, data source, or grading arithmetic.
- Quoting any performance number not printed by `stats_canonical`.
- Choosing conventions after seeing results; submitting the max of several tries.
- Re-proposing a failure-ledger entry without a NEW mechanism story.
- Touching `tools/stats_canonical.py`, the data cache, or another agent's artifacts.

## If you believe a convention is wrong

Argue it BEFORE measuring: mechanism argument → pre-registration → one canonical
run → that number counts, whatever it is. Discovering your favorite convention by
which one won is the crime this contract exists to make impossible.

## Why this is in your interest

Compliance makes your verification cost O(1): one canonical run, believed instantly.
Non-compliance makes your work worthless regardless of quality — the 2026-10-23
BTC-gate idea was real (direction survived every implementation), and still died a
full day of forensic time because its magnitude was convention-dependent.
