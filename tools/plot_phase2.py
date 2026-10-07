#!/usr/bin/env python3
"""Phase-2 regime-stratified scoreboard graph (from salvaged summary JSON).

One panel: x = 16 windows (chronological, regime-tinted zones), grouped bars =
per-window OOS excess for each formula; regime means annotated per formula.
Equity paths unavailable (params lost to RUNS_DIR bug) — bars are the honest
representation of what the study measured.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

import plotly.graph_objects as go

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLORS = {"alpha_029": "#2ca02c", "alpha_027": "#ff7f0e", "alpha_028": "#9467bd"}
REGIME_BG = {"bear": "rgba(200,60,60,0.10)", "bull": "rgba(60,180,90,0.10)", "neutral": "rgba(160,160,160,0.08)"}

d = json.load(open(os.path.join(REPO, "tuner", "runs", "phase2_summary_salvaged.json")))
formulas = list(d["formulas"].keys())
# chronological union of windows
allw = sorted({(w["valid"], w["regime"]) for f in formulas for w in d["formulas"][f]})
xs = [f"{v[:7]}<br>{r}" for v, r in allw]

fig = go.Figure()
for f in formulas:
    by_valid = {w["valid"]: w["excess_pct"] for w in d["formulas"][f]}
    fig.add_trace(go.Bar(
        x=xs, y=[by_valid.get(v, None) for v, _ in allw], name=f,
        marker_color=COLORS[f], opacity=0.88, width=0.26,
        offset=[-0.28, 0, 0.28][formulas.index(f)],
    ))

# regime zones
spans = []
for i, (v, r) in enumerate(allw):
    if spans and spans[-1][0] == r and spans[-1][2] == i - 1:
        spans[-1][2] = i
    else:
        spans.append([r, i, i])
for r, a, b in spans:
    fig.add_vrect(x0=a - 0.5, x1=b + 0.5, fillcolor=REGIME_BG[r], line_width=0)

# regime means per formula
means = defaultdict(dict)
for f in formulas:
    rows = d["formulas"][f]
    for reg in ("bear", "bull", "neutral"):
        sub = [w["excess_pct"] for w in rows if w["regime"] == reg]
        means[f][reg] = sum(sub) / len(sub) if sub else float("nan")
tbl = " &nbsp;|&nbsp; ".join(
    f"<b>{f}</b>: bear {means[f]['bear']:+.1f} · bull {means[f]['bull']:+.1f} · neutral {means[f]['neutral']:+.1f}"
    for f in formulas)
fig.add_annotation(xref="paper", x=0.5, y=-0.16, showarrow=False, font=dict(size=11),
                   text="mean OOS excess % per regime — " + tbl)

fig.update_layout(
    template="plotly_dark", width=1500, height=640, barmode="overlay",
    title=("Phase-2 regime-stratified walk-forward — 16 windows over 2021–2026 (8 bear / 5 bull / 3 neutral) | "
           "Optuna 40 trials on train inside each episode, honest OOS on valid | bars = excess vs ETH B&H"),
    yaxis_title="OOS excess vs B&H (%)",
    xaxis_title="valid window (regime)",
    legend=dict(orientation="h", y=1.06),
    margin=dict(l=50, r=20, t=80, b=110),
)
out = os.path.join(REPO, "reports", "phase2_specialists.html")
os.makedirs(os.path.dirname(out), exist_ok=True)
fig.write_html(out, include_plotlyjs="cdn")
print("WROTE", out)
