#!/usr/bin/env python3
"""Overnight audit task 4 — alpha_056 direct-path full-span verification, chunked.

Five yearly chunks (2021, 2022, 2023, 2024, 2025-01..2026-07-28). Chain initial
capital = prior chunk final. Compare each chunk's growth factor vs the stored
fast-context curve (data/precompute/alpha_056.csv.gz) over the same window.
Output: tuner/runs/verify_056.json
"""
from __future__ import annotations
import json, os, sys
import pandas as pd

REPO = "/home/node/.openclaw/workspace/crypto"
CHUNK_DIR = f"{REPO}/tuner/runs/v21g_direct/chunks_056"
CHUNKS = [
    ("2021", "2021-01-01T00:00:00+00:00", "2022-01-01T00:00:00+00:00"),
    ("2022", "2022-01-01T00:00:00+00:00", "2023-01-01T00:00:00+00:00"),
    ("2023", "2023-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00"),
    ("2024", "2024-01-01T00:00:00+00:00", "2025-01-01T00:00:00+00:00"),
    ("2025H1", "2025-01-01T00:00:00+00:00", "2026-07-28T00:00:00+00:00"),
]

def growth_of_curve(path, s, e):
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="mixed")
    d = df.set_index("timestamp").sort_index()
    w = d[(d.index >= pd.Timestamp(s)) & (d.index < pd.Timestamp(e))]
    if len(w) < 2:
        return None
    return float(w["equity"].iloc[-1] / w["equity"].iloc[0])

def main():
    stored = f"{REPO}/data/precompute/alpha_056.csv.gz"
    rows, missing = [], []
    for name, s, e in CHUNKS:
        p = f"{CHUNK_DIR}/ETH_alpha_056_{name}.csv.gz"
        if not os.path.exists(p):
            missing.append(name)
            continue
        g_direct = growth_of_curve(p, s, e)
        g_stored = growth_of_curve(stored, s, e)
        rel = abs(g_direct - g_stored) / abs(g_stored) if g_direct and g_stored else None
        rows.append({"chunk": name, "window": [s, e], "direct_growth": round(g_direct, 6),
                     "stored_growth": round(g_stored, 6), "rel_divergence_pct": round(rel * 100, 4)})
    if missing:
        json.dump({"status": "incomplete", "missing_chunks": missing, "chunks": rows},
                  open(f"{REPO}/tuner/runs/verify_056.json", "w"), indent=1)
        print(f"VERIFY056 incomplete — missing {missing}")
        sys.exit(1)
    chain_d = chain_s = 10000.0
    for r in rows:
        chain_d *= r["direct_growth"]
        chain_s *= r["stored_growth"]
    max_rel = max(r["rel_divergence_pct"] for r in rows)
    out = {"status": "ok", "chunks": rows,
           "chained_direct_final_equity": round(chain_d, 2),
           "chained_stored_final_equity": round(chain_s, 2),
           "chained_rel_divergence_pct": round(abs(chain_d - chain_s) / chain_s * 100, 4),
           "max_per_chunk_rel_divergence_pct": round(max_rel, 4)}
    json.dump(out, open(f"{REPO}/tuner/runs/verify_056.json", "w"), indent=1)
    print(f"VERIFY056_OK max_chunk_div={max_rel:.4f}% chained {chain_d:.0f} vs {chain_s:.0f} "
          f"({out['chained_rel_divergence_pct']}%)")

if __name__ == "__main__":
    main()
