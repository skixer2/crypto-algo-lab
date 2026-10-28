#!/usr/bin/env python3
"""OKX ETH-USDT lending-rate history via public endpoint
GET /api/v5/finance/savings/lending-rate-history?ccy=ETH (hourly, paginated backward).
Public source, no auth. Data only."""
import csv
import json
import time
import urllib.request
from datetime import datetime, timezone

OUT = "/home/node/.openclaw/workspace/crypto/framework/data_cache/okx_eth_lending_rate_hourly.csv"
URL = "https://www.okx.com/api/v5/finance/savings/lending-rate-history?ccy=ETH"

def q(after=None):
    u = URL + (f"&after={after}" if after else "")
    req = urllib.request.Request(u, headers={"User-Agent": "curl/8"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read())
            if d.get("code") != "0":
                raise RuntimeError(f"code={d.get('code')} msg={d.get('msg')}")
            return d.get("data", [])
        except Exception as exc:
            print(f"retry {attempt+1}: {exc}", flush=True)
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("failed request")

rows = {}
after = None
pages = 0
while True:
    data = q(after)
    pages += 1
    if not data:
        break
    for rec in data:
        rows[int(rec["ts"])] = (rec.get("rate", ""), rec.get("lendingRate", ""))
    oldest = min(int(rec["ts"]) for rec in data)
    if after is not None and oldest >= after:
        print("pagination stalled; stop"); break
    after = oldest
    if pages % 40 == 0:
        print(f"page {pages}: total {len(rows)}, oldest "
              f"{datetime.fromtimestamp(after/1000, timezone.utc).isoformat()}", flush=True)
    time.sleep(0.15)

with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ts_utc", "rate", "lendingRate"])
    for ts in sorted(rows):
        rate, lr = rows[ts]
        iso = datetime.fromtimestamp(ts / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        w.writerow([iso, rate, lr])

print(f"WROTE {OUT} rows={len(rows)} pages={pages}")
