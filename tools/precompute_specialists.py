#!/usr/bin/env python3
"""Precompute specialist equity curves for the blender (JP $0 plan, 2026-10-09).

For each pool formula: freeze params at its BEST window's config (demonstrated
skill), sim the FULL sealed span 2021-01-01 -> 2026-07-28 once via the engine,
store the 15m equity curve (csv.gz) + manifest. The blender then evaluates
candidates as exact piecewise arithmetic over these curves — no engine re-sims.

Output: data/precompute/<formula>.csv.gz + manifest.json (params, spans, fees).
Resumable: skips formulas whose outputs already exist.
"""
from __future__ import annotations

import glob
import gzip
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from models.wq_alpha_miner import WQAlphaParams
from models.wq_alpha_fast import prepare_fast_context
from tuner.alpha_orchestrator import run_backtest

POOL = ["alpha_004", "alpha_008", "alpha_024", "alpha_027", "alpha_028",
        "alpha_029", "alpha_032", "alpha_035", "alpha_039", "alpha_040"]
START, END = "2021-01-01T00:00:00+00:00", "2026-07-28T00:00:00+00:00"
CSV = {tf: os.path.join("framework", "data_cache", f"okx_ETH_USDT_{tf}_20210101_20260928.csv")
       for tf in ("15m", "1h")}
OUT_DIR = os.path.join("data", "precompute")

os.makedirs(OUT_DIR, exist_ok=True)


def best_params_for(formula: str):
    """Params from the formula's best-excess window across its run JSONs."""
    best = None
    for path in sorted(glob.glob(f"tuner/runs/{formula}*.json")):
        try:
            d = json.load(open(path))
        except Exception:
            continue
        for w in d.get("windows", []):
            v = (w.get("valid") or {}).get("excess_pct")
            if v is None or not w.get("best_params"):
                continue
            if best is None or v > best[0]:
                best = (v, w["best_params"], os.path.basename(path))
    return best


def main():
    ctx_cache = {}
    manifest = {}
    for f in POOL:
        out = os.path.join(OUT_DIR, f"{f}.csv.gz")
        if os.path.exists(out):
            print(f"[{f}] exists, skip", flush=True)
            continue
        bp = best_params_for(f)
        if bp is None:
            print(f"[{f}] NO stored params — SKIP (needs manual config)", flush=True)
            continue
        exc, params, src = bp
        if f not in ctx_cache:
            ctx_cache[f] = prepare_fast_context(CSV["15m"], CSV["1h"], f)
        t0 = time.time()
        p = WQAlphaParams(formula_path=f, **params)
        eq = run_backtest(p, "ETH/USDT", "15m", "1h", CSV, START, END,
                          ctx=ctx_cache[f], allow_shorts=True, fee=0.0008)
        if eq is None:
            print(f"[{f}] sim FAILED", flush=True)
            continue
        tmp = out + ".tmp"
        with gzip.open(tmp, "wt") as fh:
            fh.write("timestamp,equity\n")
            for row in eq.itertuples(index=False):
                fh.write(f"{row.timestamp},{row.equity:.6f}\n")
        os.replace(tmp, out)
        manifest[f] = {"src_run": src, "best_window_excess": exc,
                       "params": params, "span": [START, END],
                       "rows": len(eq), "sec": round(time.time() - t0, 1),
                       "final_equity": float(eq["equity"].iloc[-1])}
        json.dump(manifest, open(os.path.join(OUT_DIR, "manifest.json"), "w"), indent=1)
        print(f"[{f}] DONE {len(eq)} rows in {time.time()-t0:.0f}s "
              f"(params from {src}, window excess {exc:+.1f})", flush=True)
    print("PRECOMPUTE COMPLETE", flush=True)


if __name__ == "__main__":
    main()
