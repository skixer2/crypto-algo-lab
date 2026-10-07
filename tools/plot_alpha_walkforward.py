#!/usr/bin/env python3
"""Per-window equity graphs for an alpha_*_auto.json study (JP v4 specs,
independent-window adaptation: strategy AND bench normalized to 100 at each
valid-slice start; the valid slice IS the OOS period).

Re-simulates each window with its stored per-window best_params via the same
run_backtest the loop used. No trade markers (run_backtest returns equity only).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from framework.data_loader import load_candles  # noqa: F401  (kept for parity, unused)
from models.wq_alpha_miner import WQAlphaParams
from models.wq_alpha_fast import prepare_fast_context
from tuner.alpha_orchestrator import run_backtest

REPO = os.getcwd()
CACHE_2021 = os.path.join(REPO, "framework", "data_cache")
NORM = 100.0
STRAT_COLOR = "#2ca02c"
BENCH_COLOR = "#4a78b0"


def downsample(xs, ys, n=1200):
    if len(xs) <= n:
        return xs, ys
    step = max(1, len(xs) // n)
    return xs[::step], ys[::step]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="e.g. alpha_030_auto")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    d = json.load(open(os.path.join(REPO, "tuner", "runs", f"{args.run}.json")))
    formula = d.get("formula") or args.run.split("_auto")[0]
    data_span = d.get("data") or {}
    print("data span:", data_span)

    def csv_for(tf):
        if str(data_span.get("start", "")).startswith("2021") or "2021" in str(data_span):
            return os.path.join(CACHE_2021, f"okx_ETH_USDT_{tf}_20210101_20260928.csv")
        return os.path.join(CACHE_2021, f"okx_ETH_USDT_{tf}_20260101_20260928.csv")

    csv_paths = {"15m": csv_for("15m"), "1h": csv_for("1h")}
    bench_full = pd.read_csv(csv_paths["15m"], parse_dates=["timestamp"], index_col="timestamp").sort_index()
    ctx = prepare_fast_context(csv_paths["15m"], csv_paths["1h"], formula)

    wins = d["windows"]
    n = len(wins)
    ncol = min(n, 2)
    nrow = (n + ncol - 1) // ncol
    fig = make_subplots(rows=nrow, cols=ncol,
                        specs=[[{"type": "xy"} for _ in range(ncol)] for _ in range(nrow)],
                        vertical_spacing=0.08, horizontal_spacing=0.06)
    notes = []
    for i, w in enumerate(wins):
        row, col = 1 + i // ncol, 1 + i % ncol
        vs, ve = pd.Timestamp(w["valid_span"][0]), pd.Timestamp(w["valid_span"][1])
        ts, te = pd.Timestamp(w["train_span"][0]), pd.Timestamp(w["train_span"][1])
        p = WQAlphaParams(formula_path=formula, **w["best_params"])
        eq = run_backtest(p, "ETH/USDT", "15m", "1h", csv_paths,
                          ts.isoformat(), ve.isoformat(), ctx=ctx,
                          allow_shorts=bool(d.get("allow_shorts", True)),
                          fee=float(d.get("fee", 0.0008)))
        b = bench_full[(bench_full.index >= vs) & (bench_full.index < ve)]
        if eq is None or b.empty:
            continue
        if hasattr(eq, "equity_curve"):
            eqdf = eq.equity_curve
        else:
            eqdf = eq
        m = eqdf[eqdf["timestamp"] >= vs]
        if len(m) == 0:
            continue
        strat_n = m["equity"] / float(m["equity"].iloc[0]) * NORM
        bench_n = b["close"] / float(b["close"].iloc[0]) * NORM
        sx, sy = downsample([str(t) for t in m["timestamp"]], strat_n.tolist())
        bx, by = downsample([str(t) for t in b.index], bench_n.tolist())
        fig.add_trace(go.Scatter(x=bx, y=by, mode="lines", showlegend=False,
                                 line=dict(color=BENCH_COLOR, width=1.3)), row=row, col=col)
        fig.add_trace(go.Scatter(x=sx, y=sy, mode="lines", showlegend=False,
                                 line=dict(color=STRAT_COLOR, width=1.7)), row=row, col=col)
        vm = w.get("valid", {})
        excess = vm.get("excess_pct", float("nan"))
        ret = vm.get("return_pct", float("nan"))
        benchpct = vm.get("bench_pct", float("nan"))
        notes.append((vs, ret, benchpct, excess))
        fig.add_annotation(xref=f"x{(i+1) if n > 1 else ''}", yref="paper", x=str(vs), y=1.0,
                           showarrow=False, font=dict(size=10),
                           text=f"{vs.date()} | strat {ret:+.1f} vs bench {benchpct:+.1f} | exc {excess:+.1f}",
                           row=row, col=col)
        fig.update_xaxes(type="date", tickfont=dict(size=8), row=row, col=col)
        fig.update_yaxes(tickfont=dict(size=8), row=row, col=col)

    fig.update_layout(
        height=330 * nrow + 60, width=1500, template="plotly_dark",
        title=(f"{formula} — per-window OOS (valid slices), each normalized to 100 at window start | "
               f"blue = ETH B&H, green = strategy | independent windows, no capital carry"),
        margin=dict(l=40, r=20, t=70, b=30),
    )
    out = args.out or os.path.join(REPO, "reports", f"{args.run}_windows.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.write_html(out, include_plotlyjs="cdn")
    print("WROTE", out)


if __name__ == "__main__":
    main()
