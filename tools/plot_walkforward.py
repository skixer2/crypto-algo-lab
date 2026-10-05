#!/usr/bin/env python3
"""Walk-forward window graphs per JP's Telegram v4 specs, adapted for
INDEPENDENT windows (JP 2026-10-05): every test window re-simulated with its
frozen params; strategy AND benchmark each normalized to 100 at window start.
No cumulative equity across windows (skill rule explicitly overridden).

Specs applied: same Y-axis both series @100 anchor; trade markers (green
entry / red exit, opacity 0.35) on every panel; ISO strings + type='date';
shapes-list (no add_vline loops); include_plotlyjs='cdn'; downsampling.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from models.composite_router import CompositeRouterModel, RouterParams

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXEC = os.path.join(REPO, "framework", "data_cache", "okx_ETH_USDT_15m_20210101_20260928.csv")
BIAS = os.path.join(REPO, "framework", "data_cache", "okx_ETH_USDT_1h_20210101_20260928.csv")
PAD_DAYS = 7
RUN_COLORS = ["#2ca02c", "#ff7f0e", "#9467bd"]  # v1 green, v2 orange, ...
BENCH_COLOR = "#4a78b0"
NORM = 100.0


def resim_window(bp: dict, start, end):
    """Frozen-params re-sim of one test window -> (eq_df, bench_df, trades)."""
    from framework.runner import RunConfig, run_strategy

    p = RouterParams(
        donchian_bars=bp["donchian_bars"], confirm_bars=bp["confirm_bars"],
        grind_slope_bars=bp.get("grind_slope_bars", 96),
        vol_compression=bp["vol_compression"],
        meltup_threshold=bp["meltup_threshold"], chop_threshold=bp["chop_threshold"],
        down_threshold=bp["down_threshold"], signal_smoothing=bp["signal_smoothing"],
        atr_stop_mult=bp["atr_stop_mult"], atr_take_mult=bp["atr_take_mult"],
    )
    pad = (start - timedelta(days=PAD_DAYS)).isoformat()
    end_i = (end - timedelta(minutes=1)).isoformat()
    m = CompositeRouterModel(p, execution_tf="15m", bias_tfs=["1h"])
    m.bind_context(EXEC)
    cfg = RunConfig(data_files={"15m": EXEC, "1h": BIAS}, execution_tf="15m",
                    model=m, initial_capital=10_000.0, fee=0.0008,
                    exchange="simulation", allow_shorts=True,
                    data_start=pad, data_end=end_i)
    res = run_strategy(cfg)
    sim = res.equity_curve
    eq = sim.equity_curve
    eq = eq[eq["timestamp"] >= pd.Timestamp(start)].reset_index(drop=True)
    trades = [(t.entry_time, t.exit_time, t.direction, t.pnl_pct) for t in sim.trades]
    return eq, trades


def downsample(xs, ys, n=1200):
    if len(xs) <= n:
        return xs, ys
    step = max(1, len(xs) // n)
    return xs[::step], ys[::step]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True, help="comma list of tuner/runs labels")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    labels = args.runs.split(",")
    runs = []
    for lb in labels:
        with open(os.path.join(REPO, "tuner", "runs", f"{lb}.json")) as f:
            runs.append((lb, json.load(f)))

    bench_full = pd.read_csv(EXEC, parse_dates=["timestamp"], index_col="timestamp").sort_index()
    n_win = len(runs[0][1]["results"])
    ncol = 3
    nrow = (n_win + ncol - 1) // ncol  # window grid + summary row
    fig = make_subplots(
        rows=nrow + 1, cols=ncol,
        specs=[[{"colspan": ncol, "rowspan": 1} if c == 0 else None for c in range(ncol)]] +
              [[{"type": "xy"} for _ in range(ncol)] for _ in range(nrow)],
        row_heights=[0.28] + [0.72 / nrow] * nrow,
        vertical_spacing=0.03,
    )

    shapes, summary_data = [], []
    for w_i, r in enumerate(runs[0][1]["results"]):
        row = 2 + w_i // ncol
        col = 1 + w_i % ncol
        s = pd.Timestamp(r["test"][0], tz="UTC")
        e = pd.Timestamp(r["test"][1], tz="UTC")
        b = bench_full[(bench_full.index >= s) & (bench_full.index < e)]
        if b.empty:
            continue
        bench_n = b["close"] / float(b["close"].iloc[0]) * NORM
        bx, by = downsample([str(t) for t in b.index], bench_n.tolist())
        fig.add_trace(go.Scatter(x=bx, y=by, mode="lines", showlegend=False,
                                 line=dict(color=BENCH_COLOR, width=1.3),
                                 hovertemplate="bench %{y:.1f}<extra></extra>"),
                      row=row, col=col)
        for run_i, (lb, run) in enumerate(runs):
            r2 = run["results"][w_i]
            eq, trades = resim_window(r2["best_params"], s, e)
            eq_n = eq["equity"] / float(eq["equity"].iloc[0]) * NORM
            ex, ey = downsample([str(t) for t in eq["timestamp"]], eq_n.tolist())
            fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", showlegend=False,
                                     line=dict(color=RUN_COLORS[run_i], width=1.7),
                                     hovertemplate=f"{lb} %{{y:.1f}}<extra></extra>"),
                          row=row, col=col)
            for et, xt, d, pnl in trades:
                for (ts, c) in ((et, "green"), (xt, "red")):
                    if ts < s:
                        continue  # pad-period trade, not visible in this window
                    shapes.append(dict(type="line", x0=str(ts), x1=str(ts), y0=0, y1=1,
                                       xref=f"x{w_i + 2}", yref=f"y{w_i + 2} domain",
                                       line=dict(color=c, width=0.7), opacity=0.35))
        shapes.append(dict(type="line", x0=str(b.index[0]), x1=str(b.index[-1]),
                           y0=NORM, y1=NORM, xref=f"x{w_i + 2}", yref=f"y{w_i + 2}",
                           line=dict(color="#888", width=0.6, dash="dot")))
        excess_txt = " ".join(f"{lb.split('_')[1]}:{r2['excess']:+.0f}" for lb, run in runs
                              for r2 in [run["results"][w_i]])
        fig.add_annotation(xref=f"x{w_i + 2}", yref=f"y{w_i + 2} domain", x=str(b.index[0]),
                           y=1.06, showarrow=False, font=dict(size=9),
                           text=f"{s.date()} {excess_txt}")
        fig.update_xaxes(type="date", row=row, col=col, tickfont=dict(size=7))
        fig.update_yaxes(ticksuffix="", tickfont=dict(size=7), row=row, col=col)

    # summary bars
    xs = [f"{r['test'][0][2:]}" for r in runs[0][1]["results"]]
    for run_i, (lb, run) in enumerate(runs):
        vals = [r["excess"] for r in run["results"]]
        summary_data.append((lb, vals))
        fig.add_trace(go.Bar(x=xs, y=vals, name=lb, marker_color=RUN_COLORS[run_i],
                             opacity=0.85), row=1, col=1)
    m0 = runs[0][1]["mean_test_excess"]
    fig.add_annotation(xref="paper", x=0.01, y=0.985, showarrow=False,
                       yanchor="top", align="left", font=dict(size=11),
                       text=" | ".join(f"<b>{lb}</b>: mean {d['mean_test_excess']:+.1f}%, "
                                       f"{d['windows_positive']}/{d['windows']} positive"
                                       for lb, d in runs) +
                            f"<br><span style='font-size:9px'>ETH/USDT bench = blue; strategy = "
                            f"{'/'.join(RUN_COLORS[:len(runs)])}; each window normalized to 100 "
                            f"at its own start (independent windows, no capital carry)</span>",
                       row=1, col=1)
    fig.update_yaxes(title="excess vs B&H (%)", row=1, col=1)
    fig.update_xaxes(type="category", row=1, col=1)

    fig.update_layout(
        height=260 * (nrow + 1), width=1500,
        template="plotly_dark",
        title=f"CompositeRouter walk-forward — {' vs '.join(lb for lb, _ in runs)} (frozen per-window params, test slices only)",
        margin=dict(l=40, r=20, t=90, b=30),
        bargap=0.25,
    )
    fig.update_layout(shapes=shapes)

    out = args.out or os.path.join(REPO, "reports", f"{'_vs_'.join(lb for lb, _ in runs)}_windows.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"WROTE {out}")


if __name__ == "__main__":
    main()
