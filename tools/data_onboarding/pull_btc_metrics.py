#!/usr/bin/env python3
"""BTCUSDT metrics pull from Binance Vision (2020-09-01 -> today).
Sequential urllib, 0.25s sleep, skip existing, PULL_COMPLETE marker.
Pattern: identical to completed ETHUSDT pull. Data only — no strategy code."""
import urllib.request
import time
import os
import sys
from datetime import date, timedelta

BASE = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/"
OUT = "/home/node/.openclaw/workspace/crypto/framework/data_cache/binance_um_metrics/BTCUSDT"
START = date(2020, 9, 1)
END = date.today()  # inclusive; today's file may not exist yet -> 404 tolerated
os.makedirs(OUT, exist_ok=True)

log = open(os.path.join(OUT, "pull.log"), "a", buffering=1)
def L(msg):
    log.write(msg + "\n")

d = START
n_new = n_skip = n_404 = n_err = 0
while d <= END:
    fn = f"BTCUSDT-metrics-{d.isoformat()}.zip"
    path = os.path.join(OUT, fn)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        n_skip += 1
    else:
        url = BASE + fn
        ok = False
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "data-onboarding/1.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = r.read()
                tmp = path + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, path)
                n_new += 1
                ok = True
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    n_404 += 1
                    L(f"404 {fn}")
                    ok = None  # expected for today/future dates
                    break
                L(f"HTTP {e.code} {fn} attempt {attempt+1}")
                time.sleep(2 * (attempt + 1))
            except Exception as e:
                L(f"ERR {fn} attempt {attempt+1}: {e}")
                time.sleep(2 * (attempt + 1))
        if ok is False:
            n_err += 1
    d += timedelta(days=1)
    time.sleep(0.25)

L(f"SUMMARY new={n_new} skip={n_skip} notfound={n_404} errors={n_err}")
open(os.path.join(OUT, "PULL_COMPLETE"), "w").write(
    f"new={n_new} skip={n_skip} notfound={n_404} errors={n_err}\n")
print("DONE")
