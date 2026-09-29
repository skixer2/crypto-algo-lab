"""Equivalence gate: FastWQAlphaMinerModel vs WQAlphaMinerModel (reference).

The fast path is ONLY trusted if this passes: identical trade lists
(timestamps, directions, prices) and final equity (1e-6 rel) across a
deterministic spread of parameter sets on real cached data.

Usage: python3 tuner/verify_fast_equivalence.py [--window-days 14]
Exit 0 = all cases PASS.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import pandas as pd  # noqa: E402

from framework.runner import RunConfig, run_strategy  # noqa: E402
from models.wq_alpha_fast import prepare_fast_context  # noqa: E402
from models.wq_alpha_miner import WQAlphaMinerModel, WQAlphaParams  # noqa: E402

EXEC_CSV = os.path.join(REPO_ROOT, "framework", "data_cache",
                        "okx_ETH_USDT_15m_20260615_20260928.csv")
BIAS_CSV = os.path.join(REPO_ROOT, "framework", "data_cache",
                        "okx_ETH_USDT_1h_20260615_20260928.csv")

# Deterministic spread: bias on/off, exit thresholds, smoothing spans, stops.
PARAM_SETS = [
    dict(long_threshold=0.45, short_threshold=0.60, signal_smoothing=10,
         atr_stop_mult=2.0, atr_take_mult=3.0, use_bias_filter=False,
         signal_exit_threshold=None),
    dict(long_threshold=0.45, short_threshold=0.60, signal_smoothing=10,
         atr_stop_mult=2.0, atr_take_mult=3.0, use_bias_filter=False,
         signal_exit_threshold=0.3),
    dict(long_threshold=0.55, short_threshold=0.55, signal_smoothing=3,
         atr_stop_mult=1.5, atr_take_mult=2.5, use_bias_filter=True,
         signal_exit_threshold=None),
    dict(long_threshold=0.40, short_threshold=0.80, signal_smoothing=17,
         atr_stop_mult=3.0, atr_take_mult=4.0, use_bias_filter=True,
         signal_exit_threshold=0.4),
    dict(long_threshold=0.70, short_threshold=0.35, signal_smoothing=21,
         atr_stop_mult=2.5, atr_take_mult=1.5, use_bias_filter=True,
         signal_exit_threshold=0.5),
    dict(long_threshold=0.30, short_threshold=0.30, signal_smoothing=5,
         atr_stop_mult=1.0, atr_take_mult=5.0, use_bias_filter=False,
         signal_exit_threshold=0.3),
]


def run_case(params: dict, model_factory, window: tuple) -> tuple:
    p = WQAlphaParams(formula_path="alpha_001", **params)
    model = model_factory(p)
    cfg = RunConfig(
        data_files={"15m": EXEC_CSV, "1h": BIAS_CSV}, execution_tf="15m",
        model=model, initial_capital=10_000.0, fee=0.0008,
        exchange="simulation", allow_shorts=True,
        data_start=window[0], data_end=window[1],
    )
    t0 = time.time()
    res = run_strategy(cfg)
    dt = time.time() - t0
    assert res.success, res.error
    sim = res.equity_curve
    trades = [(str(t.entry_time), str(t.exit_time), t.direction,
               round(t.entry_price, 9), round(t.exit_price, 9),
               t.exit_reason) for t in sim.trades]
    return trades, sim.final_equity, len(sim.equity_curve), dt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=14)
    args = ap.parse_args()

    data_end = pd.Timestamp("2026-09-15", tz="UTC").isoformat()
    data_start = (pd.Timestamp("2026-09-15", tz="UTC")
                  - pd.Timedelta(days=args.window_days)).isoformat()
    window = (data_start, data_end)

    ctx = prepare_fast_context(EXEC_CSV, BIAS_CSV, "alpha_001")
    print(f"context: {len(ctx.exec_df)} exec candles | window {data_start[:10]}..{data_end[:10]}")

    all_pass = True
    tot_ref, tot_fast = 0.0, 0.0
    for i, params in enumerate(PARAM_SETS):
        ref_trades, ref_eq, ref_n, ref_dt = run_case(
            params, lambda p: WQAlphaMinerModel(p, execution_tf="15m", bias_tfs=["1h"]), window)
        fast_trades, fast_eq, fast_n, fast_dt = run_case(
            params, lambda p: __import__("models.wq_alpha_fast", fromlist=["x"]).FastWQAlphaMinerModel(
                p, ctx, execution_tf="15m", bias_tfs=["1h"]), window)
        tot_ref += ref_dt
        tot_fast += fast_dt

        same_trades = ref_trades == fast_trades
        same_eq = abs(ref_eq - fast_eq) / max(abs(ref_eq), 1e-9) < 1e-6
        same_n = ref_n == fast_n
        ok = same_trades and same_eq and same_n
        all_pass &= ok
        status = "PASS" if ok else "FAIL"
        detail = "" if ok else (f" trades ref={len(ref_trades)} fast={len(fast_trades)}"
                                f" eq ref={ref_eq:.4f} fast={fast_eq:.4f}"
                                f" rows {ref_n}/{fast_n}")
        print(f"case {i}: {status} | trades={len(ref_trades)} eq={ref_eq:,.2f} "
              f"| ref {ref_dt:.1f}s vs fast {fast_dt:.1f}s{detail}")
        if not same_trades and len(ref_trades) == len(fast_trades):
            for a, b in zip(ref_trades, fast_trades):
                if a != b:
                    print(f"    first diff: ref={a} fast={b}")
                    break

    speedup = tot_ref / max(tot_fast, 1e-9)
    print(f"\n{'ALL PASS' if all_pass else 'EQUIVALENCE FAILED'} | "
          f"total ref {tot_ref:.1f}s vs fast {tot_fast:.1f}s -> {speedup:.0f}x")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
