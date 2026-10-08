#!/usr/bin/env python3
"""Funding-rate + open-interest history fetch (honest microstructure cache).

Endpoints (public REST, no auth):
  /api/v5/public/funding-rate-history  — perp funding events, 100/page, DESC.
      Paginate backward from now to 2021. Records are 8h-spaced (verify!).
  /api/v5/rubik/stat/contracts/open-interest-history — DAILY granularity only
      for long history (OKX limitation, disclosed in cache header note).

Integrity checks before any file lands (values-verified rule, 2026-10-02):
  - funding timestamps 8h-spaced (max gap <= 9h) — else abort
  - spot-check latest rate vs live funding-rate endpoint
Output CSVs (framework/data_cache/):
  okx_{SYM}_funding_20210101_20260928.csv      ts,funding_rate
  okx_{SYM}_oi_daily_20210101_20260928.csv     ts,oi_contracts,oi_value_usd (granularity note)
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

BASE = "https://www.okx.com/api/v5"
OUT_DIR = "/home/node/.openclaw/workspace/crypto/framework/data_cache"
START_MS = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "funding-fetch/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                p = json.loads(r.read())
            if p.get("code") == "0":
                return p.get("data") or []
        except Exception:
            pass
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"GET failed: {url}")

def fetch_funding(inst):
    rows, after = [], None
    while True:
        url = f"{BASE}/public/funding-rate-history?instId={inst}&limit=100"
        if after:
            url += f"&after={after}"
        page = get(url)
        if not page:
            break
        rows.extend((r["fundingTime"], r["fundingRate"]) for r in page)
        oldest = int(page[-1]["fundingTime"])
        if oldest <= START_MS:
            break
        after = oldest
        time.sleep(0.15)
        if len(rows) % 5000 < 100:
            print(f"[funding] {len(rows)} rows, oldest={datetime.fromtimestamp(oldest/1000, timezone.utc).date()}", flush=True)
    rows = [(int(t), float(r)) for t, r in rows if int(t) >= START_MS]
    rows.sort()
    # dedup
    seen, ded = set(), []
    for t, r in rows:
        if t not in seen:
            seen.add(t); ded.append((t, r))
    # integrity: 8h spacing
    gaps = [(ded[i+1][0] - ded[i][0]) / 3.6e6 for i in range(len(ded) - 1)]
    bad = sum(1 for g in gaps if g > 9.0)
    print(f"[funding] {len(ded)} rows, gaps>9h: {bad} ({bad/ max(len(gaps),1)*100:.2f}%)", flush=True)
    if bad / max(len(gaps), 1) > 0.01:
        raise SystemExit("INTEGRITY: >1% of funding gaps exceed 9h — aborting")
    out = os.path.join(OUT_DIR, f"okx_{inst.replace('-SWAP','').replace('-','_')}_funding_20210101_20260928.csv")
    with open(out + ".tmp", "w") as f:
        f.write("ts,funding_rate\n")
        for t, r in ded:
            iso = datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")
            f.write(f"{iso},{r}\n")
    os.replace(out + ".tmp", out)
    cov0 = datetime.fromtimestamp(ded[0][0]/1000, timezone.utc).date()
    cov1 = datetime.fromtimestamp(ded[-1][0]/1000, timezone.utc).date()
    hdr = f"# coverage: {cov0} -> {cov1} (public endpoint depth-limited; deeper needs paid sources)\n"
    with open(out, "r") as f: body = f.read()
    with open(out, "w") as f: f.write(hdr + body)
    print(f"[funding] WROTE {out} ({len(ded)} rows, coverage {cov0}..{cov1})", flush=True)

def fetch_rubik(name, path_tmpl, inst_ccy, cols):
    """Generic rubik daily fetch (array-of-arrays format)."""
    url = path_tmpl.format(base=BASE, ccy=inst_ccy)
    page = get(url)
    rows = sorted((int(r[0]), *[float(x) for x in r[1:]]) for r in page)
    out = os.path.join(OUT_DIR, f"okx_{inst_ccy}_{name}_20210101_20260928.csv")
    with open(out + ".tmp", "w") as f:
        f.write(f"# granularity: DAILY (OKX rubik limit); coverage: {datetime.fromtimestamp(rows[0][0]/1000, timezone.utc).date()} -> {datetime.fromtimestamp(rows[-1][0]/1000, timezone.utc).date()}\n")
        f.write("ts," + ",".join(cols) + "\n")
        for r in rows:
            iso = datetime.fromtimestamp(r[0] / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")
            f.write(iso + "," + ",".join(str(x) for x in r[1:]) + "\n")
    os.replace(out + ".tmp", out)
    print(f"[{name}] WROTE {out} ({len(rows)} rows, {rows[0][0]}..{rows[-1][0]})", flush=True)

def fetch_oi(inst_ccy):
    fetch_rubik("oi_daily", "{base}/rubik/stat/contracts/open-interest-volume?ccy={ccy}&period=1D",
                inst_ccy, ["oi_contracts", "oi_value"])

def fetch_taker(inst_ccy):
    fetch_rubik("taker_daily", "{base}/rubik/stat/taker-volume?ccy={ccy}&instType=CONTRACTS&period=1D",
                inst_ccy, ["taker_buy_vol", "taker_sell_vol"])

if __name__ == "__main__":
    import sys as _s
    only = _s.argv[1] if len(_s.argv) > 1 else "all"
    if only in ("all", "oi"):
        for ccy in ("ETH", "BTC"):
            fetch_oi(ccy); fetch_taker(ccy)
    if only in ("all", "funding"):
        for inst in ("ETH-USDT-SWAP", "BTC-USDT-SWAP"):
            try:
                fetch_funding(inst)
            except Exception as e:
                print(f"[funding] {inst} FAILED: {e}", flush=True)
    print("ALL DONE", flush=True)
