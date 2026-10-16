#!/usr/bin/env python3
"""Overnight audit task 3 — knob jitter audit (ETH pool, DIRECT path).

Per pool specialist (priority = v21g weight desc): full-span direct re-sim (orig),
then 2 draws with every numeric frozen param x0.85 / x1.15 (skip bool/None;
thresholds clamped <1; int smoothing rounded >=1). Records orig vs perturbed
full-span total return; sensitivity_pct per draw; flags sign flips / >50% moves.
alpha_056 orig = chained 2021..2026-07 direct chunks from verify_056.json.

Output: tuner/runs/knob_jitter.json (written progressively, resumable).
"""
from __future__ import annotations
import json, os, subprocess, sys

REPO = "/home/node/.openclaw/workspace/crypto"
OUTDIR = f"{REPO}/tuner/runs/v21g_direct"
JOUT = f"{REPO}/tuner/runs/knob_jitter.json"
START, END = "2021-01-01T00:00:00+00:00", "2026-07-28T00:00:00+00:00"
# priority order by v21g weight desc (056 first — orig comes free from task 4 chunks)
POOL = ["alpha_056", "alpha_050", "alpha_027", "alpha_035",
        "alpha_048", "alpha_028", "alpha_024", "alpha_004", "alpha_032"]

def perturb(params: dict, factor: float) -> dict:
    out = {}
    for k, v in params.items():
        if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
            continue  # categorical / None untouched
        nv = v * factor
        if k in ("long_threshold", "short_threshold"):
            nv = min(nv, 0.999)
        if k == "signal_smoothing":
            nv = max(1, int(round(nv)))
        out[k] = nv
    return out

def run_sim(alpha, out, params_json=None):
    cmd = ["nice", "-n", "10", "python3", "/tmp/audit/sim_one.py",
           "--market", "ETH", "--alpha", alpha, "--start", START, "--end", END, "--out", out]
    if params_json:
        cmd += ["--params-json", json.dumps(params_json)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()
    line = tail[-1] if tail else ""
    print(f"  [{alpha}] rc={r.returncode} {line[:140]}", flush=True)
    if r.returncode != 0 or "SIM_OK" not in line:
        return None
    import pandas as pd
    df = pd.read_csv(out)
    return float(df["equity"].iloc[-1] / 10000.0 - 1) * 100.0

def main():
    man = json.load(open(f"{REPO}/data/precompute/manifest.json"))
    store = json.load(open(JOUT)) if os.path.exists(JOUT) else {}
    try:
        v56 = json.load(open(f"{REPO}/tuner/runs/verify_056.json"))
    except Exception:
        v56 = {}
    for alpha in POOL:
        e = store.get(alpha, {})
        base_params = man[alpha]["params"]
        # ---- orig ----
        if "orig_return" not in e:
            if alpha == "alpha_056" and v56.get("status") == "ok":
                e["orig_return"] = round((v56["chained_direct_final_equity"] / 10000.0 - 1) * 100, 3)
                e["orig_source"] = "chained_direct_chunks (task 4)"
            else:
                p = f"{OUTDIR}/ETH_{alpha}_orig.csv.gz"
                ret = run_sim(alpha, p) if not os.path.exists(p) else None
                if ret is None and os.path.exists(p):
                    import pandas as pd
                    ret = float(pd.read_csv(p)["equity"].iloc[-1] / 10000.0 - 1) * 100
                if ret is None:
                    e["error"] = "orig sim failed twice-check log"
                    store[alpha] = e
                    json.dump(store, open(JOUT, "w"), indent=1)
                    continue
                e["orig_return"] = round(ret, 3)
                e["orig_source"] = "direct_full_span"
        # ---- 2 perturbation draws ----
        e.setdefault("perturbed_returns", {})
        e.setdefault("sensitivity_pct", {})
        for f in (0.85, 1.15):
            key = f"x{f}"
            if key in e["perturbed_returns"]:
                continue
            p = f"{OUTDIR}/ETH_{alpha}_j{f}.csv.gz"
            ret = run_sim(alpha, p, perturb(base_params, f)) if not os.path.exists(p) else None
            if ret is None and os.path.exists(p):
                import pandas as pd
                ret = float(pd.read_csv(p)["equity"].iloc[-1] / 10000.0 - 1) * 100
            if ret is None:
                e["error"] = e.get("error", "") + f" | draw {key} failed"
                continue
            e["perturbed_returns"][key] = round(ret, 3)
            e["sensitivity_pct"][key] = round((ret - e["orig_return"]) / max(abs(e["orig_return"]), 1e-9) * 100, 2)
        # ---- flags ----
        flags = []
        for k, r in e.get("perturbed_returns", {}).items():
            if (r > 0) != (e["orig_return"] > 0):
                flags.append(f"SIGN_FLIP at {key_fmt(k)}: orig {e['orig_return']}% -> {r}%")
            if abs(e["sensitivity_pct"].get(k, 0)) > 50:
                flags.append(f">50pct move at {key_fmt(k)}: {e['sensitivity_pct'][k]}%")
        e["flag"] = bool(flags)
        e["flags"] = flags
        store[alpha] = e
        json.dump(store, open(JOUT, "w"), indent=1)
        print(f"[{alpha}] orig {e['orig_return']}% draws {e['perturbed_returns']} flag={e['flag']}", flush=True)
    print("JITTER_PHASE_COMPLETE", flush=True)

def key_fmt(k):
    return k.replace("x0.85", "-15%").replace("x1.15", "+15%")

if __name__ == "__main__":
    main()
