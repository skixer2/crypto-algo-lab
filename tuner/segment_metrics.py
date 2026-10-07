#!/usr/bin/env python3
"""Segment metrics (JP directive 2026-10-07): judge WITHIN-window path quality,
not just window-aggregate return.

Decomposition: each OOS window splits at the benchmark's trough:
  DOWN-LEG  start -> trough   (shield or short-earn here)
  UP-LEG    trough -> end     (participate here — capture fraction rewards
                              BUYING AT RECOVERY START: full capture requires
                              being in from the leg's beginning)

Core quantities per window:
  down_shield_pct   = strat return during down-leg (>= 0.2*bench means shield)
  down_excess_pct   = strat - bench over the down-leg
  up_capture_ratio  = strat up-leg return / bench up-leg return  (bench > 0)
                      ~1.0 = rode the recovery from its start
                      ~0.5 = entered halfway; <0 = fought the recovery
  v_shape           = bench dropped then rose (both legs > 3%) — the
                      drop-recovery windows JP's rule targets
Reusable: gates v3 sub-rules + blend-optimizer fitness terms.
"""
from __future__ import annotations

import pandas as pd


def segment_metrics(eq: pd.DataFrame, bench: pd.DataFrame, win_start, win_end) -> dict:
    """eq: DataFrame(timestamp, equity); bench: close-indexed frame, sliced later."""
    vs = pd.Timestamp(win_start)
    ve = pd.Timestamp(win_end)
    m = eq[(eq["timestamp"] >= vs) & (eq["timestamp"] < ve)]
    b = bench[(bench.index >= vs) & (bench.index < ve)]
    if len(m) < 2 or len(b) < 2:
        return {"ok": False}

    trough_i = b["close"].idxmin()
    # boundary equities: last value at-or-before each boundary
    def eq_at(ts):
        sub = m[m["timestamp"] <= ts]
        return float(sub["equity"].iloc[-1]) if len(sub) else float(m["equity"].iloc[0])

    e0, e_t, e1 = float(m["equity"].iloc[0]), eq_at(trough_i), float(m["equity"].iloc[-1])
    c0 = float(b["close"].iloc[0]); c_t = float(b.loc[trough_i, "close"]); c1 = float(b["close"].iloc[-1])

    down_b = (c_t / c0 - 1) * 100
    up_b = (c1 / c_t - 1) * 100
    down_s = (e_t / e0 - 1) * 100
    up_s = (e1 / e_t - 1) * 100
    v_shape = down_b <= -3.0 and up_b >= 3.0
    return {
        "ok": True,
        "trough_ts": str(trough_i),
        "bench_down_pct": round(down_b, 2), "bench_up_pct": round(up_b, 2),
        "strat_down_pct": round(down_s, 2), "strat_up_pct": round(up_s, 2),
        "down_excess_pct": round(down_s - down_b, 2),
        "up_capture_ratio": round(up_s / up_b, 3) if up_b > 3.0 else None,
        "v_shape": v_shape,
    }


def demo_alpha(run_label: str, formula: str):
    import json, os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from models.wq_alpha_miner import WQAlphaParams
    from models.wq_alpha_fast import prepare_fast_context
    from tuner.alpha_orchestrator import run_backtest

    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = json.load(open(os.path.join(REPO, "tuner", "runs", f"{run_label}.json")))
    csv = {tf: os.path.join(REPO, "framework", "data_cache", f"okx_ETH_USDT_{tf}_20210101_20260928.csv")
           for tf in ("15m", "1h")}
    bench = pd.read_csv(csv["15m"], parse_dates=["timestamp"], index_col="timestamp").sort_index()
    ctx = prepare_fast_context(csv["15m"], csv["1h"], formula)
    print(f"\n=== {run_label} — segment metrics ===")
    print(f"{'window':22s} {'bench dn/up':>14s} {'strat dn/up':>14s} {'dn excess':>9s} {'up capture':>10s} v")
    for w in d["windows"]:
        p = WQAlphaParams(formula_path=formula, **w["best_params"])
        eq = run_backtest(p, "ETH/USDT", "15m", "1h", csv,
                          w["train_span"][0], w["valid_span"][1], ctx=ctx,
                          allow_shorts=bool(d.get("allow_shorts", True)), fee=0.0008)
        s = segment_metrics(eq, bench, w["valid_span"][0], w["valid_span"][1])
        if not s.get("ok"):
            continue
        cap = f"{s['up_capture_ratio']:+.2f}" if s["up_capture_ratio"] is not None else "  n/a"
        print(f"{w['valid_span'][0][:10]}→{w['valid_span'][1][:10]:<11s} "
              f"{s['bench_down_pct']:+6.1f}/{s['bench_up_pct']:+6.1f}  "
              f"{s['strat_down_pct']:+6.1f}/{s['strat_up_pct']:+6.1f}  "
              f"{s['down_excess_pct']:+8.1f}  {cap:>9s}  {'V' if s['v_shape'] else '-'}")


if __name__ == "__main__":
    import sys
    demo_alpha(sys.argv[1] if len(sys.argv) > 1 else "alpha_032_auto",
               sys.argv[2] if len(sys.argv) > 2 else "alpha_032")


def time_out_pct(eq: pd.DataFrame, win_start, win_end) -> float:
    """Fraction of window bars spent FLAT (JP out-penalty, 2026-10-07).
    Heuristic: in-position bars carry MTM movement; flat bars do not."""
    import numpy as np
    m = eq[(eq["timestamp"] >= pd.Timestamp(win_start)) & (eq["timestamp"] < pd.Timestamp(win_end))]
    if len(m) < 2:
        return float("nan")
    moved = m["equity"].diff().abs() > 1e-9
    return float((~moved).mean() * 100)


def out_penalty_pct(time_out: float) -> float:
    """Excess points of penalty: free below 20% out, then superlinear.
    30% out -> 1.0 pt, 40% -> 2.8, 60% -> 8.0 (JP-approved curve)."""
    if time_out != time_out or time_out <= 20.0:
        return 0.0
    return ((time_out - 20.0) / 10.0) ** 1.5
