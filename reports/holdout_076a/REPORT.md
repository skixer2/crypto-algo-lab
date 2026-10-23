# alpha_076a ETH HOLDOUT READOUT — the irreversible read

Date: 2026-10-23 (run 15:05–15:08 UTC). Operator-directed, pre-registered
(RESEARCH_LEDGER 15:0x, JP plan of record 13:13 UTC; both per-asset portability
legs no-pass → holdout path fires). One canonical run, one readout. **No
interpretation beyond the bar.**

## Definition (pre-registered, quoted from ledger)

Holdout = post-GRID segment of the ETH cache: **2026-07-01 → 2026-09-28**.
Windows per stats_canonical machinery, [s, e) half-open:

- **2026-07 (partial):** ruler `JULY` tuple [2026-07-01, 2026-07-28) — the
  28-day-partial caveat stands: defined in the blend era, never before quoted
  for the 076 family.
- **2026-08:** [2026-08-01, 2026-09-01) — full month.
- **2026-09 (partial):** [2026-09-01, 2026-09-28) — to cache end; final cache
  bar 2026-09-28 00:00 excluded by the ruler's `< e` convention.

The 63-month GRID (2021-04..2026-06) is the exam window — **not re-graded, not
touched, nothing adjusted based on it.**

## Pre-registered bar

**PASS = holdout mean excess > 0 AND worst holdout month >= −40** (same floor
logic as Entry Exam v3.2 floor 2: worst ABSOLUTE strat month, not excess).
PASS/FAIL per item below. No tuning, no variants, no re-runs.

## Validation gate (ran FIRST)

Feefree full-curve grade of the extended run (END → cache end 2026-09-28) vs
manifest production grade — **PASS, exact on all four numbers**:

| source | mean exc | t | DD | worst abs |
|---|---|---|---|---|
| manifest `grade_fee_free` | +2.89 | 1.96 | −46.2 | −18.47 |
| this run (feefree) | +2.89 | 1.96 | −46.2 | −18.47 |

Supporting: pre-seal position agreement vs the stored portability curve
(`reports/portability_076a/curves/076a_ETH_pos.csv.gz`) = **100.0%**;
July-partial −9.98 identical to the portability feefree row. Extending the run
end did not perturb history (engine causal; fund_pct built on the full cache,
trailing 30-day rank).
*(Span note: gate-line time-in reads 54.0% here vs the portability row's 53.0%
— grade's time-in covers the whole pos series; this curve includes the
post-seal tail, portability's ended at the seal. The four gate numbers,
which read GRID+July windows only, are identical.)*

## Run (frozen, verbatim)

Formula md5 **137ce302a6c4**; params == manifest (channel 192 / mp96, ATR96
×1.0 rails 50/50 — effectively off, gate pctl 0.7 formula-mode, warmup CLOSED,
long-only). Engine path = `tools/portability_076a.py` **imported verbatim**
(`engine_run`, funding plumbing, `netting_on_curve`); only delta: END extended
to cache end. Funding: gate = binance settled proxy (`build_fund_pct`), cost =
binance+bybit elementwise avg (ETH production convention); fee 0.0008 netted on
|Δpos|; funding charged at 00/08/16 bars. Headline book = **netfund**;
feefree/netted disclosed. Ruler = stats_canonical machinery on the holdout
windows; bench = same-asset buy-hold close.

**Seal discipline:** the engine path enforces `tuner/holdout.py`
SEAL_DATE 2026-07-28; this readout is the final-holdout verification run that
seal was built for. Bypass per its own documented one-shot protocol:
`tuner/.holdout_final_run` created 15:07:33Z → `final_run=True` → deleted
15:07:53Z (guard re-arms: flag checked on disk). Flag absent after run.

Ops note: engine executed twice (15:0x and 15:07), frozen config both times —
first run crashed in the JSON-reporting step (numpy scalar in the gate-check
dict), after the full readout had printed. Rerun is deterministic; the
validation gate re-verified bit-exact reproduction inside the second run
(divergence would have aborted). No measurement arithmetic changed between
runs; no degree of freedom existed.

## THE READOUT (headline: netfund)

| window | strat | bench | excess |
|---|---|---|---|
| 2026-07 (partial, JULY tuple) | +9.24% | +20.22% | **−10.98%** |
| 2026-08 | +21.52% | +32.32% | **−10.80%** |
| 2026-09 (to cache end) | −1.13% | +8.75% | **−9.88%** |

| metric | value | bar | verdict |
|---|---|---|---|
| holdout mean excess | **−10.55%/mo** | > 0 | **FAIL** |
| worst holdout month (abs, strat) | **−1.13%** | ≥ −40 | **PASS** |
| worst / best excess | −10.98% / −9.88% | — | — |
| DD within holdout | −13.1% (bench −9.7%) | — | — |
| time-in (holdout) | 68.6% | — | — |
| latch entries / exits (holdout) | 11 / 11 (position carried in long at window start) | — | — |
| gate states (holdout bars) | open 61.1% / closed 38.9% / NaN 0.0% (fund_pct mean 0.564) | — | — |

Activity sanity: the book traded actively through the holdout (68.6% invested,
11 round trips, gate open 61% of bars) — this is not a lucky flat line; the
negative excess was earned while participating in a strong bench tape.

Disclosed books (context only, not graded): feefree mean excess −9.63%/mo,
worst abs −0.38%; netted-fees-only mean −10.25%/mo, worst abs −0.93%.

## BAR VERDICT

| item | result |
|---|---|
| holdout mean excess > 0 | **FAIL** (−10.55%/mo) |
| worst holdout month ≥ −40 | PASS (−1.13%) |
| **HOLDOUT (both must pass)** | **FAIL** |

No interpretation beyond the bar. Artifacts: `results.json` (incl. raw
fractions, seal log, gate detail), `curves/` (feefree / netfund / netted / pos,
full span 2021-01-01 → 2026-09-28), `run.log`, runner `tools/holdout_076a.py`.
