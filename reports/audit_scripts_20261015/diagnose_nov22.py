#!/usr/bin/env python3
"""Diagnose the Nov-2022 reconciliation trip (tasks 1-2).

The shipped guard compared contribution_i = sum_t w_i(t)*r_i(t) against the
specialist's FULL-month arithmetic return. With lane-restricted weights that
invariant can legitimately fail when the specialist loses OUTSIDE its lane.
The correct invariant: contribution <= w_max * (lane-restricted month return).
This script computes both views + decomposition vs the portfolio month return.
Writes tuner/runs/v21g_direct/reconciliation_diagnosis.json. Ships nothing.
"""
from __future__ import annotations
import json, os, sys

REPO = "/home/node/.openclaw/workspace/crypto"
sys.path.insert(0, REPO)
os.chdir(REPO)

import numpy as np
import pandas as pd
from tools.regime_grid import regime_array

FEE = 0.0008
LANES = ["confirmed_bearish", "grind_down", "vol_compressed", "expansion"]
V21G = json.load(open(f"{REPO}/tuner/runs/blender_v21g.json"))
DET = V21G["detector"]
WEIGHTED = sorted({a for ln in V21G["weights"].values() for a in ln})
BENCH = {
    "SOL": f"{REPO}/framework/data_cache/okx_SOL_USDT_15m_20210101_20260928.csv",
    "BTC": f"{REPO}/framework/data_cache/okx_BTC_USDT_15m_20210101_20260928.csv",
}
CURVE_DIR = f"{REPO}/tuner/runs/v21g_direct"
S, E = pd.Timestamp("2022-11-01", tz="UTC"), pd.Timestamp("2022-12-01", tz="UTC")

out = {}
for mkt in ("SOL", "BTC"):
    curves, pcs = [], []
    for al in WEIGHTED:
        d = pd.read_csv(f"{CURVE_DIR}/{mkt}_{al}.csv.gz")
        d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True, format="mixed")
        d = d.set_index("timestamp").sort_index()
        curves.append(d["equity"].rename(al)); pcs.append(d["position"].fillna(0.0).rename(al))
    eq = pd.concat(curves, axis=1); P = pd.concat(pcs, axis=1).fillna(0.0)
    rets = eq.pct_change().fillna(0.0); idx = eq.index
    bench = pd.read_csv(BENCH[mkt], parse_dates=["timestamp"], index_col="timestamp").sort_index().loc[idx[0]: idx[-1]]
    det7 = next(m for m in json.load(open(f"{REPO}/data/precompute/regime_grid.json")) if m["i"] == DET)
    codes = regime_array(bench, det7["donchian"], det7["confirm"], det7["vol_enter"],
                         det7["vol_exit"], det7["grind_slope"], det7["grind_confirm"])
    gi = pd.DatetimeIndex(bench.index)
    lane_codes = codes[gi.asi8.searchsorted(idx.asi8)]
    n = len(WEIGHTED)
    W = np.zeros((4, n))
    for li, ln in enumerate(LANES):
        for al, w in V21G["weights"].get(ln, {}).items():
            W[li][WEIGHTED.index(al)] = w
    wl = np.zeros((len(idx), n))
    for li in range(4):
        wl[lane_codes == li] = W[li]
    mask = (idx >= S) & (idx < E)
    rows = {}
    port_arith = float(((wl[mask] * rets.to_numpy()[mask]).sum(axis=1)
                        - FEE * np.abs(np.diff((wl * P.to_numpy()).sum(axis=1), prepend=0.0))[mask]).sum() * 100)
    port_comp = float(np.prod(1.0 + ((wl[mask] * rets.to_numpy()[mask]).sum(axis=1)
                        - FEE * np.abs(np.diff((wl * P.to_numpy()).sum(axis=1), prepend=0.0))[mask])) - 1) * 100
    for j, al in enumerate(WEIGHTED):
        r = rets[al].to_numpy()[mask]; w = wl[mask][:, j]
        contrib = float((w * r).sum() * 100)
        r_full = float(r.sum() * 100)
        inlane = w > 0
        r_lane = float(r[inlane].sum() * 100) if inlane.any() else 0.0
        r_out = float(r[~inlane].sum() * 100)
        wmax = float(w.max())
        ok_lane = contrib <= wmax * r_lane + 1e-6 if r_lane >= 0 else contrib >= wmax * r_lane - 1e-6
        rows[al] = {"contrib_pct": round(contrib, 3), "full_month_arith_pct": round(r_full, 2),
                    "lane_return_pct": round(r_lane, 2), "out_of_lane_pct": round(r_out, 2),
                    "w_max": round(wmax, 4), "lane": [LANES[i] for i in range(4) if W[i][j] > 0],
                    "guard_ok_vs_lane": bool(ok_lane),
                    "guard_trips_vs_full_month": bool((contrib > r_full + 1e-6) if r_full >= 0 else (contrib < r_full - 1e-6))}
    out[mkt] = {"portfolio_month_arith_pct": round(port_arith, 2),
                "portfolio_month_comp_pct": round(port_comp, 2),
                "sum_contributions_pct": round(sum(r["contrib_pct"] for r in rows.values()), 2),
                "specialists": rows}
    json.dump(out, open(f"{CURVE_DIR}/reconciliation_diagnosis.json", "w"), indent=1)
    print(f"[{mkt}] port arith {port_arith:+.2f}% comp {port_comp:+.2f}% sum_contrib {out[mkt]['sum_contributions_pct']:+.2f}%")
    for al, r in rows.items():
        if r["guard_trips_vs_full_month"] or r["contrib_pct"]:
            print(f"  {al} w{r['w_max']:.3f} contrib {r['contrib_pct']:+.2f} vs full {r['full_month_arith_pct']:+.2f} "
                  f"lane {r['lane_return_pct']:+.2f} out {r['out_of_lane_pct']:+.2f} ok_vs_lane={r['guard_ok_vs_lane']}")
print("DIAGNOSIS_DONE")
