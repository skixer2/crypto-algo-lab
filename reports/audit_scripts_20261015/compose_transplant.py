#!/usr/bin/env python3
"""Overnight audit tasks 1+2 — compose v21g transplant portfolio from DIRECT-path
specialist curves, monthly grid stats, FTX strat, worst months, per-specialist
reconciliation (Nov-2022), 3-panel plotly-dark HTML.

Usage: compose_transplant.py --market SOL
Outputs: tuner/runs/v21g_direct/{MKT}_summary.json + reports/v21g_{MKT}_direct.html
Read-only elsewhere. Runs the RECONCILIATION GUARD: a specialist's Nov-2022
arithmetic contribution may never exceed its own month arithmetic return
(weight <= 1) — on violation, writes INCONSISTENCY_{MKT}.json and exits 3.
"""
from __future__ import annotations
import argparse, json, os, sys

REPO = "/home/node/.openclaw/workspace/crypto"
sys.path.insert(0, REPO)
os.chdir(REPO)

import numpy as np
import pandas as pd

from tools.regime_grid import regime_array

FEE = 0.0008
LANES = ["confirmed_bearish", "grind_down", "vol_compressed", "expansion"]
V21G = json.load(open(f"{REPO}/tuner/runs/blender_v21g.json"))
DET = V21G["detector"]

BENCH = {
    "SOL": f"{REPO}/framework/data_cache/okx_SOL_USDT_15m_20210101_20260928.csv",
    "BTC": f"{REPO}/framework/data_cache/okx_BTC_USDT_15m_20210101_20260928.csv",
    "ETH": f"{REPO}/framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv",
}
CURVE_DIR = f"{REPO}/tuner/runs/v21g_direct"
WEIGHTED = sorted({a for ln in V21G["weights"].values() for a in ln})


def load_curve(mkt: str, alpha: str) -> pd.DataFrame:
    df = pd.read_csv(f"{CURVE_DIR}/{mkt}_{alpha}.csv.gz")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="mixed")
    return df.set_index("timestamp").sort_index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["SOL", "BTC"])
    a = ap.parse_args()
    mkt = a.market

    curves, pos_cols = [], []
    for al in WEIGHTED:
        d = load_curve(mkt, al)
        curves.append(d["equity"].rename(al))
        pos_cols.append(d["position"].fillna(0.0).rename(al))
    eq = pd.concat(curves, axis=1)          # timestamp-aligned join (never positional)
    P = pd.concat(pos_cols, axis=1).fillna(0.0)
    rets = eq.pct_change().fillna(0.0)
    idx = eq.index

    bench = pd.read_csv(BENCH[mkt], parse_dates=["timestamp"], index_col="timestamp").sort_index()
    bench = bench.loc[idx[0]: idx[-1]]

    det7 = next(m for m in json.load(open(f"{REPO}/data/precompute/regime_grid.json")) if m["i"] == DET)
    codes = regime_array(bench, det7["donchian"], det7["confirm"],
                         det7["vol_enter"], det7["vol_exit"],
                         det7["grind_slope"], det7["grind_confirm"])
    gi = pd.DatetimeIndex(bench.index)
    pos_in_full = gi.asi8.searchsorted(idx.asi8)   # timestamp searchsorted, never positional
    assert (gi[pos_in_full] == idx).all(), "grid/bench timestamp misalignment"
    lane_codes = codes[pos_in_full]

    n = len(WEIGHTED)
    W = np.zeros((4, n))
    for li, ln in enumerate(LANES):
        for al, w in V21G["weights"].get(ln, {}).items():
            W[li][WEIGHTED.index(al)] = w
    wl = np.zeros((len(idx), n))
    for li in range(4):
        wl[lane_codes == li] = W[li]
    lane_names = np.array(LANES)[lane_codes]

    net_expo = (wl * P.to_numpy()).sum(axis=1)
    port_ret = (wl * rets.to_numpy()).sum(axis=1) - FEE * np.abs(np.diff(net_expo, prepend=0.0))
    port_eq = pd.Series(np.cumprod(1.0 + port_ret), index=idx)

    # monthly grid 2021-04 .. 2026-07 (last window partial to 2026-07-28 data end)
    starts = pd.date_range("2021-04-01", "2026-07-01", freq="MS", tz="UTC")
    rows, contrib_nov = [], {}
    for s in starts:
        e = min(s + pd.DateOffset(months=1), idx[-1] + pd.Timedelta(minutes=15))
        m = port_eq[(port_eq.index >= s) & (port_eq.index < e)]
        b = bench["close"][(bench.index >= s) & (bench.index < e)]
        if len(m) < 2 or len(b) < 2:
            continue
        strat = (float(m.iloc[-1]) / float(m.iloc[0]) - 1) * 100
        bret = (float(b.iloc[-1]) / float(b.iloc[0]) - 1) * 100
        rows.append({"month": str(s.date()), "strat": round(strat, 2),
                     "bench": round(bret, 2), "excess": round(strat - bret, 2),
                     "partial": bool(e >= idx[-1])})
        if s == pd.Timestamp("2022-11-01", tz="UTC"):
            mask = (idx >= s) & (idx < e)
            sl = wl[mask]
            for j, al in enumerate(WEIGHTED):
                r_bar = rets[al].to_numpy()[mask]
                contrib = float((sl[:, j] * r_bar).sum() * 100)      # arithmetic contribution
                r_arith = float(r_bar.sum() * 100)                    # specialist month arith return
                r_comp = (float(eq[al][(idx >= s) & (idx < e)].iloc[-1]) /
                          float(eq[al][(idx >= s) & (idx < e)].iloc[0]) - 1) * 100
                w_eff = float(sl[:, j].mean())
                contrib_nov[al] = {"weight_mean": round(w_eff, 4), "contribution_pct": round(contrib, 3),
                                   "spec_month_arith_pct": round(r_arith, 2),
                                   "spec_month_comp_pct": round(r_comp, 2)}
                # RECONCILIATION GUARD
                bad = (contrib > r_arith + 1e-6) if r_arith >= 0 else (contrib < r_arith - 1e-6)
                if bad and abs(r_arith) > 1e-9:
                    json.dump({"market": mkt, "month": "2022-11", "alpha": al,
                               "contrib": contrib, "spec_month_arith": r_arith,
                               "detail": contrib_nov[al]},
                              open(f"{REPO}/tuner/runs/v21g_direct/INCONSISTENCY_{mkt}.json", "w"), indent=1)
                    print(f"INCONSISTENCY {mkt} {al}: contribution {contrib:.3f}% vs month return {r_arith:.2f}%")
                    sys.exit(3)

    exc = [r["excess"] for r in rows]
    mean_exc = float(np.mean(exc))
    fulls = [r["excess"] for r in rows if not r["partial"]]
    mean_exc_full = float(np.mean(fulls)) if fulls else mean_exc
    worst4 = sorted(rows, key=lambda r: r["excess"])[:4]
    ftx = next(r for r in rows if r["month"] == "2022-11-01")
    total_strat = (port_eq.iloc[-1] / port_eq[port_eq.index >= pd.Timestamp("2021-04-01", tz="UTC")].iloc[0] - 1) * 100
    total_bench = (bench["close"].iloc[-1] / bench["close"][bench.index >= pd.Timestamp("2021-04-01", tz="UTC")].iloc[0] - 1) * 100
    peak = port_eq.cummax()
    mdd = float(((peak - port_eq) / peak).max() * 100)

    summary = {
        "market": mkt, "path": "direct ctx=None", "detector": DET, "detector_params": det7,
        "specialists": WEIGHTED, "n_months": len(rows),
        "mean_monthly_excess_pct": round(mean_exc, 3),
        "mean_monthly_excess_full_months_only_pct": round(mean_exc_full, 3),
        "n_full_months": len(fulls),
        "t_stat_monthly": round(mean_exc / (np.std(exc, ddof=1) / np.sqrt(len(exc))), 3),
        "ftx_2022_11": ftx, "worst4_months": worst4,
        "nov2022_contributions": contrib_nov,
        "total_2021_04_onwards": {"strat_pct": round(total_strat, 1), "bench_pct": round(total_bench, 1)},
        "portfolio_mdd_pct": round(mdd, 2),
        "lane_share_pct": {ln: round(float((lane_codes == li).mean() * 100), 1)
                           for li, ln in enumerate(LANES)},
    }
    json.dump(summary, open(f"{CURVE_DIR}/{mkt}_summary.json", "w"), indent=1)

    # ── HTML: 3 panels (equity vs B&H + regime shading | monthly excess | DD) ──
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    anchor = pd.Timestamp("2021-04-01", tz="UTC")
    p = port_eq[port_eq.index >= anchor]
    b = bench["close"][bench.index >= anchor]
    pn, bn = p / float(p.iloc[0]) * 100, b / float(b.iloc[0]) * 100
    step = max(1, len(p) // 2500)
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        row_heights=[0.55, 0.25, 0.2])
    fig.add_trace(go.Scatter(x=b.index[::step], y=bn[::step], name=f"{mkt} B&H",
                             line=dict(color="#4a78b0", width=1.3)), row=1, col=1)
    fig.add_trace(go.Scatter(x=p.index[::step], y=pn[::step], name="v21g direct transplant",
                             line=dict(color="#2ca02c", width=1.8)), row=1, col=1)
    reg = pd.Series(lane_names, index=idx)[idx >= anchor]
    spans = []
    for i, ts in enumerate(reg.index):
        r = reg.iloc[i]
        if spans and spans[-1][0] == r and spans[-1][2] == i - 1:
            spans[-1][2] = i
        else:
            spans.append([r, i, i])
    COLORS = {"confirmed_bearish": "rgba(200,60,60,0.10)", "grind_down": "rgba(160,160,160,0.10)",
              "vol_compressed": "rgba(220,180,40,0.10)", "expansion": "rgba(60,180,90,0.08)"}
    for r, i0, i1 in spans:
        if i1 - i0 > 96:
            fig.add_vrect(x0=reg.index[i0], x1=reg.index[i1], fillcolor=COLORS[r],
                          line_width=0, row=1, col=1)
    fig.add_trace(go.Bar(x=[r["month"] for r in rows], y=exc, name="monthly excess %",
                         marker_color=np.where(np.array(exc) >= 0, "#2ca02c", "#c0504d"),
                         opacity=0.85), row=2, col=1)
    ddp = (pn / pn.cummax() - 1) * 100
    ddb = (bn / bn.cummax() - 1) * 100
    fig.add_trace(go.Scatter(x=p.index[::step], y=ddp[::step], name="portfolio DD%",
                             line=dict(color="#2ca02c", width=1.2)), row=3, col=1)
    fig.add_trace(go.Scatter(x=b.index[::step], y=ddb[::step], name="B&H DD%",
                             line=dict(color="#4a78b0", width=1.2)), row=3, col=1)
    fig.update_layout(
        template="plotly_dark", width=1600, height=950,
        title=(f"blender v21g → {mkt}/USDT DIRECT-path transplant (ctx=None rebuild, detector {DET}) — "
               f"2021-04 → 2026-07 | mean excess {mean_exc:+.2f}%/mo · FTX Nov-22 {ftx['strat']:+.1f}% vs bench {ftx['bench']:+.1f}% · "
               f"MDD {mdd:.1f}%<br><span style='font-size:11px'>specialist curves re-simmed per-bar via engine direct path "
               f"(not fast-context); netted fees 8bp on Δnet exposure; lane shares: "
               + " · ".join(f"{ln} {summary['lane_share_pct'][ln]:.0f}%" for ln in LANES) + "</span>"),
        legend=dict(orientation="h", y=-0.08), margin=dict(l=50, r=20, t=110, b=110))
    fig.update_xaxes(type="date", row=1, col=1)
    fig.update_xaxes(type="category", row=2, col=1, tickfont=dict(size=7), tickangle=45)
    fig.update_yaxes(title="excess %", row=2, col=1)
    fig.update_yaxes(title="DD %", row=3, col=1)
    out = f"{REPO}/reports/v21g_{mkt}_direct.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"COMPOSE_OK {mkt} mean_exc={mean_exc:+.3f}%/mo n_months={len(rows)} "
          f"FTX strat {ftx['strat']:+.2f} vs bench {ftx['bench']:+.2f} -> {out}")
    print(json.dumps(summary, indent=1)[:1500])

if __name__ == "__main__":
    main()
