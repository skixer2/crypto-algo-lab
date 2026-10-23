# 076a-FAMILY PARAMETER SEARCH — SOL-USDT 15m (2026-10-23)

## PRE-REGISTERED OUTCOMES (verbatim, frozen before any run)

- **survivor** → flagged for holdout-style confirmation, **NOT deployment**.
- **none** → ledgered **no-pass**.

No interpretation beyond floors/exam verdicts. NOTE (pre-registered): the
portability run showed the frozen ETH config on SOL at squeeze-driven worst month
−38.5 and DD −85.6; most of the grid is expected to die at the floors. That is a
valid outcome. Do NOT add stops or new exits — family search only; new mechanisms
arrive as separate idea cards. Runs under `AGENT_CONTRACT.md` in full.

## Grid declaration (BEFORE any grading run)

**Provenance of the dimensions:** the ETH r3 family (reports/bull_mining_r3) is the
turtle-latch family × funding gate; its recorded 27-config search was the ±15%
jitter neighborhood of the ETH production point (N∈{163,192,221} × gate∈{0.595,0.7,
0.805} × buf∈{0.85,1.0,1.15}). As a *family-level* grid for a new asset that
neighborhood is too narrow around an ETH-fitted point, so per the brief the
**fallback family grid** is used, mirroring the same three dimensions at family
scale (identical to the 076a production-jitter dimension set):

- channel **N ∈ {144, 192, 288}**, `min_periods = N/2` (72/96/144), shift-1 channels
- ATR buffer mult **∈ {0.85, 1.0, 1.15}** on ATR96 = SMA(TR, 96, min_periods=32) (window fixed, r3/production convention)
- funding gate pctl **∈ {0.5, 0.7, 0.8}** (gate INSIDE the formula, `funding_gate_mode='formula'`)

3 × 3 × 3 = **27 configs**, all graded. Selection among survivors is by exam verdict,
never grid max.

**Path validation gate (pre-declared, runs first):** the center config
(N=192, buf=1.0, gate=0.7) is the frozen alpha_076a production config and MUST
reproduce the portability SOL netfund row to the digit (mean_exc −5.17, t −1.27,
DD −85.6, worst_abs −38.51, halves −7.55/−2.86). Divergence ⇒ abort, no search.

**Fixed conventions (AGENT_CONTRACT.md — zero freedom):**
- Data: `framework/data_cache/okx_SOL_USDT_15m_20210101_20260928.csv`, span
  2021-01-01 → 2026-07-28 seal. No other source, no resampling.
- Engine: formula-mode fast path (`prepare_fast_context` + `run_backtest`),
  decide@close, fill@next-open, 2× intrabar disaster rails (ATR 50/50 —
  effectively off), `allow_shorts=False`, engine fee=0.0, `warmup_candles=100`
  (warmup CLOSED — NaN channels ⇒ no entry; latch flat).
- Costs: fee 0.0008 netted on |Δpos|; funding = **binance settled proxy**
  (`binance_SOLUSDT_funding_proxy_202101_202610.csv`; portability-run convention —
  SOL has no bybit/okx-native cache; source stated here per portability header
  convention) charged at 00/08/16 UTC bars on position
  (`netting_on_curve`, seam-4 overlay). **Headline book = netted+funding.**
  Fee-free and fee-only books disclosed in results.json.
- Gate series: `build_fund_pct(df, "binance", "SOL/USDT")` — 30d rolling percentile
  of the ffilled settled rate, causal, NaN ⇒ gate closed.
- Ruler: `tools/stats_canonical.grade` ONLY, bench = same-asset buy-hold close.
  63 windows 2021-04..2026-06; July-26 partial disclosed by the ruler.
  The ruler's unit-tripwire carries the portability-verified in-process release
  (`GuardRelease`): SOL bench Aug-21 = +202.5% (raw closes, flagship-checked),
  window excess beyond ±band is real, not unit mix; `stats_canonical.py` untouched.

## Screen floors per config (hard, on the headline netfund book)

1. **OOS sign > 0** — `mean_excess_pct_mo > 0`
2. **worst absolute month ≥ −40%** — `worst_absolute_month_pct ≥ −40`
3. **both halves ≥ 0** — `first_half_pct ≥ 0 AND second_half_pct ≥ 0`

## Phase 2 battery (screen survivors only)

- **Jitter ±15%**, one-at-a-time, 6 neighbors (N→round(N·0.85)/round(N·1.15);
  buf→±15%; gate→±15%): all 6 sign-stable (`mean_excess_pct_mo > 0`) **and**
  halves ≥ 0.
- **Shift-2 retention ≥ 0.25** — genuine relabel: the decision/event series is
  shifted 2 bars INSIDE the formula and the engine re-runs with identical costs
  (r3 / btc_stress relabel convention); retention = shift-2 mean excess / center
  mean excess. *(Pre-run amendment 2026-10-23, committed before the run: the
  portability-style cost-overlay-only shift was rejected — it keeps the original
  PnL stream under the shifted position's costs, an incoherent book.)*
- **Anchored exam v3.2 soft scores** (theta **0.598**, sigma **0.22** — frozen
  verbatim as instructed) on the netfund monthly excesses vs the **SAME-ASSET
  raw-latch anchor**: same family (turtle latch), same (N, buf), **without funding
  gate**, netted+funding book. Report score and whether it clears the anchor line
  (clears = candidate soft mean ≥ anchor soft mean).
  Disclosed: `sigma_m(SOL bench)` is measured and reported next to the frozen
  sigma (ETH-frozen 0.22 used verbatim regardless).
- **One best-by-exam config per asset max** gets a full battery writeup
  (best = highest soft mean among battery-passing survivors).

## Pre-declared verdict logic

- config passes screen → survivor (phase 2).
- survivor passes jitter + retention + anchor line → battery-pass.
- best battery-pass (max one) → full writeup + flagged for holdout-style
  confirmation, NOT deployment.
- no battery-pass (incl. no screen survivor) → ledgered **no-pass**.

---

## RESULTS (filled after the run — pre-registration above untouched)

**Run metadata:** template md5 `137ce302a6c4` (== portability-run formula md5).
Path-validation gate: center config (N192/b1.0/g0.7) reproduced the portability
SOL netfund row **to the digit** (−5.17 / t −1.27 / DD −85.6 / worst −38.51 /
halves −7.55/−2.86) → MATCH, search proceeded. 27/27 grid runs completed, EXIT=0,
~10 min wall. GuardRelease fired on SOL out-of-band window extremes
(portability-precedent, disclosed in results.json per book).
Disclosed: `sigma_m(SOL bench) = 0.4332` (frozen σ 0.22 used verbatim per brief;
anchor exam not reached — no survivors).

## VERDICT (pre-registered branch): **none → ledgered no-pass**

**SCREEN: 0/27 survivors.** Phase 2 (jitter / shift-2 / anchored exam) not
executed — no config passed the screen. Survivor curves: none exist (curves/ is
intentionally empty).

### Floor pass counts (headline netfund book, 27 configs)

| floor | pass |
|---|---|
| OOS sign > 0 | **0 / 27** |
| worst absolute month ≥ −40 | 27 / 27 |
| both halves ≥ 0 | **0 / 27** |

### Full grid (mean excess %/mo per cell; every row failed floors 1+3)

| N \ buf | 0.85 | 1.0 | 1.15 |
|---|---|---|---|
| **gate 0.5** | −5.00 / −5.65 / −5.40 | −5.18 / −5.22 / −4.96 | −4.62 / −4.83 / −5.07 |
| **gate 0.7** | −4.65 / −4.70 / −4.71 | −5.35 / −5.17 / −4.95 | −3.96 / −3.99 / −4.24 |
| **gate 0.8** | −4.19 / −4.51 / −4.43 | −5.59 / −4.56 / −4.26 | −3.87 / −3.68 / −3.99 |

(cells = N ∈ {144, 192, 288} left→right; t ∈ [−0.99, −1.38] across the grid;
worst absolute month ∈ [−38.97, −24.0]; DD ∈ [−87.9, −64.0]; full per-config
rows in `grid.csv`, verbatim 3-book grades in `results.json`.)

**Range across the entire family: mean excess −3.68 … −5.65 %/mo; both halves
negative in all 27 configs.** No parameter region of the 076a family (channel
length × ATR buffer × funding-gate percentile) is standalone-positive on
SOL-USDT 15m under the canonical conventions. Per the pre-registered outcomes:
ledgered **no-pass**; ETH holdout path unaffected; new mechanisms for SOL arrive
as separate idea cards.
