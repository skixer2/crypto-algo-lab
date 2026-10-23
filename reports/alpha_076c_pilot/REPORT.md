# alpha_076c PRE-REGISTERED PILOT — RESULTS (2026-10-23)

**Spec:** `reports/router_nn_ideas_20261022/REPORT.md` §3 (frozen 2026-10-22) + JP pilot
notes (2026-10-23). **No commits made.** Repo scope touched: `alpha_076c.py` (new) +
`btc_mom` column-injection seam (`wq_alpha_fast.py`, `wq_alpha_miner.py`) only.
**Ruler:** `tools/stats_canonical.grade` only. 63 windows 2021-04..2026-06; July-26
partial disclosed per grade. Engine: fast path, `fee=0.0` (pool convention),
`allow_shorts=False`, 15m exec, full span 2021-01-01→2026-07-28 — the exact
alpha_076a production recipe.
**076c config (selection-free):** 30d/1.00 plateau centroid; BTC = OKX 15m close,
`btc/btc.shift(96*30)`, reindex-ffill to ETH index; gate state shifted 1 bar inside
the formula (frozen-spec causality); warmup CLOSED (NaN → gate closed); exits never
gated; funding gate block frozen identical to 076a (binance pctl 0.7, formula mode).
**Formula hashes:** alpha_076c `f70b45c06119`, alpha_076a `137ce302a6c4` (snapshot at
run time; content-asserted on every derived jitter variant).

**Pipeline validation:** engine rerun of 076a == stored production curve
`data/precompute/alpha_076a.csv.gz`: **100.0%** bar-exact position agreement. Engine
076c vs bar-arithmetic 076c (shift-aligned): **99.9933%**. Bar-arithmetic A static
**+2.09 t1.40** vs ledger-established +2.06 t1.35 → **+0.03** (cost layer reproduces;
DD −47.5 vs −50.4 disclosed below).

## (a) Canonical grade — 076c vs 076a (verbatim ruler output)

| book | net %/mo | t | DD % | worst abs % | worst win % | fee/mo | time-in | halves | July-26 |
|---|---|---|---|---|---|---|---|---|---|
| **076c fee-free** (engine) | **+3.05** | 1.47 | −34.2 | −16.03 | −47.23 | — | 34% | +2.08/+3.99 | −20.19 |
| **076c netted-fees** (0.0008·\|Δpos\|) | **+2.80** | 1.35 | −34.8 | −16.23 | −47.46 | 0.24 | 34% | +1.85/+3.72 | −20.59 |
| **076c net-of-costs** (+avg funding @8h) | **+2.37** | 1.12 | −35.3 | −16.43 | −47.98 | 0.24 | 34% | +1.39/+3.33 | −20.68 |
| 076a fee-free (engine) | +2.89 | 1.96 | −46.2 | −18.47 | −31.39 | — | 53% | +2.90/+2.87 | −9.98 |
| 076a netted-fees | +2.47 | 1.67 | −47.1 | −18.80 | −31.75 | 0.40 | 53% | +2.48/+2.47 | −10.68 |
| 076a net-of-costs | +1.95 | 1.29 | −47.5 | −18.83 | −32.70 | 0.40 | 53% | +1.87/+2.02 | −10.98 |

Concentration/neg-windows (076c netfund): conc 0.30, 25/63 negative. Best window
+44.69 (2022-07 recovery ride) and worst window −47.98 are the two violent tails the
spec's slice reporting below makes verbatim.

## (b) Jitter

### 076c — BTC window {25.5, 30, 34.5}d × thr {0.90, 1.00, 1.10} (engine runs; netfund primary)

| variant | net %/mo | t | halves | DD | sign | halves ≥ 0 |
|---|---|---|---|---|---|---|
| w25.5 thr0.90 | +2.07 | 1.23 | +2.23/+1.90 | −42.5 | ✓ | ✓ |
| w34.5 thr0.90 | +1.96 | 0.97 | +1.46/+2.44 | −35.8 | ✓ | ✓ |
| w25.5 thr1.00 | +2.59 | 1.29 | +1.67/+3.47 | −34.4 | ✓ | ✓ |
| w34.5 thr1.00 | +1.62 | 0.74 | +0.00/+3.19 | −43.0 | ✓ | ✓ (0.00 exactly) |
| w25.5 thr1.10 | +0.73 | 0.33 | **−0.004**/+1.44 | −34.4 | ✓ | ✗ (marginal) |
| w34.5 thr1.10 | **+0.06** | 0.03 | **−0.64**/+0.74 | −29.9 | ✓ | ✗ |
| center w30 thr1.00 | +2.37 | 1.12 | +1.39/+3.33 | −35.3 | ✓ | ✓ |

- Sign never flips: **PASS** (all 6 variants positive; feefree likewise all positive:
  +2.94/+2.78/+3.26/+2.31/+1.16/+0.49).
- Both halves ≥ 0 per variant: **FAIL** — thr1.10 arm (w34.5 first half −0.64; w25.5
  first half −0.004). The threshold 1.10 arm is also where net collapses toward zero.
- Frozen-spec §3 sub-criterion "net stays ≥ +3.0": **FAIL** (max variant +2.59 netfund;
  feefree max +3.26).

### alpha_076a dedicated jitter (JP request; production-engine runs, one-at-a-time, netfund)

| variant | net %/mo | t | halves | DD | sign |
|---|---|---|---|---|---|
| buf 0.85 | +2.14 | 1.29 | +2.40/+1.89 | −44.8 | ✓ |
| buf 1.15 | +2.84 | 2.00 | +2.82/+2.86 | −51.3 | ✓ |
| N 163 | +2.73 | 1.62 | +2.72/+2.73 | −50.1 | ✓ |
| N 221 | +1.09 | 0.75 | +0.77/+1.41 | −51.6 | ✓ |
| gate 0.5 | +1.69 | 0.97 | +2.26/+1.14 | −44.4 | ✓ |
| gate 0.8 | +1.18 | 0.79 | +1.01/+1.35 | −48.6 | ✓ |
| center (buf1.0/N192/gate0.7) | +1.95 | 1.29 | +1.87/+2.02 | −47.5 | ✓ |

**6/6 sign-stable, all halves positive → A jitter CLEAN.** Weakest arm N221 +1.09;
strongest buf1.15 +2.84 (center is not the sweep max — no selection concern, sweep
disclosed as-is).

## (c) Shift-2 relabel (076c)

- netfund: +2.37 t1.12 → retention **100.0%** (≥ 0.25 PASS). netted: +2.80 → 100.0%.
- Perturbation is real: 384/195,265 bars differ (0.20%) — a multi-week latch shifted
  2 bars barely changes the book.

## (d) Anchored exam v3.2 (theta 0.598, sigma 0.22 — frozen as instructed)

- sigma_m(ETH bench) = **0.22** — reproduces the frozen sigma ✓.
- Soft scores on net-of-costs books, frozen theta/sigma: **A_soft +1.69** (t_s 0.14),
  **C_soft +1.76** (t_s 0.10) → **C − A = +0.068**.
- Scale consistency: A_soft +1.69 equals the recorded r3 v3.2 score of this latch
  family ("076 gated latch: raw +2.11 → v3.2 +1.69") — the frozen constants land on
  the recorded exam scale.
- Disclosed observation: theta-by-inversion on my A netfund excesses pins at the
  0.05 lower bound (the 11pt allowance floor makes target 0.3 unreachable there);
  the frozen 0.598 was used verbatim as instructed.

## Verbatim slices (net-of-costs monthly excess %)

| month | A | 076c | delta |
|---|---|---|---|
| 2021-04 (mania whipsaw) | −20.55 | **−43.62** | −23.07 |
| 2021-05 | +28.29 | +26.83 | −1.46 |
| 2022-07 (counter-slice: gate blocks A's best month) | −14.24 | **−36.44** | −22.20 |

## Bar-arithmetic cross-check vs the 2026-10-22 ledger reference (+3.16 t1.53)

`compose_portfolio` law (decision@close → eff t+1; fee 0.0008·|Δeff|; funding
−rate·eff at 00/08/16 UTC bars, avg binance/bybit; entry-gated latch rebuild,
engine-convention fund gate):

| implementation | net %/mo | t | DD | worst abs | ledger | delta |
|---|---|---|---|---|---|---|
| A static (reference base) | **+2.09** | 1.40 | −47.5 | −18.82 | +2.06 t1.35 DD−50.4 | **+0.03** net |
| 076c entry-gated, state shift-1 (spec causality) | **+2.41** | 1.14 | −35.3 | −16.42 | +3.16 t1.53 | **−0.75** |
| 076c entry-gated, state shift-0 (sensitivity) | **+2.77** | 1.32 | −35.3 | −16.42 | +3.16 t1.53 | **−0.39** |

- **Direction reproduces** (entry-gate improves A: +0.32 shift-1 / +0.68 shift-0 vs
  the ledger's +1.10); **magnitude does not**. My reconstruction's tails are much
  milder (DD −35.3 / worst-abs −16.4 vs −43.4 / −40.5).
- Scanned convention space (all disclosed in `results/` probes): BTC series 15m vs
  1h-resample vs true-1h-shift720 (+2.08..+2.77), warmup open/closed (no effect),
  binance-vs-avg cost input (±0.01), funding-on-decision-pos (no effect), lab-90-
  settle vs engine gate series (±0.02). None reaches +3.16/−43.4. The 2026-10-22
  session's exact code was not saved; the remaining delta is unreconciled and is
  carried as the disclosed cross-check delta.

## PASS/FAIL — frozen bar (REPORT §3)

| # | item | bar | 076c value | verdict |
|---|---|---|---|---|
| 1 | net | ≥ +2.17 (static 2.47 − 0.3, netted-fees convention) | **+2.80** netted (netfund +2.37 — passes under both readings) | **PASS** |
| 2 | DD | ≤ 40 | **−34.8** netted / −35.3 netfund | **PASS** |
| 3 | fee | ≤ 1.5/mo | **0.24** | **PASS** |
| 4 | worst abs | ≥ −40 | **−16.23** | **PASS** |
| 5 | soft score | ≥ A + 0.3 | **+0.068** (1.76 vs 1.69) | **FAIL** |
| 6 | jitter | sign never flips + halves ≥ 0 per variant | sign ✓ all 6; halves ✗ (thr1.10 arm); "net ≥ +3.0" ✗ | **FAIL** |
| 7 | shift-2 retention | ≥ 0.25 | **1.00** | **PASS** |

**KILL criterion (§3) check:** anchored exam ≤ A's? No (+0.068 > 0). Jitter sign
flip? No. → kill not auto-triggered. **Supersede bar (items 5+6) not met → the pilot
does not supersede static A as the product.** 5/7 items pass; both failures are in
the exam-soft and the thr1.10 jitter arm.

## Artifacts & provenance

- `results/pilot_results.json` — every ruler grade verbatim (centers, 12 jitter
  variants, shift-2, exam, slices, cross-check, hashes).
- `curves/C_engine_netfund.csv.gz`, `curves/A_engine_netfund.csv.gz` — net-of-costs
  engine books. Scratch (snapshots, variant formulas, probes): `/tmp/z076c_sub/`,
  `/tmp/pilot076c/` (probes only).
- Incident disclosure: a concurrent pilot process (same task family) clobbered
  `/tmp/pilot076c/` formula variants and rewrote `models/alpha_formulas/alpha_076c.py`
  during the first run; v2 re-ran from a hash-snapshotted template with content
  asserts in an isolated scratch dir. Final repo `alpha_076c.py` md5 `f70b45c06119`
  (gate state shift-1, warmup closed, plateau centroid — spec-faithful).
- Nothing committed; no files outside the declared scope touched.
