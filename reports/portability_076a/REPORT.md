# alpha_076a PORTABILITY READOUT — BTC-USDT & SOL-USDT 15m (2026-10-23)

**Pre-registered reading (verbatim, frozen before the run):** both-positive =
mechanism portability confirmed; mixed = ETH-specific (noted, product unchanged);
negative = warning flagged to operator.

**Run type:** operator-directed canonical readout — Machine A (alpha_076a) VERBATIM,
production params exactly as frozen in the ETH path. NO re-tuning, NO grids, NO
variants. Ruler: `tools/stats_canonical.grade` only, bench = same-asset buy-hold.
63 windows 2021-04..2026-06; July-26 partial disclosed separately by the ruler.

**Frozen spec (manifest-normative, asserted equal to `alpha_076a.py` at run time):**
channel 192 (`min_periods=96`, shift-1), exit channel 192 − 1.0×ATR96
(SMA of TR, min_periods 32), funding gate pctl 0.7 INSIDE the formula
(`funding_gate_mode='formula'`, injected `fund_pct` column), long-only
(`allow_shorts=False`), warmup closed, decide@close / fill@next-open, 2× intrabar
disaster rails (ATR 50/50), engine fee=0.0 (pool convention). Formula md5 at run
time: `137ce302a6c4`.

**Funding sources (per asset):**
- **ETH/USDT** (reference): gate = binance settled proxy; funding cost = binance+bybit avg — the exact production convention (`binance_ETHUSDT_funding_proxy_202101_202610.csv` + `bybit_ETHUSDT_funding_202101_202610.csv`).
- **BTC/USDT**: gate = binance settled proxy; funding cost = binance only (`binance_BTCUSDT_funding_proxy_202101_202610.csv`).
- **SOL/USDT**: gate = binance settled proxy; funding cost = binance only (`binance_SOLUSDT_funding_proxy_202101_202610.csv`; no okx-native/bybit cache exists for SOL).

**Cost overlay (all assets):** fee 0.0008 netted on |Δpos| + settled funding charged
at 00/08/16 UTC bars on position (ENG_funding_plumbing seam-4 overlay convention).
**Headline book below = netted + funding** (the readout convention).

## Readout — 5-line table per asset (netted-fees + funding book)

| metric | BTC-USDT 15m | SOL-USDT 15m |
|---|---|---|
| mean_excess_pct_mo | **−2.19** | **−5.17** |
| t | −1.58 | −1.27 |
| continuous_dd_pct | −65.4 | −85.6 |
| worst_absolute_month_pct | −18.55 | −38.51 |
| halves (first/second) | +0.25 / −4.55 | −7.55 / −2.86 |

ETH/USDT reference (same path, rerun): mean_excess_pct_mo **+1.95**, t 1.29,
continuous_dd_pct −47.5, worst_absolute_month_pct −18.83, halves +1.87 / +2.02.

**Pre-registered reading, applied:** BTC negative, SOL negative → **warning flagged
to operator** (ETH-specific; product unchanged — alpha_076a stays the ETH product).

## Validation (path integrity, all asserted in the runner)

- Engine rerun of 076a on ETH == stored production curve `data/precompute/alpha_076a.csv.gz`: **100.0%** bar-exact position agreement.
- ETH fee-free grade reproduces the manifest's stored production grade exactly: +2.89 t1.96 DD −46.2 worst-abs −18.47 (all four fields identical).
- ETH net-of-costs row reproduces the 076c pilot's 076a row exactly: +1.95 t1.29 DD −47.5 worst-abs −18.83 halves +1.87/+2.02.

## Appendix — full ruler output, all three books (verbatim)

| asset | book | net %/mo | t | DD % | worst abs % | worst win % | best win % | halves % | fee/mo % | time-in | neg windows | July-26 % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | fee-free (engine) | +2.89 | 1.96 | −46.2 | −18.47 | −31.39 | +31.60 | +2.90/+2.87 | — | 53% | 25/63 | −9.98 |
| ETH | netted-fees | +2.47 | 1.67 | −47.1 | −18.80 | −31.75 | +30.98 | +2.48/+2.47 | 0.40 | 53% | 27/63 | −10.68 |
| ETH | netted+funding | +1.95 | 1.29 | −47.5 | −18.83 | −32.70 | +28.29 | +1.87/+2.02 | 0.40 | 53% | 29/63 | −10.98 |
| BTC | fee-free (engine) | −1.40 | −1.02 | −52.7 | −17.98 | −39.67 | +28.41 | +1.16/−3.89 | — | 49% | 38/63 | −12.15 |
| BTC | netted-fees | −1.85 | −1.34 | −59.5 | −18.50 | −39.83 | +28.12 | +0.70/−4.33 | 0.45 | 49% | 38/63 | −12.77 |
| BTC | netted+funding | −2.19 | −1.58 | −65.4 | −18.55 | −39.89 | +27.96 | +0.25/−4.55 | 0.45 | 49% | 40/63 | −12.96 |
| SOL | fee-free (engine) | −4.44 | −1.10 | −84.1 | −38.04 | −185.83* | +63.48 | −6.80/−2.17 | — | 51% | 32/63 | −11.76 |
| SOL | netted-fees | −4.83 | −1.19 | −85.0 | −38.53 | −186.21* | +63.14 | −7.20/−2.54 | 0.40 | 51% | 32/63 | −12.47 |
| SOL | netted+funding | −5.17 | −1.27 | −85.6 | −38.51 | −187.29* | +64.33 | −7.55/−2.86 | 0.40 | 51% | 32/63 | −12.55 |

\* **Ruler guard release (disclosed):** `stats_canonical._boundary_pct`'s
−100%..+1000% window plausibility assert tripped on these three values; released
in-process only (arithmetic byte-identical; `tools/stats_canonical.py` untouched).
Proof of legitimacy from raw closes (audit in `results.json`): SOL same-asset
buy-hold returned **+202.52% in 2021-08** while the strategy returned +15.23% —
the −187.29 window "excess" is real arithmetic against a violent benchmark month,
not a unit mix. (SOL bench months: +202.5% Aug-21, +140.5% Jan-23, +120.7% Apr-21;
raw close range 1.499..294.89, no data glitches.)

## Artifacts

- Runner: `tools/portability_076a.py` (strict ruler first; guard release only on tripwire, with per-window audit).
- Results: `reports/portability_076a/results.json` (full verbatim grade dicts + guard-release audit + funding sources).
- Curves: `reports/portability_076a/curves/076a_{BTC,SOL}_netfund.csv.gz`, `076a_{BTC,SOL}_pos.csv.gz`.
- Run log: `reports/portability_076a/run.log`.

*Readout only. No interpretation beyond the table and the pre-registered reading, per operator directive.*
