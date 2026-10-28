#!/usr/bin/env python3
"""Task 2: extract 1792 ETHUSDT daily metrics zips into ONE canonical 5m panel.
Output: framework/data_cache/binance_um_metrics/ETHUSDT_metrics_5m.csv.gz
Columns: ts_utc, sum_open_interest, sum_open_interest_value,
         count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
         count_long_short_ratio, sum_taker_long_short_vol_ratio
Data only — no strategy code. Also writes a QA sidecar summary JSON."""
import glob
import gzip
import io
import json
import os
import zipfile
from datetime import datetime, timezone

SRC = "/home/node/.openclaw/workspace/crypto/framework/data_cache/binance_um_metrics/ETHUSDT"
OUT = "/home/node/.openclaw/workspace/crypto/framework/data_cache/binance_um_metrics/ETHUSDT_metrics_5m.csv.gz"
QA = "/home/node/.openclaw/workspace/crypto/reports/data_onboarding_20261028/eth_panel_extract_summary.json"

COLS = ["sum_open_interest", "sum_open_interest_value",
        "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
        "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]

zips = sorted(glob.glob(os.path.join(SRC, "ETHUSDT-metrics-*.zip")))
print(f"zips found: {len(zips)}", flush=True)

n_files_with_symbol_mismatch = 0
rows_written = 0
per_day_rows = {}          # date -> rows
spot_checks = []           # 5 rows kept for verification
bad_rows = 0

with gzip.open(OUT, "wt", newline="") as out:
    out.write("ts_utc," + ",".join(COLS) + "\n")
    for zp in zips:
        day = os.path.basename(zp)[len("ETHUSDT-metrics-"):-len(".zip")]
        try:
            with zipfile.ZipFile(zp) as z:
                inner = z.namelist()[0]
                with z.open(inner) as f:
                    text = f.read().decode()
        except Exception as e:
            print(f"BAD ZIP {zp}: {e}", flush=True)
            per_day_rows[day] = -1
            continue
        lines = text.strip().split("\n")
        header = lines[0].split(",")
        idx = {c: header.index(c) for c in ["create_time", "symbol"] + COLS}
        n = 0
        for ln in lines[1:]:
            if not ln.strip():
                continue
            p = ln.split(",")
            try:
                ts = datetime.strptime(p[idx["create_time"]], "%Y-%m-%d %H:%M:%S"
                                       ).replace(tzinfo=timezone.utc)
                vals = [p[idx[c]] for c in COLS]
                if p[idx["symbol"]] != "ETHUSDT":
                    n_files_with_symbol_mismatch += 1
                if len(spot_checks) < 5:
                    spot_checks.append([ts.strftime("%Y-%m-%d %H:%M:%S")] + vals)
                out.write(ts.strftime("%Y-%m-%d %H:%M:%S") + "," + ",".join(vals) + "\n")
                n += 1
            except Exception:
                bad_rows += 1
        per_day_rows[day] = n
        rows_written += n
        if len(per_day_rows) % 400 == 0:
            print(f"processed {len(per_day_rows)} days, rows {rows_written}", flush=True)

meta = {
    "zips": len(zips),
    "rows_written": rows_written,
    "bad_rows": bad_rows,
    "symbol_mismatches": n_files_with_symbol_mismatch,
    "days": len(per_day_rows),
    "first_day": min(per_day_rows) if per_day_rows else None,
    "last_day": max(per_day_rows) if per_day_rows else None,
    "spot_checks": spot_checks,
    "out": OUT,
    "out_bytes": os.path.getsize(OUT),
}
os.makedirs(os.path.dirname(QA), exist_ok=True)
with open(QA, "w") as f:
    json.dump(meta, f, indent=1)
# per-day census for gap QA
with open(QA.replace(".json", "_perday.json"), "w") as f:
    json.dump(per_day_rows, f, indent=0)
print(f"DONE rows={rows_written} days={len(per_day_rows)} "
      f"gz_bytes={meta['out_bytes']} bad={bad_rows}", flush=True)
