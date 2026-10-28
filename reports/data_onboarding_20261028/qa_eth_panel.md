## ETHUSDT metrics 5m panel — QA

- File: `framework/data_cache/binance_um_metrics/ETHUSDT_metrics_5m.csv.gz` (19.6 MB gz), rows=515956, days=1792/1792 (2021-12-01 → 2026-10-27)
- Expected grid rows: 516096 (288/day × 1792d); actual 515956; deficit 140 (0.03%); duplicate timestamps: 0
- Days with >1% missing rows: 4

| day | rows | % of 288 |
|---|---|---|
| 2021-12-04 | 285 | 98.96 |
| 2023-09-12 | 285 | 98.96 |
| 2024-02-16 | 163 | 56.6 |
| 2025-08-29 | 285 | 98.96 |

### Per-column sanity

| column | min | max | first | last | neg | NaN | n outside 0.1–10 |
|---|---|---|---|---|---|---|---|
| sum_open_interest | 0 | 2.535e+06 | 363886 | 2.34665e+06 | 0 | 0 | 515956 |
| sum_open_interest_value | 0 | 1.17e+10 | 1.68393e+09 | 5.50708e+09 | 0 | 0 | 515956 |
| count_toptrader_long_short_ratio | 0.528 | 8.697 | 2.04368 | 2.65488 | 0 | 92219 | 0 |
| sum_toptrader_long_short_ratio | 0.8658 | 6.162 | 0.98913 | 1.73051 | 0 | 92181 | 0 |
| count_long_short_ratio | 0.5183 | 6.364 | 1.83382 | 3.05887 | 0 | 5789 | 0 |
| sum_taker_long_short_vol_ratio | 0 | 305.3 | 0.726271 | 0.582894 | 0 | 37247 | 82 |

- OI growth first→last: sum_open_interest ×6.45, sum_open_interest_value ×3.27 (monotone-ish growth expected: PASS)
- Ratio columns outside 0.1–10: 82/2063824 (0.00%) — wide excursions noted, not excluded

### Spot checks (5 rows vs raw zips)

- 2021-12-01 00:00:00: MATCH
- 2021-12-01 00:05:00: MATCH
- 2021-12-01 00:10:00: MATCH
- 2021-12-01 00:15:00: MATCH
- 2021-12-01 00:20:00: MATCH

### Correlation sanity: daily-mean OI_value vs OKX ETH daily close (5 dates)

| date | OI_value (mean, USD) | ETH close (OKX) |
|---|---|---|
| 2022-06-15 | 906,501,539 | 1,237.76 |
| 2023-06-15 | 1,423,222,675 | 1,666.50 |
| 2024-06-15 | 3,590,270,530 | 3,569.19 |
| 2025-06-15 | 4,772,905,994 | 2,547.53 |
| 2026-06-15 | 4,126,688,997 | 1,796.02 |

- Pearson r over the 5 points: **0.6107** (expected positive, not ~1)

### Publisher-side anomalies (present in raw zips, not introduced by extraction)

- `sum_open_interest` == 0 on 215 rows: concentrated 2022-03-07 (102), 2022-03-08 (15), 2024-07-09→15 (55 total), scattered single days otherwise — Binance publisher outages
- Ratio-column NaNs are embedded in the raw zips (blank fields): count_toptrader… NaNs span 2021-12-30→2025-07-22 (92,219 rows), sum_taker… NaNs span 2021-12-30→2022-09-14 (37,247 rows) — periods where Binance did not publish the field
