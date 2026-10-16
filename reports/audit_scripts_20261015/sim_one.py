#!/usr/bin/env python3
"""Overnight audit — single direct-path (ctx=None) specialist sim.

Usage: sim_one.py --market SOL --alpha alpha_004 --start ... --end ... --out x.csv.gz
Optional: --params-json '{"long_threshold":...}' overrides manifest params (knob jitter).
Never modifies tools/ tuner/ framework/ code. Read-only on repo except --out.
"""
from __future__ import annotations
import argparse, json, os, sys, time

REPO = "/home/node/.openclaw/workspace/crypto"
sys.path.insert(0, REPO)
os.chdir(REPO)

import pandas as pd
from models.wq_alpha_miner import WQAlphaParams
from tuner.alpha_orchestrator import run_backtest

CSV = {
    "ETH": {"15m": f"{REPO}/framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv",
            "1h":  f"{REPO}/framework/data_cache/okx_ETH_USDT_1h_20210101_20260928.csv"},
    "BTC": {"15m": f"{REPO}/framework/data_cache/okx_BTC_USDT_15m_20210101_20260928.csv",
            "1h":  f"{REPO}/framework/data_cache/okx_BTC_USDT_1h_20210101_20260928.csv"},
    "SOL": {"15m": f"{REPO}/framework/data_cache/okx_SOL_USDT_15m_20210101_20260928.csv",
            "1h":  f"{REPO}/framework/data_cache/okx_SOL_USDT_1h_20210101_20260928.csv"},
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["ETH", "BTC", "SOL"])
    ap.add_argument("--alpha", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--params-json", default=None)
    ap.add_argument("--capital", type=float, default=10_000.0)  # recorded only; run_backtest fixes 10k
    a = ap.parse_args()

    man = json.load(open(f"{REPO}/data/precompute/manifest.json"))
    params = dict(man[a.alpha]["params"])
    overrides = json.loads(a.params_json) if a.params_json else None
    if overrides:
        params.update(overrides)

    p = WQAlphaParams(formula_path=a.alpha, **params)
    t0 = time.time()
    eq = run_backtest(p, f"{a.market}/USDT", "15m", "1h", CSV[a.market],
                      a.start, a.end, ctx=None, allow_shorts=True, fee=0.0008)
    dt = time.time() - t0
    if eq is None:
        print(f"SIM_FAILED {a.market} {a.alpha} after {dt:.0f}s", flush=True)
        sys.exit(2)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    tmp = a.out + ".tmp"
    eq_out = eq[["timestamp", "equity"] + (["position"] if "position" in eq.columns else [])].copy()
    if "position" in eq_out.columns:
        eq_out["position"] = eq_out["position"].map(
            lambda v: {"long": 1.0, "short": -1.0}.get(v, 0.0) if isinstance(v, str)
            else (0.0 if v is None else float(v)))
    eq_out.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, a.out)
    fin = float(eq["equity"].iloc[-1])
    print(f"SIM_OK {a.market} {a.alpha} rows={len(eq)} final_equity={fin:.2f} "
          f"ret={(fin/10000-1)*100:.2f}% sec={dt:.0f} -> {a.out}", flush=True)

if __name__ == "__main__":
    main()
