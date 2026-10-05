#!/usr/bin/env python3
"""OKX order-book depth snapshot recorder (ETH-USDT, 400 levels/side).

Detached daemon started via exec (no crontab in this container). Cadence 5 min.
Disk budget (MEASURED 2026-10-05: 24.4 KB/snapshot raw):
  raw   ~6.9 MB/day -> ~208 MB/month
  gzip  ~25 MB/month (JSON compresses ~8x)
  retention: raw .jsonl gzipped at day roll, .gz pruned >90 days
  steady state ~75 MB; HARD CAP 2 GB -> HALT file + stop appending.
Liveness: HEARTBEAT.md check `pgrep -f depth_recorder` -> restart one-liner.
"""
import gzip
import json
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta

BASE = "/home/node/.openclaw/workspace/crypto/data/depth"
INST = "ETH-USDT"
URL = f"https://www.okx.com/api/v5/market/books?instId={INST}&sz=400"
CADENCE_S = 300
RETENTION_DAYS = 90
HARD_CAP_BYTES = 2 * 1024**3

d = os.path.join(BASE, INST)
os.makedirs(d, exist_ok=True)
log = os.path.join(d, "recorder.log")


def plog(msg):
    with open(log, "a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")


def gz_previous_days(today_str):
    for fn in os.listdir(d):
        if fn.endswith(".jsonl") and fn != f"depth_{today_str}.jsonl":
            src = os.path.join(d, fn)
            try:
                with open(src, "rb") as fin, gzip.open(src + ".gz", "wb") as fout:
                    fout.writelines(fin)
                os.remove(src)
                plog(f"gzipped {fn} -> {os.path.getsize(src + '.gz')} B")
            except Exception as e:
                plog(f"gzip FAIL {fn}: {e}")


def prune_old():
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    for fn in os.listdir(d):
        if fn.startswith("depth_") and fn.endswith(".jsonl.gz"):
            try:
                day = datetime.strptime(fn[6:14], "%Y%m%d").replace(tzinfo=timezone.utc)
                if day < cutoff:
                    os.remove(os.path.join(d, fn))
            except ValueError:
                pass


def dir_bytes():
    return sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d))


plog(f"recorder start pid={os.getpid()} cadence={CADENCE_S}s retention={RETENTION_DAYS}d")
misses = 0
while True:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    halt = os.path.join(d, "HALT")
    if os.path.exists(halt):
        plog("HALT present — idling (remove HALT to resume)")
        time.sleep(3600)
        continue
    try:
        gz_previous_days(today)
        if datetime.now(timezone.utc).hour == 0 and datetime.now(timezone.utc).minute < CADENCE_S // 60:
            prune_old()
        if dir_bytes() > HARD_CAP_BYTES:
            open(halt, "w").write(datetime.now(timezone.utc).isoformat())
            plog("HARD CAP exceeded — HALT written")
            continue
        req = urllib.request.Request(URL, headers={"User-Agent": "depth-recorder/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            payload = json.loads(r.read())
        if payload.get("code") != "0" or not payload.get("data"):
            raise RuntimeError(f"okx code={payload.get('code')}")
        book = payload["data"][0]
        line = json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "bids": book["bids"], "asks": book["asks"], "checksum": book.get("checksum"),
        }, separators=(",", ":"))
        with open(os.path.join(d, f"depth_{today}.jsonl"), "a") as f:
            f.write(line + "\n")
        misses = 0
    except Exception as e:
        misses += 1
        plog(f"miss #{misses}: {e}")
        if misses >= 96:  # ~8h of consecutive failures = something structural
            plog("96 consecutive misses — still alive, check manually")
            misses = 0
    time.sleep(CADENCE_S)
