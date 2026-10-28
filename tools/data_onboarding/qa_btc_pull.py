#!/usr/bin/env python3
"""Post-pull QA for the BTCUSDT metrics zip cache (Task 1).
Verifies: zip count vs expected day range, spot-open integrity of a sample of
zips, earliest/latest files, and writes qa_btc_pull.md."""
import glob
import os
import zipfile
from datetime import date, timedelta

D = "/home/node/.openclaw/workspace/crypto/framework/data_cache/binance_um_metrics/BTCUSDT"
OUT = "/home/node/.openclaw/workspace/crypto/reports/data_onboarding_20261028/qa_btc_pull.md"

expected_start = date(2020, 9, 1)
today = date.today()
expected_days = (today - expected_start).days + 1  # today's file typically absent (404)

zips = sorted(glob.glob(os.path.join(D, "BTCUSDT-metrics-*.zip")))
names = {os.path.basename(z): z for z in zips}
days = sorted(date.fromisoformat(n[len("BTCUSDT-metrics/"):-len(".zip")] if False else n[len("BTCUSDT-metrics-"):-len(".zip")]) for n in names)

missing = []
d = expected_start
while d < today:
    if f"BTCUSDT-metrics-{d.isoformat()}.zip" not in names:
        missing.append(str(d))
    d += timedelta(days=1)

# integrity: try opening a sample (first 5, last 5, plus any remaining at random stride)
sample = zips[:5] + zips[-5:]
bad = []
for zp in sample:
    try:
        with zipfile.ZipFile(zp) as z:
            with z.open(z.namelist()[0]) as f:
                head = f.read(200).decode()
        if "sum_open_interest" not in head:
            bad.append(zp)
    except Exception:
        bad.append(zp)

L = []
L.append("## BTCUSDT metrics zip cache — QA\n")
L.append(f"- Dir: `framework/data_cache/binance_um_metrics/BTCUSDT/`")
L.append(f"- Zips: {len(zips)} (expected {expected_days - 1} for {expected_start} → {today - timedelta(days=1)}; today's file publishes D+1)")
L.append(f"- Span on disk: {days[0]} → {days[-1]}" if days else "- no files")
L.append(f"- Missing days vs grid: {len(missing)}" + (f": {', '.join(missing[:10])}" + (" …" if len(missing) > 10 else "") if missing else " (none)"))
L.append(f"- Zip integrity sample (10 zips, first/last): {'PASS' if not bad else 'FAIL ' + str(bad)}")
marker = os.path.join(D, "PULL_COMPLETE")
L.append(f"- PULL_COMPLETE marker: {'present: ' + open(marker).read().strip() if os.path.exists(marker) else 'ABSENT'}")
open(OUT, "w").write("\n".join(L) + "\n")
print("\n".join(L))
