## Deribit ETH DVOL daily — QA

- File: `framework/data_cache/deribit_eth_dvol_daily.csv`, rows=2045, span 2021-03-24 → 2026-10-28 (2045 days)
- Task asked 2021-01-01 start; API returns nothing before **2021-03-24** (DVOL inception) — 83 requested days have no data
- Missing days within span: 0 (none — contiguous daily grid)
- open: min=30.69 max=193.37 mean=73.51 neg=0 NaN=0
- high: min=31.05 max=206.44 mean=75.76 neg=0 NaN=0
- low: min=30.12 max=182.97 mean=71.36 neg=0 NaN=0
- close: min=30.69 max=193.34 mean=73.51 neg=0 NaN=0
- close outside typical 30–120 band: 55/2045 (2.7%) — min close 30.69 (2023-08-11), max close 193.34 (2021-05-23)
- OHLC sanity (high>=low, close in [low,high]): 2045/2045

## OKX ETH lending rate (hourly) — QA

- Endpoint: `GET /api/v5/finance/savings/lending-rate-history?ccy=ETH` (public, no auth) — **LIVE, not DEAD**
- File: `framework/data_cache/okx_eth_lending_rate_hourly.csv`, rows=42687, span 2021-12-14 09:00:00 → 2026-10-28 08:00:00
- Expected hourly grid rows: 42696; actual 42687; missing 9 (0.02%); duplicates: 0
- rate: min=0.010000 max=0.800000 mean=0.013970 NaN=0 neg=0
- lendingRate: min=0.003200 max=0.800000 mean=0.013009 NaN=0 neg=0
- `rate` pinned at 0.01 on 30563/42687 rows (71.6%) — OKX floor/cap semantics; `lendingRate` is the varying utilization-driven field
- History depth found: back to 2021-12-14 (endpoint returns nothing older; 2021 not available from this source)
