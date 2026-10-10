#!/usr/bin/env python3
"""Blender candidate graphs (JP v4 specs, continuous-span variant).

Reconstructs the winning portfolio's 15m equity curve (exact arithmetic over
precomputed specialist curves, weights from the run JSON), then:
  Panel 1: portfolio vs ETH B&H, normalized 100 at first evaluated window
           (2021-04-01), regime shading behind (bear/chop/grind/expansion)
  Panel 2: monthly excess bars (63 months)
  Panel 3: drawdown curves (both series, same axis)
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from tools.blender import FEE, load_specialists, regime_series

REPO = os.getcwd()
RUN = sys.argv[1] if len(sys.argv) > 1 else "blender_v1b"
d = json.load(open(os.path.join(REPO, "tuner", "runs", f"{RUN}.json")))
NORM = 100.0

rets, names = load_specialists()
bench = pd.read_csv(os.path.join(REPO, "framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv"),
                    parse_dates=["timestamp"], index_col="timestamp").sort_index()
bench = bench.loc[rets.index[0]:]
lane = regime_series(bench).loc[rets.index]

W = np.zeros((4, len(names)))
LANES = ["confirmed_bearish", "grind_down", "vol_compressed", "expansion"]
for li, ln in enumerate(LANES):
    for nm, w in d["weights"].get(ln, {}).items():
        W[li][names.index(nm)] = w

lane_arr = lane.to_numpy()
wl = np.zeros((len(rets), len(names)))
for li, ln in enumerate(LANES):
    wl[lane_arr == ln] = W[li]
expo = wl.sum(axis=1)
port_ret = (wl * rets.to_numpy()).sum(axis=1) - FEE * np.abs(np.diff(expo, prepend=0.0))
port = pd.Series(np.cumprod(1 + port_ret), index=rets.index)

anchor = pd.Timestamp("2021-04-01", tz="UTC")
p = port[port.index >= anchor]
b = bench["close"][bench.index >= anchor]
pn = p / float(p.iloc[0]) * NORM
bn = b / float(b.iloc[0]) * NORM

fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                    row_heights=[0.55, 0.25, 0.2])
step = max(1, len(p) // 2500)
fig.add_trace(go.Scatter(x=[str(t) for t in b.index[::step]], y=bn.tolist()[::step],
                         name="ETH B&H", line=dict(color="#4a78b0", width=1.3)), row=1, col=1)
fig.add_trace(go.Scatter(x=[str(t) for t in p.index[::step]], y=pn.tolist()[::step],
                         name=f"{RUN} portfolio", line=dict(color="#2ca02c", width=1.8)), row=1, col=1)

# regime shading (segments)
reg = lane[lane.index >= anchor]
spans = []
for i, ts in enumerate(reg.index):
    r = reg.iloc[i]
    if spans and spans[-1][0] == r and spans[-1][2] == i - 1:
        spans[-1][2] = i
    else:
        spans.append([r, i, i])
COLORS = {"confirmed_bearish": "rgba(200,60,60,0.10)", "grind_down": "rgba(160,160,160,0.10)",
          "vol_compressed": "rgba(220,180,40,0.10)", "expansion": "rgba(60,180,90,0.08)"}
for r, a, bb in spans:
    if bb - a > 96:  # only shade stretches > 1 day
        fig.add_vrect(x0=str(reg.index[a]), x1=str(reg.index[bb]), fillcolor=COLORS[r],
                      line_width=0, row=1, col=1)

ws = d["windows"]
fig.add_trace(go.Bar(x=[w["month"] for w in ws], y=[w["excess"] for w in ws],
                     name="monthly excess", marker_color=np.where(
                         np.array([w["excess"] for w in ws]) >= 0, "#2ca02c", "#c0504d"),
                     opacity=0.85), row=2, col=1)

ddp = (pn / pn.cummax() - 1) * 100
ddb = (bn / bn.cummax() - 1) * 100
fig.add_trace(go.Scatter(x=[str(t) for t in p.index[::step]], y=ddp.tolist()[::step],
                         name="portfolio DD%", line=dict(color="#2ca02c", width=1.2)), row=3, col=1)
fig.add_trace(go.Scatter(x=[str(t) for t in b.index[::step]], y=ddb.tolist()[::step],
                         name="B&H DD%", line=dict(color="#4a78b0", width=1.2)), row=3, col=1)

det = d["details"]
fig.update_layout(
    template="plotly_dark", width=1600, height=950,
    title=(f"{RUN} — reconstructed portfolio, 2021-04 → 2026-07 (sealed span, continuous, both @100 at anchor) | "
           f"mean excess {det['mean_excess']:+.1f}%/mo · t {det['t']:+.2f} · maxDD {det['run_mdd']:.1f}% · "
           f"out {det['time_out']:.0f}% · {det['active']} specialists<br>"
           f"<span style='font-size:11px'>shading: red=confirmed_bearish · yellow=chop · gray=grind · green=expansion | "
           f"weights frozen from search; curve = exact arithmetic over precomputed specialist curves (incl. their fees + turnover cost)</span>"),
    legend=dict(orientation="h", y=1.05), margin=dict(l=50, r=20, t=90, b=30),
)
fig.update_xaxes(type="date", row=1, col=1)
fig.update_yaxes(ticksuffix="", row=1, col=1)
fig.update_xaxes(type="category", row=2, col=1, tickfont=dict(size=7), tickangle=45)
fig.update_yaxes(title="excess %", row=2, col=1)
fig.update_yaxes(title="DD %", row=3, col=1)
out = os.path.join(REPO, "reports", f"{RUN}_portfolio.html")
fig.write_html(out, include_plotlyjs="cdn")
print("WROTE", out)
