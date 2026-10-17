#!/usr/bin/env python3
"""compose_portfolio.py — canonical portfolio recomposition (WARN-4 fix, 2026-10-17).

Laws encoded (see RESEARCH_LEDGER 2026-10-16/17):
- HONEST pairing: lane label of bar t may only act on returns from t+1 (shift=1).
- NETTED-ONLY fees (JP 2026-10-17 standing law): fee = |Delta(sum w_i pos_i)| x 0.0008.
  Use fee-free curves; if curves embed per-trade fees, pass --embed-fee (legacy forensic).
- 63-window grid 2021-04..2026-06 (matches blender.py main()); July-2026 partial disclosed.
- Guards: flip-rent share + relabel-invariance on every run.

Usage:
  python3 tools/audits/compose_portfolio.py --weights tuner/runs/blender_v3h.json \
      [--market ETH --curves data/precompute] \
      [--market SOL|BTC --curves tuner/runs/v21g_direct] \
      [--funding framework/data_cache/binance_ETHUSDT_funding_proxy_202101_202610.csv]
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from tools.blender import LANES, evaluate, flip_rent, relabel_invariance
from tools.regime_grid import regime_array

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEE = 0.0008


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True, help="blender result JSON")
    ap.add_argument("--market", default="ETH")
    ap.add_argument("--curves", default=None, help="dir of specialist curves (ETH precompute default)")
    ap.add_argument("--detector", type=int, default=None, help="detector index; default = weights JSON's")
    ap.add_argument("--funding", default=None, help="funding CSV overlay (binance proxy)")
    ap.add_argument("--embed-fee", action="store_true", help="curves embed per-trade fees (legacy double-charge world)")
    ap.add_argument("--fee-free", action="store_true", help="EXPERIMENTAL: strips nothing — reminder flag that substrate must be fee-free")
    args = ap.parse_args()

    d = json.load(open(args.weights))
    names = sorted({nm for wm in d["weights"].values() for nm in wm})
    det_idx = args.detector if args.detector is not None else d.get("detector", 7)
    gmeta = json.load(open(os.path.join(REPO, "data/precompute/regime_grid.json")))
    m = [x for x in gmeta if x["i"] == det_idx][0]

    bench = pd.read_csv(os.path.join(REPO, f"framework/data_cache/okx_{args.market}_USDT_15m_20210101_20260928.csv"),
                        parse_dates=["timestamp"], index_col="timestamp").sort_index()
    cu, po = {}, {}
    for n in names:
        p = os.path.join(args.curves or os.path.join(REPO, "data/precompute"),
                         f"{n}.csv.gz" if args.market == "ETH" else f"{args.market}_{n}.csv.gz")
        df = pd.read_csv(p)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        s = df.set_index("timestamp")
        cu[n] = s["equity"]
        po[n] = s["position"].fillna(0.0)  # NUMERIC convention — the 2026-10-16 bug class
    cu = pd.concat(cu, axis=1); po = pd.concat(po, axis=1)
    assert float(po.to_numpy().__abs__().sum()) > 0, "position coverage zero — parse bug"

    lanes = pd.Series(regime_array(bench, m["donchian"], m["confirm"], m["vol_enter"], m["vol_exit"],
                                   m["grind_slope"], m["grind_confirm"]),
                      index=bench.index).reindex(cu.index).fillna(3).to_numpy().astype(int)
    nl = list(cu.columns)
    W = np.zeros((4, len(nl)))
    for ln, wm in d["weights"].items():
        for nm, w in wm.items():
            if nm in nl:
                W[LANES.index(ln)][nl.index(nm)] = w
    warr = {LANES[li]: W[li] for li in range(4)}

    months = [(pd.Timestamp("2021-04-01", tz="UTC") + pd.DateOffset(months=k),
               pd.Timestamp("2021-04-01", tz="UTC") + pd.DateOffset(months=k + 1)) for k in range(63)]
    rets = cu[nl].pct_change().fillna(0.0)
    ga = 8.9
    sc, det = evaluate(warr, rets, lanes, bench["close"], months, len(nl), pos_mat=po[nl], g_anchor=ga, shift=1)

    if args.funding:
        fund = pd.read_csv(args.funding, index_col=0)
        fund.index = pd.to_datetime(fund.index, utc=True, format="ISO8601")
        fr = fund["rate"].sort_index().reindex(cu.index, method="ffill").fillna(0.0).to_numpy()
        wl = np.zeros((len(cu), len(nl)))
        for li in range(4):
            wl[lanes == li] = W[li]
        wl = np.vstack([wl[:1], wl[:-1]])
        net = (wl * po[nl].to_numpy()).sum(axis=1)
        fc = np.where((cu.index.hour % 8 == 0) & (cu.index.minute == 0), fr * net, 0.0)
        sc_f, det_f = evaluate(warr, rets - 0, lanes, bench["close"], months, len(nl), pos_mat=po[nl], g_anchor=ga, shift=1)
        # recompute with funding by direct composition (evaluate has no funding hook yet)
        pr = (wl * rets.to_numpy()).sum(axis=1) - FEE * np.abs(np.diff(net, prepend=0.0)) - fc
        port = pd.Series(np.cumprod(1 + pr), index=cu.index)
        excs = []
        for s_, e_ in months:
            mm = port[(port.index >= s_) & (port.index < e_)]
            bb = bench["close"][(bench.index >= s_) & (bench.index < e_)]
            if len(mm) >= 2:
                excs.append((mm.iloc[-1] / mm.iloc[0] - 1 - (bb.iloc[-1] / bb.iloc[0] - 1)) * 100)
        ex = np.array(excs)
        t = ex.mean() / (ex.std(ddof=1) / np.sqrt(len(ex)))
        print(f"[+funding] mean excess {ex.mean():+.2f}%/mo | t {t:+.2f} | final {port.iloc[-1]/port.iloc[0]:,.0f}x")
        det = {"mean_excess": float(ex.mean()), "t": float(t)}

    fr_guard = flip_rent(warr, rets, lanes, bench["close"], months, len(nl), po[nl], ga)
    ri_guard = relabel_invariance(warr, rets, lanes, bench["close"], months, len(nl), po[nl], ga)
    jul = evaluate(warr, rets, lanes, bench["close"],
                   [(pd.Timestamp("2026-07-01", tz="UTC"), pd.Timestamp("2026-07-28", tz="UTC"))],
                   len(nl), pos_mat=po[nl], g_anchor=ga, shift=1)[1]["mean_excess"]

    world = "legacy double-charge (forensic)" if args.embed_fee else "NETTED-ONLY (real-account law)"
    print(f"[{args.market}] {world} | honest mean excess {det['mean_excess']:+.2f}%/mo | t {det['t']:+.2f}")
    print(f"guards: flip-rent {fr_guard['rent_share_pct']}% (alarm {fr_guard['alarm']}) | "
          f"relabel retention {ri_guard['retention']} (alarm {ri_guard['alarm']}) | July-26 partial {jul:+.2f}%")


if __name__ == "__main__":
    main()
