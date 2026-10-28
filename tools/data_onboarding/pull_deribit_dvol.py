#!/usr/bin/env python3
"""Deribit ETH DVOL daily history (2021-01-01 -> now) via public API.
Paginated, 86400s resolution. Output: framework/data_cache/deribit_eth_dvol_daily.csv
Data only — no strategy code."""
import csv
import json
import time
import urllib.request
from datetime import datetime, timezone

OUT = "/home/node/.openclaw/workspace/crypto/framework/data_cache/deribit_eth_dvol_daily.csv"
URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
# NOTE: live API requires 'currency' (not 'index_name'); caps response at 1000 rows.
# ETH DVOL history actually starts 2021-03-24 (QA finding).

start_ms = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
end_ms = int(time.time() * 1000)
CHUNK_MS = 500 * 86400 * 1000  # 500 days per request (API caps 1000 rows)

def fetch(s, e):
    q = f"?currency=eth&resolution=86400&start_timestamp={s}&end_timestamp={e}"
    req = urllib.request.Request(URL + q, headers={"User-Agent": "data-onboarding/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = json.loads(r.read())
            if payload.get("result") is None:
                raise RuntimeError(f"null result: {payload}")
            return payload["result"]["data"]
        except Exception as exc:
            print(f"retry {attempt+1} {s}-{e}: {exc}", flush=True)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed chunk {s}-{e}")

rows = {}
cursor = start_ms
nchunks = 0
while cursor < end_ms:
    cend = min(cursor + CHUNK_MS, end_ms)
    data = fetch(cursor, cend)
    nchunks += 1
    for rec in data:
        ts, o, h, l, c = rec
        rows[int(ts)] = (o, h, l, c)
    print(f"chunk {nchunks}: {datetime.fromtimestamp(cursor/1000, timezone.utc).date()} "
          f"+{len(data)} rows (total {len(rows)})", flush=True)
    if len(data) == 0 and cend >= end_ms:
        break
    if len(data) == 0:
        # advance anyway to avoid infinite loop
        cursor = cend
    else:
        last_ts = max(int(r[0]) for r in data)
        nxt = last_ts + 86400 * 1000
        if nxt <= cursor:
            cursor = cend
        else:
            cursor = nxt
    time.sleep(0.35)

with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ts", "open", "high", "low", "close"])
    for ts in sorted(rows):
        o, h, l, c = rows[ts]
        iso = datetime.fromtimestamp(ts / 1000, timezone.utc).strftime("%Y-%m-%d")
        w.writerow([iso, o, h, l, c])

print(f"WROTE {OUT} rows={len(rows)}")
