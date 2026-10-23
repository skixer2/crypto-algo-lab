# 076a-FAMILY PARAMETER SEARCH — BTC-USDT 15m (pre-registered)

**Date:** 2026-10-23 · **Asset:** BTC-USDT 15m (per-asset tailoring, JP-directed) · **Seat:** fsearch-btc subagent
**Contract:** `AGENT_CONTRACT.md` in full. Ruler: `tools/stats_canonical.grade` ONLY. Bench = same-asset buy-hold (BTC close, seal 2026-07-28).
**Pre-registration:** this section written BEFORE any grading run. Outcomes branch is fixed: **survivor -> flagged for holdout-style confirmation, NOT deployment; none -> ledgered no-pass.** No interpretation beyond floors/exam verdicts.

## Engine + costs (zero freedom, portability-076a path verbatim)

`tools/portability_076a.py` is the template: formula-mode engine (`tuner.alpha_orchestrator.run_backtest`, fast context via `models.wq_alpha_fast.prepare_fast_context`), `fund_pct` injection seam (`funding_gate_mode="formula"`), decide@close / fill@next-open, 2× intrabar disaster rails (ATR 50/50 — effectively off), `allow_shorts=False`, engine fee=0.0 (pool convention), span 2021-01-01 -> 2026-07-28, warmup_candles=100 (frozen production recipe).
Costs: fee 0.0008 netted on |Δpos| + funding charged at 00/08/16 UTC bars on the position (`netting_on_curve`, portability convention). **Headline book = netted+funding ("netfund").**
**Funding source (header, as required):** funding = **binance settled proxy** (`framework/data_cache/binance_BTCUSDT_funding_proxy_202101_202610.csv`), the portability-run convention for BTC (no bybit cache exists for this pair; ETH production uses binance+bybit avg for COSTS — not applicable here). Gate series = causal 30d rolling percentile of the ffilled settled rate (`build_fund_pct`, symbol BTC/USDT).

## Grid — PRE-REGISTERED (Phase 1)

**Source (recovered, not fallback):** the ETH r3 family dimensions are the round-3 jitter neighborhood of the committed funding-gated turtle192, `reports/bull_mining_r3/REPORT.md` §Robustness + `reports/bull_mining_r3/jitter_bin_g0.7.json`: N ∈ {163, 192, 221} × gate pctl ∈ {0.595, 0.7, 0.805} × ATR-mult (buf) ∈ {0.85, 1.0, 1.15} = **27 configs**. Center = committed 076a production spec (N192, gate 0.7, buf 1.0).
**Formula family:** `models/alpha_formulas/alpha_076a.py` with N, buf, gate substituted (same replacements as the 076c pilot's engine jitter: `rolling({N}, min_periods={N//2})` both channels, `tl - {buf} * atr`, `fund < {gate}`). mp = N/2 per brief. Long-only. Warmup CLOSED (engine warmup 100 bars + NaN channels before mp bars; no trading during warmup).

| dim | values |
|-----|--------|
| N (channel) | 163, 192, 221 |
| ATR mult (exit buffer) | 0.85, 1.0, 1.15 |
| gate pctl (fund_pct < g) | 0.595, 0.7, 0.805 |

## Screen floors per config — HARD (Phase 1, netfund book)

1. OOS sign > 0 (`mean_excess_pct_mo` > 0)
2. worst absolute month >= −40 (`worst_absolute_month_pct` >= −40)
3. both halves >= 0 (`first_half_pct` >= 0 AND `second_half_pct` >= 0)

## Phase 2 battery — only for screen passers

1. **Jitter ±15%, 6 neighbors** (2 per dimension; N rounded to nearest int, buf/gate rounded to 3 dp): every neighbor netfund sign-stable (mean excess > 0) AND both halves >= 0. Requirement: 6/6.
2. **Shift-2 retention >= 0.25** — GENUINE relabel (twin lesson 2026-10-23: pos-series-on-engine-curve shift is vacuous for a slow latch). Substrate: `ret = close.pct_change()`, eff = engine effective position (center) vs `eff.shift(1)` (shift-2 relabel: the decision acts one extra bar later), fee 0.0008·|Δeff|, funding −rate·eff at 8h bars; both legs same substrate, ruler-graded; retention = mean_excess(shift-2)/mean_excess(center), netfund.
3. **Anchored exam v3.2 soft scores** — theta **0.598**, sigma **0.22** (frozen, per brief; `soft_scores` verbatim), per-month excesses of the netfund book vs BTC bench monthly returns. **Anchor = SAME-ASSET raw-latch**: BTC turtle192 N192/buf1.0 WITHOUT funding gate, netted book, same engine path, same ruler. **Anchor line = the anchor's own anchored score under the same theta/sigma.** Candidate clears iff candidate score > anchor score (strict; the un-gated parent wins ties, simplicity law). Sigma_m(BTC bench) and the theta inversion check on the BTC anchor are computed and disclosed alongside (diagnostics only — frozen 0.598/0.22 used in all scores).

**Best-by-exam:** at most ONE config per asset gets the full battery writeup — highest anchored v3.2 soft score among configs passing screen + 6/6 jitter + retention >= 0.25 + anchored-clears; ties -> lower N, then lower gate (simplicity).
**Survivor (pre-registered):** screen-pass AND 6/6 jitter sign-stable with halves >= 0 AND shift-2 retention >= 0.25 AND anchored score clears the anchor line. Survivor -> flagged for holdout-style confirmation, NOT deployment. None -> ledgered no-pass.

## Artifacts (planned)

`tools/family_search_BTC.py` (this search, tmp-isolated per PID under /tmp/fsearch_BTC_*), `grid.csv` (27 rows + battery columns), `results.json` (verbatim ruler dicts), `curves/` (netfund + pos for screen passers and the anchor), this REPORT (pre-registration above, machine-appended results below).

---

# RESULTS (appended after the run — nothing below existed at pre-registration)
