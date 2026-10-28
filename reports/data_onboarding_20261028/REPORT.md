# Data Onboarding Report — 2026-10-28

Operator-delegated infrastructure onboarding (JP, 2026-10-28). DATA ONLY:
no strategy code, no formula files, no engine changes, no performance numbers.
AGENT_CONTRACT.md observed throughout — nothing in `models/`, `tools/stats_canonical.py`,
or existing caches was modified. All pulls read-only public endpoints; new files only.

Run environment: `nice -n 10`, sequential pulls with polite sleeps. Scripts kept in
`tools/data_onboarding/` for reproducibility.

---

## Task 1 — BTCUSDT metrics pull (Binance Vision)

- Pattern: identical to the completed ETHUSDT pull. Sequential `urllib`, 0.25 s
  sleep between requests, skip-if-exists, 3 retries, 404 tolerated (today's file
  publishes D+1). Filename convention: `BTCUSDT-metrics-YYYY-MM-DD.zip` (hyphens).
- Destination: `framework/data_cache/binance_um_metrics/BTCUSDT/`
- Range requested: 2020-09-01 → 2026-10-28 (today).
- Result: **2,248/2,248 zips on disk, 2020-09-01 → 2026-10-27, 0 missing days,
  0 errors** (the only 404 is today's file, which publishes D+1).
- Zip integrity: 10-zip sample (first 5 + last 5) opens clean with expected header.
- QA: `qa_btc_pull.md`. PULL_COMPLETE marker: `new=2248 skip=0 notfound=1 errors=0`.
- Canonical 5m panel for BTCUSDT is NOT built in this pass (task scoped the
  panel build to ETH); zips are on disk at the declared path and the same
  extractor (`tools/data_onboarding/build_eth_metrics_panel.py`) applies as-is.

## Task 2 — ETHUSDT metrics canonical 5m panel

- Input: 1,792 daily zips (2021-12-01 → 2026-10-27) already in
  `framework/data_cache/binance_um_metrics/ETHUSDT/` (PULL_COMPLETE marker present).
- Extraction: python `zipfile` (no unzip binary on host), all fields verbatim from
  raw CSVs; `create_time` taken as UTC → `ts_utc`.
- Output: `framework/data_cache/binance_um_metrics/ETHUSDT_metrics_5m.csv.gz`
  (19.6 MB gz; columns exactly: ts_utc, sum_open_interest, sum_open_interest_value,
  count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
  count_long_short_ratio, sum_taker_long_short_vol_ratio).
- Result: **515,956 rows / 1,792 days / 0 bad rows / 0 duplicate timestamps**.
- Full QA: `qa_eth_panel.md` (+ `qa_eth_panel_gap_days.json`). Headlines:
  - Grid deficit 140 rows (0.03%) vs perfect 288×1792 grid; only 4 days >1% short
    (worst: 2024-02-16 with 56.6% — source-side outage).
  - Spot checks 5/5 MATCH vs raw zips.
  - OI growth ×6.45 (units) / ×3.27 (USD notional) first→last; ratios sane
    (82/2.06M rows outside 0.1–10; no negatives anywhere).
  - Publisher-side anomalies declared, not repaired: zero-OI outages
    (2022-03-07/08, 2024-07-09→15, ~215 rows), blank ratio fields in raw zips
    (NaN: 92k/92k/5.8k/37k rows per column).
  - Correlation sanity: daily-mean OI_value vs OKX ETH close on 5 overlapping
    dates → Pearson r = **0.6107** (positive, not ~1 — passes).

## Task 3 — Deribit ETH DVOL daily

- Endpoint: `GET /api/v2/public/get_volatility_index_data` — live API takes
  `currency=eth` (the `index_name=eth_dvol` form from the brief returns 400
  `Invalid params: currency`); `resolution=86400`; paginated forward in 500-day
  chunks (API caps 1,000 rows/response).
- Output: `framework/data_cache/deribit_eth_dvol_daily.csv` (ts, open, high, low, close).
- Result: **2,045 daily rows, 2021-03-24 → 2026-10-28, zero internal gaps**.
- QA (`qa_dvol_okx_lending.md`):
  - Row count = full day grid since inception; **no data exists before 2021-03-24**
    (83 requested days from 2021-01-01 are absent upstream — DVOL inception).
  - Range: close 30.69 (2023-08-11) → 193.34 (2021-05-23); 2.7% of days outside
    the "typical" 30–120 band, all at crisis extremes; no negatives, no NaNs.
  - OHLC internal consistency: 2,045/2,045 pass.

## Task 4 — OKX ETH-USDT lending-rate history

- **Outcome: LIVE — public history exists; no DEAD mark.**
- Endpoint: `GET /api/v5/finance/savings/lending-rate-history?ccy=ETH` (public,
  no auth; hourly; paginated backward with `after`, limit 100/page, 428 pages).
- Output: `framework/data_cache/okx_eth_lending_rate_hourly.csv`
  (ts_utc, rate, lendingRate).
- Result: **42,687 hourly rows, 2021-12-14 → 2026-10-28; 9 missing hours (0.02%); 0 dups.**
- Semantics (declared in draft amendment): `rate` = advertised rate, pinned at the
  0.01 floor 71.6% of samples; `lendingRate` = actual utilization-driven paid rate
  (min 0.0032, max 0.80). History does not reach 2021-01; upstream begins 2021-12-14.
- Also probed and rejected: `/api/v5/public/interest-rate-loan-quota` (current
  margin borrow rates only, no history — noted as alternative semantics if the
  operator wants margin *borrow* rates instead of savings *lending* rates).

---

## Files landed

| path | kind | size |
|---|---|---|
| `framework/data_cache/binance_um_metrics/BTCUSDT/*.zip` | cache zips | 21 MB+ (growing) |
| `framework/data_cache/binance_um_metrics/ETHUSDT_metrics_5m.csv.gz` | canonical panel | 19.6 MB |
| `framework/data_cache/deribit_eth_dvol_daily.csv` | cache csv | ~150 KB |
| `framework/data_cache/okx_eth_lending_rate_hourly.csv` | cache csv | ~2.5 MB |
| `tools/data_onboarding/*.py` | reproducibility scripts | — |
| `reports/data_onboarding_20261028/*` | QA + this report + amendment draft | — |

## Git handling

The whole `framework/data_cache/` tree is gitignored by repo policy
(`.gitignore:22`), so ALL cache files (zips, panel, DVOL csv, lending csv) stay
on disk at the paths declared above — not even the 19.6 MB panel is force-added.
Committed (new files only): this report, the QA fragments, the amendment draft,
and the reproducibility scripts under `tools/data_onboarding/`. No pre-existing
modified/untracked files from other workstreams were touched.

## Interpretation discipline

No strategy claims, no ranking, no "this panel is useful for X" — that is
proposal work and out of scope here.
