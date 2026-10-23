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
- **Shift-2 retention ≥ 0.25** — position shifted 2 bars, same cost overlay;
  retention = shift-2 mean excess / center mean excess (genuine shift, not no-op).
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

*pending*
