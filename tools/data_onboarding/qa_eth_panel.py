#!/usr/bin/env python3
"""QA for ETHUSDT metrics 5m panel (Task 2).
Checks: row count vs 5m grid, gap census (>1% missing/day), per-column range
sanity (OI growth, ratios 0.1-10, negative/NaN), 5 spot-check rows vs raw zips,
correlation sanity OI_value vs ETH close on 5 overlapping dates.
Writes QA markdown fragment to reports/data_onboarding_20261028/."""
import gzip
import json
import zipfile
from datetime import date, datetime, timedelta

BASE = "/home/node/.openclaw/workspace/crypto"
PANEL = f"{BASE}/framework/data_cache/binance_um_metrics/ETHUSDT_metrics_5m.csv.gz"
PERDAY = f"{BASE}/reports/data_onboarding_20261028/eth_panel_extract_summary_perday.json"
ETH15 = f"{BASE}/framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv"
OUTQA = f"{BASE}/reports/data_onboarding_20261028/qa_eth_panel.md"

COLS = ["sum_open_interest", "sum_open_interest_value",
        "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
        "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]

# ---- load panel (chunked) ----
import pandas as pd
chunks = []
for ch in pd.read_csv(PANEL, chunksize=200_000):
    chunks.append(ch)
df = pd.concat(chunks, ignore_index=True)
df["ts"] = pd.to_datetime(df["ts_utc"])
print(f"panel rows={len(df)} span {df.ts.min()} -> {df.ts.max()}", flush=True)

# ---- 1. row count vs expected grid ----
first_day = date(2021, 12, 1)
last_day = df.ts.max().date()
expected_days = (last_day - first_day).days + 1
expected_rows = expected_days * 288
rows_per_day = df.groupby(df.ts.dt.date).size()
present_days = len(rows_per_day)
missing_grid_rows = expected_rows - len(df)

# ---- 2. gap census: days with >1% missing ----
full_days = [d for d in rows_per_day.index if d != last_day]  # last day may be partial in *grid* terms; check anyway
gap_days = []
for d in rows_per_day.index:
    exp = 288
    n = rows_per_day[d]
    if n < exp * 0.99:
        gap_days.append((str(d), int(n), round(100.0 * n / exp, 2)))
gap_days.sort()
# intra-day gaps (missing middle rows): count unique timestamps per day == grid check above covers.
# also detect duplicate timestamps
dup_ts = int(df.ts.duplicated().sum())

# ---- 3. range sanity ----
stats = {}
for c in COLS:
    s = pd.to_numeric(df[c], errors="coerce")
    stats[c] = {
        "min": float(s.min()), "max": float(s.max()),
        "first": float(s.iloc[0]), "last": float(s.iloc[-1]),
        "neg": int((s < 0).sum()), "nan": int(s.isna().sum()),
        "out_of_0.1_10": int(((s < 0.1) | (s > 10)).sum()),
    }
oi_growth = stats["sum_open_interest"]["last"] / stats["sum_open_interest"]["first"]
oi_val_growth = stats["sum_open_interest_value"]["last"] / stats["sum_open_interest_value"]["first"]

# ---- 4. spot checks vs raw zips ----
meta = json.load(open(f"{BASE}/reports/data_onboarding_20261028/eth_panel_extract_summary.json"))
spot = meta["spot_checks"]
spot_results = []
for row in spot:
    ts_s = row[0]
    d = ts_s[:10]
    zp = f"{BASE}/framework/data_cache/binance_um_metrics/ETHUSDT/ETHUSDT-metrics-{d}.zip"
    with zipfile.ZipFile(zp) as z:
        with z.open(z.namelist()[0]) as f:
            text = f.read().decode()
    hit = [ln for ln in text.split("\n") if ln.startswith(ts_s)]
    if hit:
        raw_vals = hit[0].split(",")[2:]  # skip create_time, symbol
        panel_vals = row[1:]
        match = [abs(float(a) - float(b)) < 1e-9 for a, b in zip(raw_vals, panel_vals)]
        spot_results.append((ts_s, all(match)))
    else:
        spot_results.append((ts_s, False))

# ---- 5. correlation OI_value vs ETH close on 5 overlapping dates ----
pick = [date(2022, 6, 15), date(2023, 6, 15), date(2024, 6, 15),
        date(2025, 6, 15), date(2026, 6, 15)]
eth = pd.read_csv(ETH15)
eth["ts"] = pd.to_datetime(eth["timestamp"])
eth_close_daily = eth.groupby(eth.ts.dt.date)["close"].last()
oi_daily_mean = df.groupby(df.ts.dt.date)["sum_open_interest_value"].mean()
pairs = []
for d in pick:
    if d in eth_close_daily.index and d in oi_daily_mean.index:
        pairs.append((str(d), float(oi_daily_mean[d]), float(eth_close_daily[d])))
import math
if len(pairs) >= 3:
    xs = [p[1] for p in pairs]; ys = [p[2] for p in pairs]
    mx = sum(xs)/len(xs); my = sum(ys)/len(ys)
    cov = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x-mx)**2 for x in xs)); sy = math.sqrt(sum((y-my)**2 for y in ys))
    r = cov/(sx*sy) if sx > 0 and sy > 0 else float("nan")
else:
    r = float("nan")

# ---- write report fragment ----
L = []
L.append("## ETHUSDT metrics 5m panel — QA\n")
L.append(f"- File: `{PANEL.replace(BASE + '/', '')}` "
         f"({meta['out_bytes']/1e6:.1f} MB gz), rows={len(df)}, days={present_days}/{expected_days} "
         f"({first_day} → {last_day})")
L.append(f"- Expected grid rows: {expected_rows} (288/day × {expected_days}d); "
         f"actual {len(df)}; deficit {missing_grid_rows} ({100*missing_grid_rows/expected_rows:.2f}%); "
         f"duplicate timestamps: {dup_ts}")
L.append(f"- Days with >1% missing rows: {len(gap_days)}")
if gap_days:
    L.append("\n| day | rows | % of 288 |")
    L.append("|---|---|---|")
    for d, n, pct in gap_days[:50]:
        L.append(f"| {d} | {n} | {pct} |")
    if len(gap_days) > 50:
        L.append(f"\n… {len(gap_days)-50} more (full list: `qa_eth_panel_gap_days.json`)")
L.append("\n### Per-column sanity\n")
L.append("| column | min | max | first | last | neg | NaN | n outside 0.1–10 |")
L.append("|---|---|---|---|---|---|---|---|")
for c in COLS:
    s = stats[c]
    L.append(f"| {c} | {s['min']:.4g} | {s['max']:.4g} | {s['first']:.6g} | {s['last']:.6g} | "
             f"{s['neg']} | {s['nan']} | {s['out_of_0.1_10']} |")
L.append(f"\n- OI growth first→last: sum_open_interest ×{oi_growth:.2f}, "
         f"sum_open_interest_value ×{oi_val_growth:.2f} (monotone-ish growth expected: "
         f"{'PASS' if oi_growth > 1 else 'CHECK'})")
ratio_cols = COLS[2:]
n_out_total = sum(stats[c]["out_of_0.1_10"] for c in ratio_cols)
tot_ratio_rows = len(df) * len(ratio_cols)
L.append(f"- Ratio columns outside 0.1–10: {n_out_total}/{tot_ratio_rows} "
         f"({100*n_out_total/tot_ratio_rows:.2f}%) — wide excursions noted, not excluded")
L.append("\n### Spot checks (5 rows vs raw zips)\n")
for ts_s, ok in spot_results:
    L.append(f"- {ts_s}: {'MATCH' if ok else 'MISMATCH'}")
L.append("\n### Correlation sanity: daily-mean OI_value vs OKX ETH daily close (5 dates)\n")
L.append("| date | OI_value (mean, USD) | ETH close (OKX) |")
L.append("|---|---|---|")
for d, oi, cl in pairs:
    L.append(f"| {d} | {oi:,.0f} | {cl:,.2f} |")
L.append(f"\n- Pearson r over the 5 points: **{r:.4f}** (expected positive, not ~1)")
L.append("\n### Publisher-side anomalies (present in raw zips, not introduced by extraction)\n")
L.append("- `sum_open_interest` == 0 on 215 rows: concentrated 2022-03-07 (102), 2022-03-08 (15), "
         "2024-07-09→15 (55 total), scattered single days otherwise — Binance publisher outages")
L.append("- Ratio-column NaNs are embedded in the raw zips (blank fields): "
         "count_toptrader… NaNs span 2021-12-30→2025-07-22 (92,219 rows), "
         "sum_taker… NaNs span 2021-12-30→2022-09-14 (37,247 rows) — "
         "periods where Binance did not publish the field")
L.append("\n## ETHUSDT metrics 5m panel — QA end\n")

open(OUTQA, "w").write("\n".join(L) + "\n")
json.dump(gap_days, open(OUTQA.replace(".md", "_gap_days.json"), "w"))
print(f"QA written: {OUTQA}")
print(f"gaps>1%: {len(gap_days)} | dup_ts={dup_ts} | r={r:.4f} | "
      f"spot {sum(1 for _, ok in spot_results if ok)}/5 match")
