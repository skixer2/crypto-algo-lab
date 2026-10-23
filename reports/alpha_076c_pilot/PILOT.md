# alpha_076c PRE-REGISTERED PILOT — RESULT: FAIL → KILL (static A stays the product)

Run 2026-10-23 (pilot v2 subagent), frozen spec: `reports/router_nn_ideas_20261022/REPORT.md §3`
(frozen 2026-10-22, before running). All engine numbers: real engine (fast path), fee=0.0 pool
convention, `allow_shorts=False`, span 2021-01-01→2026-07-28, graded by `tools/stats_canonical`
(63-window grid, July-26 disclosed separately). Net-of-fees = netted 0.0008×|Δpos| layer.
Configs: entry-gated state machine = alpha_076a + BTC-30d-momentum entry gate (30d/1.00 plateau
centroid; 14d/0.98 grid-max named-and-forbidden), rides continue to A's own exits, warmup CLOSED,
state shifted 1 bar, BTC 15m close ratio btc/btc.shift(96·30) reindex-ffill, funding gate frozen
identical to A (binance pctl 0.7, formula mode).

**Harness validation: alpha_076a re-run through the pilot path reproduces the stored production
curve exactly — position series identical, final equity delta 5.7e-08 (126415.52922994…).**

## 1. HEADLINE (engine, same path, both books)

| book | fee-free net %/mo | t | DD % | worst abs % | time-in | fee-netted net %/mo | t | DD % | fee %/mo | soft v3.2 (θ=0.598, σ=0.22) |
|---|---|---|---|---|---|---|---|---|---|---|
| A (alpha_076a) | +2.89 | 1.96 | −46.2 | −18.47 | 53% | +2.47 | 1.67 | −47.1 | 0.40 | 2.699 |
| **076c (A×BTC-gate)** | **+3.05** | **1.47** | **−34.2** | **−16.03** | **34%** | **+2.80** | **1.35** | **−34.8** | **0.24** | **2.663** |

July-26 partial (disclosed, ungraded): A +10.63, 076c +14.99 excess.

## 2. PASS BAR (frozen) — item by item

| item | bar | 076c measured | verdict |
|---|---|---|---|
| net (fee-netted) | ≥ +2.17/mo | **+2.80** | **PASS** |
| DD | ≤ 40 | **−34.8** (fee-free −34.2) | **PASS** |
| fee | ≤ 1.5/mo | **0.24** | **PASS** |
| worst abs (spec §3) | ≥ −40 | **−16.2** | **PASS** |
| soft-score | ≥ A + 0.3 | 2.663 vs A 2.699 (**Δ = −0.04**) | **FAIL** |
| jitter clean | sign-stable + halves ≥ 0 | sign-stable ✓ (all 6 nets +0.37…+3.02); halves ✗ (34.5d/1.1 first-half **−0.29**); spec §3 stricter bar "net ≥ +3.0" also ✗ (max variant 3.02) | **FAIL** |
| shift-2 retention | ≥ 0.25 | **0.515** (engine; bar-replay 0.667 ≈ pre-measured 64%) | **PASS** |

**KILL criterion (spec §3): "if the anchored exam score ≤ A's, or jitter flips sign → gate dies,
static A stays the product, router question closed at this pool size." Anchored exam: 076c 2.663 ≤
A 2.699 → KILL TRIGGERED (on the soft-score delta, independent of the jitter-halves miss).**

Net-of-fees **+ funding** (disclosure; per-bar settled funding charged on position): 076c +1.76…+2.06
vs A +1.44…+1.72 across five conventions (fitted-const anchored on A=+2.06, const-binance,
const-avgvenue, realized-binance, realized-avgvenue) — 076c stays above A on every convention
(+0.28…+0.56), the ranking is convention-robust; the frozen bars above are judged on the fee-netted
convention in which they were written.

## 3. Spec-required slices, verbatim (engine fee-free window excess vs bench)

- 2021-04 mania-whipsaw: A −14.1, **076c −38.5** (bench +43.9) — the gate bleeds exactly where disclosed.
- 2021-05: A +31.6, 076c +29.6.
- 2022-06 crash month: A +26.2, **076c +44.7** (bench −44.7) — gate's best protection month.
- 2022-07 counter-slice: A −12.9, **076c −35.8** (bench +59.1) — gate blocked A's best month, as pre-disclosed.
- Year sums of excess: 2021 A −207.5 / C −264.0; 2022 +62.7 / +92.4; 2023 −29.6 / −43.8; 2024 +50.9 / +48.0; 2025 +44.6 / +94.4; 2026(7mo) +42.8 / +47.2.

## 4. 076c jitter battery (engine, fee-netted; window ±15% × thr {0.90,1.00,1.10})

| window | thr 0.90 | thr 1.00 | thr 1.10 |
|---|---|---|---|
| 25.5d | +2.57 t1.56 (halves 2.81/2.35, DD −42.0) | +3.02 t1.53 (2.15/3.85, DD −33.9) | +1.05 t0.49 (0.35/1.72, DD −33.2) |
| 34.5d | +2.45 t1.24 (2.01/2.88, DD −35.1) | +2.06 t0.95 (0.49/3.58, DD −41.6) | **+0.37 t0.16 (−0.29/1.00, DD −29.6)** |

Sign never flips (all positive) ✓; but the 34.5d/1.10 corner goes first-half-negative and the
surface degrades monotonically toward slow-window/loose-threshold — the effect thins at the jitter
edges rather than plateauing. Under the spec §3 jitter law ("sign never flips, net stays ≥ +3.0")
the battery fails outright (5 of 6 cells < 3.0).

## 5. alpha_076a dedicated production jitter (JP request; engine, fee-netted, baseline +2.47)

| perturbation | net %/mo | t | halves | DD |
|---|---|---|---|---|
| ATR mult ×0.85 | +2.65 | 1.62 | 2.97/2.33 | −44.7 |
| ATR mult ×1.15 | +3.40 | 2.42 | 3.47/3.33 | −49.6 |
| channel N 163 (mp 81) | +3.23 | 1.95 | 3.29/3.17 | −49.5 |
| channel N 221 (mp 110) | +1.63 | 1.14 | 1.37/1.89 | −49.9 |
| funding pctl 0.50 | +2.15 | 1.25 | 2.76/1.55 | −43.7 |
| funding pctl 0.80 | +1.74 | 1.18 | 1.63/1.84 | −47.8 |

**All six sign-stable positive (range +1.63…+3.40) — A's production config is not a tuning
artifact; it is interior to a positive neighborhood.** Nearest edges: channel 221 (−0.84 vs
baseline) and pctl 0.80 (−0.73); ATR/channel loosening never goes negative.

## 6. Cross-check vs the ledger bar reference (+3.16 t1.53, entry-gated state machine, fees+avg-funding)

**Not reproducible — disclosed.** The ledger's 2026-10-22 ad-hoc reference could not be rebuilt
from its record: faithful entry-gated state-machine replays of A (exact channel arithmetic,
shift-1 fill timing validated vs stored pos to 17 bars of 195k, funding gate kept, warmup
closed AND open, 15m AND 1h momentum, windows 7–90d, five funding conventions incl. a
fitted-constant anchored on the ledger's own A=+2.06) land the gated book at **+2.4…+2.9 net,
DD −33…−45, worst −16…−26** — none reproduces its −40.5 worst-month / −43.4 DD signature
(which would require the gate to have deleted A's *positive* 2022 rides; every faithful 30d
reconstruction keeps them). Direction agrees (entry-gate > A same-path: +2.57 vs +2.07 fitted /
+2.49 vs +1.94 const-bin), magnitude does not (+0.4…+0.55 here vs their +1.10). The engine number
(+2.80 fee-netted / +2.04 realized-funding) is the canonical one per the frozen spec; the ledger
number is superseded as a reference anchor. A-replay QA note: my bar replay of A matches the
stored engine position except 17 bars (engine double-flip bars), n=195,265.

## 7. Verdict

Frozen spec: **FAIL on 2 of 7 items (soft-score delta, jitter), KILL criterion met → alpha_076c
dies; static A (alpha_076a) stays the product; the router question stays closed at this pool
size** (the one overlay class that ever beat the static bar failed its own pre-registered exam).
What survives for the record: A's production config is jitter-robust (new, JP-requested evidence);
the BTC-gate mechanism is directionally real and convention-robust but its risk-shape gains
(DD −47→−35, worst −18.8→−16.2, time-in 53→34%) come with excess-quality loss (t 1.96→1.47,
first-half 2021 bleed −38.5) that the v3.2 anchored exam correctly refuses to pay +0.3 for.

## Appendix — run notes (audit trail)

- Formula on disk `models/alpha_formulas/alpha_076c.py` (frozen pilot build; BTC_MOM_THRESHOLD
  constant style) + minimal column-injection seam in `models/wq_alpha_fast.py` (ctx.btc_mom slice)
  and `models/wq_alpha_miner.py` (use_btc_mom_gate param, model.btc_mom reindex, _formula_frame).
  Write scope respected: no other repo files touched, nothing committed. Variant formulas for
  jitter live in /tmp/pilot076c/formulas/.
- An earlier pilot attempt (v1) had left artifacts in /tmp/pilot076c and its formula text differs
  stylistically from a first draft; the center/jitter/shift-2 runs above all used the on-disk
  frozen formula. A first jitter pass silently no-opped the threshold dimension (string-replace
  mismatch) — caught by identical-output QA check and re-run (fixup_076c.py); only fixup numbers
  are reported.
- Raw results: `pilot_results.json` in this folder; engine curves/positions: /tmp/pilot076c/*.pkl.
- Soft-score note: θ=0.598/σ=0.22 are the frozen r3-era calibration; under
  stats_canonical.soft_scores (allowance floor 11%/mo) an A-anchored inversion to mean-soft 0.30
  is infeasible (A pins at ≈2.70), so the frozen bar was evaluated on the same-θ/σ delta, as
  frozen. A's level (2.699) reported verbatim.
- Budget: ~15 engine sims ×~25s + bar-arithmetic section; well under 2h.
