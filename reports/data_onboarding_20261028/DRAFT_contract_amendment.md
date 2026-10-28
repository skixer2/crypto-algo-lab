# DRAFT — Contract Amendment: Declared Data Columns (data onboarding 2026-10-28)

STATUS: DRAFT for operator review — not yet binding. No line of AGENT_CONTRACT.md
has been changed. On approval these become declared caches alongside the existing
`okx_ETH_USDT_15m…` / funding / OI caches ("named OI/funding caches only" clause
extends to these files, by path).

## Amendment text (proposed)

Replace the Data row's cache list with:

> Data | `framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv` (primary);
> `okx_BTC_USDT_15m_20210101_20260928.csv` (conditioning), reindex-ffill to ETH
> index; plus the DECLARED EXTERNAL PANELS below, joined on UTC timestamp with
> last-known-value ffill limited to their own native cadence. No other external
> fetch, no other venues, no resampling except canonical patterns.

### D1. Binance UM metrics panel — ETHUSDT, 5-minute bars

- Path: `framework/data_cache/binance_um_metrics/ETHUSDT_metrics_5m.csv.gz`
- Source: Binance Vision daily metrics archive
  `data/futures/um/daily/metrics/ETHUSDT/ETHUSDT-metrics-<YYYY-MM-DD>.zip`
- Granularity: 5 minutes; `ts_utc` = bar open time, UTC (`YYYY-MM-DD HH:MM:SS`)
- Coverage: 2021-12-01 → present (Binance publishes ETHUSDT metrics only from 2021-12-01)
- Columns and exact definitions (per Binance futures data docs, verbatim semantics):
  - `sum_open_interest` — total open interest across all ETHUSDT perpetual
    contracts, in base asset units (ETH).
  - `sum_open_interest_value` — same, in notional USDT (OI × mark price at bar time).
  - `count_toptrader_long_short_ratio` — long/short ACCOUNT ratio of top traders
    (global, top 20% of accounts by margin balance): accounts long / accounts short.
  - `sum_toptrader_long_short_ratio` — long/short POSITION ratio of top traders
    (top 20% of accounts by margin balance): sum of long positions / sum of short
    positions, in contracts.
  - `count_long_short_ratio` — global long/short ACCOUNT ratio, all users.
  - `sum_taker_long_short_vol_ratio` — taker BUY volume / taker SELL volume
    (active buying vs selling), same 5m window.
- Publication lag: each daily zip lands on Binance Vision on day D+1; last
  complete day is therefore T-1. Intraday use requires a live REST refresh (not in scope).
- Known holes (embedded in raw source, declared not repaired): publisher zero-OI
  outages 2022-03-07/08, 2024-07-09→15, scattered days; blank ratio fields
  (NaN) 2021-12-30→2025-07-22 for top-trader columns, →2022-09-14 for taker ratio.

### D2. Deribit ETH DVOL (implied volatility index), daily bars

- Path: `framework/data_cache/deribit_eth_dvol_daily.csv`
- Source: Deribit public API `GET /api/v2/public/get_volatility_index_data`
  with `currency=eth`, `resolution=86400` (live API param is `currency`, not `index_name`)
- Granularity: 1 day; `ts` = UTC date; OHLC of the DVOL index value (annualized
  implied vol, %)
- Coverage: 2021-03-24 (index inception) → present. Requests before inception return empty.
- Publication lag: index computes continuously; daily bar closes at 00:00 UTC.
  Use T-1 as last complete bar.
- Range: observed close 30.7–193.3 (May-2021 crash peak); treat values outside
  ~25–250 as suspect.

### D3. OKX ETH lending rate (Simple Earn/savings), hourly

- Path: `framework/data_cache/okx_eth_lending_rate_hourly.csv`
- Source: OKX public API `GET /api/v5/finance/savings/lending-rate-history?ccy=ETH`
  (no auth)
- Granularity: 1 hour; `ts_utc` = hour start, UTC
- Columns:
  - `rate` — advertised annualized lending rate for the hour; floored at 0.01
    (1%) for ~72% of samples (OKX floor) and capped at 0.80 in stress.
  - `lendingRate` — actual rate paid to lenders (utilization-driven); varies
    below the floor. This is the economically meaningful series.
- Coverage: 2021-12-14 → present (endpoint returns nothing older); 9 missing
  hours in 42,696-slot grid (0.02%).
- Publication lag: hourly, ~1 h. Use T-1 h as last complete bar.

### D4. Binance UM metrics panel — BTCUSDT, 5-minute bars (zips landed; panel pending)

- Zips: `framework/data_cache/binance_um_metrics/BTCUSDT/` — **2,248 files,
  2020-09-01 → 2026-10-27, 0 missing days** (hyphenated filenames,
  `PULL_COMPLETE: new=2248 skip=0 notfound=1 errors=0`).
- Canonical panel file to be built by the same extractor
  (`tools/data_onboarding/build_eth_metrics_panel.py`) when the operator green-lights
  it; same column definitions as D1.
- BTCUSDT metrics coverage predates ETHUSDT by ~15 months (2020-09-01 vs 2021-12-01).

## Join discipline (proposed)

External panels are conditioning inputs only. Join on UTC timestamp to the
canonical 15m ETH grid by resampling DOWN (5m→15m: last value in window; 1d/1h→15m:
ffill with `limit` = native cadence) — resampling choice to be fixed once in the
canonical loader, not per-candidate. Warmup rules unchanged: no trading while a
joined panel is still NaN.

## What this amendment does NOT do

- Does not touch engine, costs, ruler, or grading conventions.
- Does not authorize any new venue for price data (all price bars remain OKX canonical).
- Does not make any performance claim.
