#!/usr/bin/env python3
"""Archive lift 2021->present via OKX /market/history-candles (direct REST).

Writes framework/data_cache/okx_<SYM>_USDT_<tf>_20210101_20260928.csv with the
EXACT schema of the existing cache (ISO '+00:00' timestamps, same column order)
so the orchestrator/router consume it unchanged.

Pagination: OKX history-candles returns DESC, max 100/req; we page backwards
from now until start-of-2021, then reverse. Rate limit: <= 10 req/s (limit 20/2s).
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://www.okx.com/api/v5/market/history-candles"
OUT_DIR = "/home/node/.openclaw/workspace/crypto/framework/data_cache"
START_MS = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 9, 28, tzinfo=timezone.utc).timestamp() * 1000)

JOBS = [
    ("ETH-USDT", "15m"),
    ("ETH-USDT", "1H"),
    ("BTC-USDT", "15m"),
    ("BTC-USDT", "1H"),
]


def fetch_job(inst_id, bar):
    tf = "15m" if bar == "15m" else "1h"
    out = os.path.join(OUT_DIR, f"okx_{inst_id.replace('-', '_')}_{tf}_20210101_20260928.csv")
    if os.path.exists(out):
        print(f"[{inst_id} {bar}] exists, skip: {out}")
        return
    rows = []
    after = END_MS + 1
    req_n = 0
    while True:
        url = f"{BASE_URL}?instId={inst_id}&bar={bar}&after={after}&limit=100"
        req = urllib.request.Request(url, headers={"User-Agent": "archive-lift/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read())
        req_n += 1
        if payload.get("code") != "0":
            raise RuntimeError(f"[{inst_id} {bar}] okx code={payload['code']} msg={payload.get('msg')}")
        candles = payload.get("data") or []
        if not candles:
            break
        rows.extend(candles)
        oldest = int(candles[-1][0])
        if oldest <= START_MS:
            break
        after = oldest
        if req_n % 50 == 0:
            print(f"[{inst_id} {bar}] {req_n} reqs, {len(rows)} rows, oldest={datetime.fromtimestamp(oldest/1000, timezone.utc).date()}", flush=True)
        time.sleep(0.12)

    rows = [c for c in rows if int(c[0]) >= START_MS]
    rows.sort(key=lambda c: int(c[0]))
    # dedup on ts
    seen = set()
    ded = []
    for c in rows:
        ts = int(c[0])
        if ts not in seen:
            seen.add(ts)
            ded.append(c)
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        f.write("timestamp,open,high,low,close,volume\n")
        for c in ded:
            iso = datetime.fromtimestamp(int(c[0]) / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")
            f.write(f"{iso},{c[1]},{c[2]},{c[3]},{c[4]},{c[5]}\n")
    os.replace(tmp, out)
    print(f"[{inst_id} {bar}] DONE {len(ded)} rows -> {out}", flush=True)


if __name__ == "__main__":
    for inst_id, bar in JOBS:
        try:
            fetch_job(inst_id, bar)
        except Exception as e:
            print(f"[{inst_id} {bar}] FAILED: {e}", flush=True)
    print("ALL JOBS COMPLETE", flush=True)
