# Bull mining r2 — stage runner. Read-only on repo; writes only ./_runs and /tmp.
import os, sys, json, time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from honest_lab import (REPO, SEAL, FEE, GRID_START, GRID_END_EX, load_exec, load_1h, load_funding_avg,
                        align_funding_to_bars, TurtleLatch, PullbackTrend, VolScaledTurtle, VolScaledCB,
                        ConfirmedBreakout, MomentumBlend, HonestEngine, build_exec_and_fund)
from dataclasses import dataclass

RUNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_runs")
os.makedirs(RUNS, exist_ok=True)

MONTHS = pd.date_range(GRID_START, GRID_END_EX, freq="MS", tz="UTC")  # 63 month starts


def monthly_table(curves, months=MONTHS):
    """curves: dict key->DataFrame(timestamp,equity). Returns DataFrame months x keys (fraction rets)."""
    nb = np.array(months.astype("int64").tolist() + [(months[-1] + pd.DateOffset(months=1)).value])
    out = {}
    for k, cur in curves.items():
        tn = cur["timestamp"].astype("int64").values
        eq = cur["equity"].values
        bnd = np.searchsorted(tn, nb, side="left")
        r = np.empty(len(months))
        for j in range(len(months)):
            a, b2 = bnd[j], bnd[j + 1]
            r[j] = eq[b2 - 1] / eq[a - 1] - 1.0 if a > 0 and b2 > a else np.nan
        out[k] = r
    return pd.DataFrame(out, index=[str(m.date()) for m in months])


def bench_monthly(x, months=MONTHS):
    tn = x["timestamp"].astype("int64").values
    c = x["close"].values
    nb = np.array(months.astype("int64").tolist() + [(months[-1] + pd.DateOffset(months=1)).value])
    bnd = np.searchsorted(tn, nb, side="left")
    return np.array([c[bnd[j + 1] - 1] / c[bnd[j] - 1] - 1.0 if bnd[j] > 0 else np.nan for j in range(len(months))])


def funding_cost_month(curve, fund, m0, m1):
    tn = curve["timestamp"].astype("int64").values
    expo = curve["qty"].values * curve["close"].values / np.maximum(curve["equity"].values, 1e-9)
    sb = fund["bucket"].astype("int64").values
    sr = fund["rate"].values
    sel = ((fund["bucket"] >= pd.Timestamp(m0)) & (fund["bucket"] < pd.Timestamp(m1))).values
    idx = np.searchsorted(tn, sb[sel], side="right") - 1
    ok = idx >= 0
    return float((-(sr[sel][ok]) * expo[idx[ok]]).sum()) if ok.any() else 0.0


def tstat(r):
    r = r[~np.isnan(r)]
    return r.mean() / r.std(ddof=1) * np.sqrt(len(r)) if len(r) > 2 and r.std(ddof=1) > 0 else 0.0


def maxdd(curve):
    eq = curve["equity"].values
    peak = np.maximum.accumulate(eq)
    return float(((peak - eq) / peak).max())


def stitch(curves_by_key, picks, months=MONTHS):
    """Concatenate per-month slices of the picked combos' curves, rebased continuously."""
    parts = []
    prev_end = None
    nb = np.array(months.astype("int64").tolist() + [(months[-1] + pd.DateOffset(months=1)).value])
    for j, key in enumerate(picks):
        cur = curves_by_key[key]
        tn = cur["timestamp"].astype("int64").values
        a = np.searchsorted(tn, nb[j], side="left")
        b = np.searchsorted(tn, nb[j + 1], side="left")
        sl = cur.iloc[a:b]
        e = sl["equity"].values.copy()
        if prev_end is not None and len(e) and e[0] != prev_end:
            e = e * (prev_end / e[0])
            sl = sl.assign(equity=e)
        prev_end = e[-1] if len(e) else prev_end
        parts.append(sl)
    return pd.concat(parts, ignore_index=True)


# ── family grids (DECLARED before results; center = fallback combo) ─────────
def grids():
    G = {}
    G["B0_base"] = [
        dict(tag="turtle192_raw", cls="turtle", kw=dict(N=192, atr_n=96, buf=1.0)),
        dict(tag="turtle192_g05", cls="turtle", kw=dict(N=192, atr_n=96, buf=1.0, gate=0.5)),
        dict(tag="turtle192_g07", cls="turtle", kw=dict(N=192, atr_n=96, buf=1.0, gate=0.7)),
    ]
    G["F1_pullback"] = [
        dict(tag=f"pb_t{t}_e{e}", cls="pb", kw=dict(theta=t, exit_ema_n=e), center=(t == 35 and e == 200))
        for t in (30, 35, 40) for e in (100, 200)
    ]
    G["F2_volscale"] = [
        dict(tag=f"vs_s{s}_m{m}", cls="vs", kw=dict(sigma_target=s, smin=m), center=(s == 0.005 and m == 0.25))
        for s in (0.004, 0.005, 0.006) for m in (0.25, 0.5)
    ]
    G["F3_confbreak"] = [
        dict(tag=f"cb_n{n}_h{h}", cls="cb", kw=dict(N=n, m=h), center=(n == 144 and h == 4))
        for n in (96, 144, 192) for h in (2, 4)
    ]
    G["F4_mombld"] = [
        dict(tag=f"mb_t{t}_{md}", cls="mb", kw=dict(theta=t, mode=md), center=(t == 0.75 and md == "mom"))
        for t in (0.5, 0.75, 1.0) for md in ("mom", "turtle")
    ]
    G["F5_fundgrad"] = [
        dict(tag=f"fg_g{g}_k{k}", cls="fg", kw=dict(gate=g, grad_k=k), center=(g == 0.6 and k == 9))
        for g in (0.5, 0.6, 0.7) for k in (9, 21)
    ]
    # declared refinement: vol-scale × funding gate (round-1 gate applied to F2), floor 0 = vol-de-risk to flat
    G["G2_volgate"] = [
        dict(tag=f"vg_s{s}_m{m}_g{g}", cls="vs", kw=dict(sigma_target=s, smin=m, gate=g),
             center=(s == 0.005 and m == 0.25 and g == 0.5))
        for s in (0.005, 0.006) for m in (0.0, 0.25) for g in (0.5, 0.7)
    ]
    # declared combination: time-confirmed breakout entry (F3 best structure) × vol sizing × funding gate
    G["G3_cbgate"] = [
        dict(tag=f"cg_n{n}_g{g}_s{s}", cls="cbs", kw=dict(N=n, m=2, gate=g, sigma_target=s, smin=0.25),
             center=(n == 144 and g == 0.5 and s == 0.005))
        for n in (96, 144, 192) for g in (0.5, 0.7) for s in (0.005, 0.006)
    ]
    return G


def make_model(cls, kw, arr, fcols, x1h):
    if cls in ("turtle", "fg"):
        kw2 = dict(kw)
        if kw2.get("gate") is not None or kw2.get("grad_k") is not None:
            kw2["fund_cols"] = fcols
        if cls == "turtle":
            return TurtleLatch(arr, **kw2)
        return TurtleLatch(arr, N=192, atr_n=96, buf=1.0, **kw2)
    if cls == "pb":
        return PullbackTrend(arr, x1h, **kw)
    if cls == "vs":
        kw2 = dict(kw)
        if kw2.get("gate") is not None or kw2.get("grad_k") is not None:
            kw2["fund_cols"] = fcols
        return VolScaledTurtle(arr, **kw2)
    if cls == "cbs":
        kw2 = dict(kw)
        if kw2.get("gate") is not None or kw2.get("grad_k") is not None:
            kw2["fund_cols"] = fcols
        return VolScaledCB(arr, **kw2)
    if cls == "cb":
        return ConfirmedBreakout(arr, **kw)
    if cls == "mb":
        return MomentumBlend(arr, **kw)
    raise ValueError(cls)


def run_combo(cls, kw, arr, fcols, x1h, fill_lag=1):
    m = make_model(cls, kw, arr, fcols, x1h)
    eng = HonestEngine(m, EXEC_DF, fill_lag=fill_lag)
    cur = eng.run()
    return cur


def jitter_kw(kw, f):
    """Scale ALL numeric params by f (ints rounded, >=8)."""
    out = {}
    for k, v in kw.items():
        if isinstance(v, (int, float)) and k != "grad_k":
            nv = v * f
            out[k] = int(round(nv)) if isinstance(v, int) else float(nv)
        else:
            out[k] = v
    return out


def main(stage):
    global EXEC_DF
    x, arr, fund, fcols = build_exec_and_fund()
    x1h = None
    EXEC_DF = x
    if stage == "validate":
        # my engine (lag=1) vs framework SimulationEngine on turtle192_raw
        sys.path.insert(0, REPO)
        from framework.simulation import SimulationEngine
        kw = dict(N=192, atr_n=96, buf=1.0)
        cur_mine = run_combo("turtle", kw, arr, fcols, x1h)
        m2 = TurtleLatch(arr, **kw)
        se = SimulationEngine(model=m2, fee=FEE, allow_shorts=False)
        res = se.run({"15m": EXEC_CSV}, "15m", data_start=DATA_START_S, data_end=SEAL_S)
        eqf = res.equity_curve
        a = cur_mine["equity"].values
        tn_mine = cur_mine["timestamp"].astype("int64").values
        tn_f = eqf["timestamp"].astype("int64").values
        assert len(a) == len(tn_f) == len(tn_mine), (len(a), len(tn_f))
        d = np.abs(a - eqf["equity"].values).max()
        print("VALIDATION max|eq diff| =", d, "bars", len(a))
        assert d < 1e-6
        print("OK")
        return
    if stage == "grids":
        x1h = load_1h()
        G = grids()
        curves, meta = {}, []
        t0 = time.time()
        for fam, combos in G.items():
            for cd in combos:
                key = cd["tag"]
                cur = run_combo(cd["cls"], cd["kw"], arr, fcols, x1h)
                curves[key] = cur
                meta.append(dict(family=fam, tag=key, cls=cd["cls"],
                                 center=bool(cd.get("center", False)), kw=json.dumps(cd["kw"], default=str)))
                print(f"{fam} {key} done {time.time()-t0:.0f}s eq_end={cur['equity'].iloc[-1]:.0f}", flush=True)
        # baseline lag variants for flip-rent on turtle192 raw/gate
        for tag, kw in [("turtle192_raw", dict(N=192, atr_n=96, buf=1.0)),
                        ("turtle192_g05", dict(N=192, atr_n=96, buf=1.0, gate=0.5))]:
            for lag in (0, 2):
                curves[f"{tag}_lag{lag}"] = run_combo("turtle", kw, arr, fcols, x1h, fill_lag=lag)
                print(f"lag{lag} {tag} done", flush=True)
        pd.DataFrame(meta).to_csv(os.path.join(RUNS, "meta.csv"), index=False)
        tbl = monthly_table(curves)
        tbl.to_csv(os.path.join(RUNS, "monthly_table.csv"))
        # persist curves efficiently (parquet)
        for k, cur in curves.items():
            cur.to_pickle(os.path.join(RUNS, f"curve_{k}.pkl"))
        pass
        json.dump({m.date().isoformat(): float(bench_monthly(x)[i]) for i, m in enumerate(MONTHS)},
                  open(os.path.join(RUNS, "bench_monthly.json"), "w"), indent=0)
        print("GRIDS DONE", len(curves))
        return
    if stage == "wf":
        meta = pd.read_csv(os.path.join(RUNS, "meta.csv"))
        tbl = pd.read_csv(os.path.join(RUNS, "monthly_table.csv"), index_col=0)
        curves = {k: pd.read_pickle(os.path.join(RUNS, f"curve_{k}.pkl")) for k in tbl.columns}
        bench = np.array(list(json.load(open(os.path.join(RUNS, "bench_monthly.json"))).values()))
        fams = [f for f in meta.family.unique() if f != "B0_base"]
        results = {}
        for fam in fams:
            keys = meta[meta.family == fam]
            tags = keys.tag.tolist()
            center = keys[keys.center].tag.iloc[0]
            sub = tbl[tags]
            # walk-forward selection: trailing up to 12 months mean, argmax; fallback center
            picks, tuned = [], []
            for k in range(len(MONTHS)):
                lo = max(0, k - 12)
                hist = sub.iloc[lo:k]
                if len(hist) >= 3 and hist.mean().max() > 0:
                    p = hist.mean().idxmax()
                else:
                    p = center
                picks.append(p)
                tuned.append(sub.iloc[k][p])
            tuned = np.array(tuned)
            ctr = sub[center].values
            results[fam] = dict(
                picks=picks, n_picks=len(set(picks)), center=center,
                oos_mean=float(tuned.mean() * 100), oos_t=float(tstat(tuned)),
                oos_mean_vs_bh=float((tuned - bench).mean() * 100), oos_t_vs_bh=float(tstat(tuned - bench)),
                center_mean=float(np.nanmean(ctr) * 100), center_t=float(tstat(ctr)),
                h1=float(tuned[:32].mean() * 100), h2=float(tuned[32:].mean() * 100),
                worst=float(tuned.min() * 100), best=float(tuned.max() * 100),
                conc=float(tuned.max() / tuned.sum()) if tuned.sum() > 0 else None,
            )
            st = stitch(curves, picks)
            results[fam]["stitch_dd"] = maxdd(st) * 100
            results[fam]["stitch_curve"] = st  # kept in memory only
            print(fam, json.dumps({k: v for k, v in results[fam].items() if k not in ("picks", "stitch_curve")}, default=float), flush=True)
        json.dump({f: {k: (v if not isinstance(v, (np.ndarray, list, pd.DataFrame)) else (v if isinstance(v, list) else None))
                       for k, v in r.items() if k != "stitch_curve"} for f, r in results.items()},
                  open(os.path.join(RUNS, "wf_results.json"), "w"), indent=1, default=str)
        # save pick sequences + stitched curves for later stages
        for fam in fams:
            pd.DataFrame({"month": [str(m.date()) for m in MONTHS], "pick": results[fam]["picks"]}).to_csv(
                os.path.join(RUNS, f"picks_{fam}.csv"), index=False)
            results[fam]["stitch_curve"].to_pickle(os.path.join(RUNS, f"stitch_{fam}.pkl"))
        print("WF DONE")
        return
    if stage == "guards":
        # jitter + shift0/2 + funding cost for survivors chosen by inspecting wf_results.json
        plan = json.load(open(os.path.join(RUNS, "guard_plan.json")))
        x1h = load_1h()
        out = {}
        for fam, p in plan.items():
            cls, kw = p["cls"], p["kw"]
            # jitter draws
            jres = {}
            for f in (0.85, 1.15):
                cur = run_combo(cls, jitter_kw(kw, f), arr, fcols, x1h)
                tbl = monthly_table({"j": cur})
                r = tbl["j"].values
                jres[f"j{f}"] = dict(mean=float(r.mean() * 100), t=float(tstat(r)))
            # shift0 / shift2 on the SAME combo (fixed spec, full span)
            s = {}
            for lag in (0, 2):
                cur = run_combo(cls, kw, arr, fcols, x1h, fill_lag=lag)
                r = monthly_table({"s": cur})["s"].values
                s[f"lag{lag}"] = dict(mean=float(r.mean() * 100), t=float(tstat(r)))
            cur = run_combo(cls, kw, arr, fcols, x1h)
            r = monthly_table({"b": cur})["b"].values
            s["lag1"] = dict(mean=float(r.mean() * 100), t=float(tstat(r)))
            # funding cost paid (full span, on this fixed spec)
            fc = [funding_cost_month(cur, fund, m,
                                     (m + pd.DateOffset(months=1))) for m in MONTHS]
            out[fam] = dict(jitter=jres, shifts=s,
                            fund_cost_mo_mean=float(np.mean(fc) * 100), fund_cost_total=float(np.sum(fc) * 100))
            print(fam, json.dumps(out[fam]), flush=True)
        json.dump(out, open(os.path.join(RUNS, "guards.json"), "w"), indent=1)
        print("GUARDS DONE")


EXEC_CSV = os.path.join(REPO, "framework", "data_cache", "okx_ETH_USDT_15m_20210101_20260928.csv")
DATA_START_S = pd.Timestamp("2021-01-01", tz="UTC").isoformat()
SEAL_S = SEAL.isoformat()
EXEC_DF = None

if __name__ == "__main__":
    main(sys.argv[1])
