#!/usr/bin/env python3
"""BLENDER v1 — the assembler (2026-10-10, JP $0 plan).

Evaluates candidate portfolios as EXACT bar-level arithmetic over the
precomputed specialist equity curves (data/precompute/). No engine re-sims.

Portfolio model (v1, documented approximations):
- Regime detector: FIXED at router v2.2 defaults (donchian 192, confirm 96,
  vol enter/exit 0.75/0.85, grind slope 96 / confirm 48), computed once from
  the archive. Lanes: confirmed_bearish (shorts legal), grind_down (cash
  only), vol_compressed (chop), expansion (fast lane).
- Per bar: portfolio return = sum_i w[lane][i] * r_i(bar), where r_i = bar
  return of specialist i's stored curve (curves already include each
  specialist's own per-trade fees at 0.0008).
- Turnover cost: 0.0008 * |d(sum w)| per bar (conservative; blending itself
  doesn't trade, this covers weight-shift rebalancing).
- Exposure per lane capped: sum |w[lane]| <= 1.

Fitness: BLENDER_FITNESS.md law — excess reward, segment terms, MDD pure
cost + vetoes (crash-shield scoped to down-leg), out-penalty (10% band),
parsimony. Search: Optuna TPE (deterministic seed) over lane weights.
Reports: top candidates, monthly-window table, bootstrap distribution.
"""
from __future__ import annotations

import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

REPO = os.getcwd()
EXEC_CSV = os.path.join(REPO, "framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv")
PRE = os.path.join(REPO, "data/precompute")
FEE = 0.0008

# fixed regime detector (router v2.2 defaults) — documented v1 simplification
DONCH, CONFIRM = 192, 96
VOL_ENTER, VOL_EXIT = 0.75, 0.85
GRIND_SLOPE, GRIND_CONFIRM = 96, 48
LANES = ["confirmed_bearish", "grind_down", "vol_compressed", "expansion"]
TRADABLE = {"confirmed_bearish": None, "vol_compressed": None, "expansion": None}  # grind = cash


def load_specialists():
    man = json.load(open(os.path.join(PRE, "manifest.json")))
    curves, names = [], []
    pos = {}
    for f in sorted(man.keys()):
        df = pd.read_csv(os.path.join(PRE, f"{f}.csv.gz"))
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        d = df.set_index("timestamp")
        curves.append(d["equity"])
        pos[f] = d["position"] if "position" in d.columns else pd.Series(0.0, index=d.index)
        names.append(f)
    eq = pd.concat(curves, axis=1)
    eq.columns = names
    P = pd.concat([pos[n] for n in names], axis=1)
    P.columns = names
    return eq.pct_change().fillna(0.0), names, P.fillna(0.0)


def regime_series(bench: pd.DataFrame) -> pd.Series:
    h, l, c = bench["high"], bench["low"], bench["close"]
    hh = h.rolling(DONCH, min_periods=DONCH // 2).max()
    ll = l.rolling(DONCH, min_periods=DONCH // 2).min()
    mid = (hh + ll) / 2.0
    prev = c.shift(1)
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    vrf = tr.rolling(14, min_periods=5).mean()
    vrs = tr.rolling(96, min_periods=24).mean().replace(0, 1e-9)
    vr = (vrf / vrs).fillna(1.0).to_numpy()
    below = (c < mid).astype(float)
    sustained = below.rolling(CONFIRM, min_periods=CONFIRM).mean() >= 0.9
    slope = (c - c.rolling(GRIND_SLOPE, min_periods=GRIND_SLOPE // 2).mean())
    slope_neg = (slope < 0).astype(float).rolling(GRIND_CONFIRM, min_periods=GRIND_CONFIRM).mean() >= 0.8

    vr_ = vr
    comp = np.zeros(len(vr_), dtype=bool)
    state = False
    for k in range(len(vr_)):
        if not state and vr_[k] < VOL_ENTER:
            state = True
        elif state and vr_[k] > VOL_EXIT:
            state = False
        comp[k] = state

    reg = np.where(sustained.to_numpy() & (c.to_numpy() < mid.to_numpy()), "confirmed_bearish",
          np.where((c.to_numpy() < mid.to_numpy()) & slope_neg.to_numpy(), "grind_down",
          np.where(comp, "vol_compressed", "expansion")))
    return pd.Series(reg, index=bench.index)


def window_metrics(port_eq: pd.Series, bench_close: pd.Series, s, e):
    m = port_eq[(port_eq.index >= s) & (port_eq.index < e)]
    b = bench_close[(bench_close.index >= s) & (bench_close.index < e)]
    if len(m) < 2 or len(b) < 2:
        return None
    strat = (float(m.iloc[-1]) / float(m.iloc[0]) - 1) * 100
    bench = (float(b.iloc[-1]) / float(b.iloc[0]) - 1) * 100
    peak = m.cummax()
    mdd = ((peak - m) / peak).max() * 100
    # segments at bench trough
    ti = b.idxmin()
    def at(series, ts):
        sub = series[series.index <= ts]
        return float(sub.iloc[-1]) if len(sub) else float(series.iloc[0])
    e0, e_t, e1 = float(m.iloc[0]), at(m, ti), float(m.iloc[-1])
    c0, c_t = float(b.iloc[0]), float(b.loc[ti])
    dn_b = (c_t / c0 - 1) * 100
    up_b = (e1 and (float(b.iloc[-1]) / c_t - 1)) * 100
    dn_s = (e_t / e0 - 1) * 100
    up_s = (e1 / e_t - 1) * 100
    # down-leg MDD (crash-shield scope) + bench down-leg MDD
    seg = m[m.index <= ti]
    dmdd = (((seg.cummax() - seg) / seg.cummax()).max() * 100) if len(seg) > 1 else 0.0
    segb = b[b.index <= ti]
    bdmdd = (((segb.cummax() - segb) / segb.cummax()).max() * 100) if len(segb) > 1 else 0.0
    return {"strat": strat, "bench": bench, "excess": strat - bench, "mdd": mdd,
            "bench_down": dn_b, "bench_up": up_b, "strat_down": dn_s, "strat_up": up_s,
            "up_capture": (up_s / up_b) if up_b > 3.0 else None,
            "dn_mdd": dmdd, "bench_dn_mdd": bdmdd}


def bench_bdd_series(bench_close, months):
    """Per-window bench down-leg MDD -> the market's own noise-floor anchor (JP directive)."""
    out = []
    for s, e in months:
        b = bench_close[(bench_close.index >= s) & (bench_close.index < e)]
        if len(b) < 2:
            continue
        ti = b.idxmin()
        seg = b[b.index <= ti]
        out.append(((seg.cummax() - seg) / seg.cummax()).max() * 100 if len(seg) > 1 else 0.0)
    return np.array(out)


def shield_anchor(bench_close, months):
    """Data-anchored g low point: p25 of window BDDs, capped [3, 20] for sanity."""
    bdd = bench_bdd_series(bench_close, months)
    return float(np.clip(np.percentile(bdd[bdd > 0], 25), 3.0, 20.0))


def out_penalty_pct(t):  # JP law 2026-10-09 (10% band)
    return 0.0 if (t != t or t <= 10.0) else ((t - 10.0) / 10.0) ** 1.5


def mdd_penalty(mdd):  # JP law v2, 2026-10-14: free <=15%, linear score haircut to 100% at 65%
    return float(np.clip((mdd - 15.0) / 50.0, 0.0, 1.0))


def evaluate(weights, rets, lane_of_bar, bench_close, months, n_specialists, pos_mat=None, g_anchor=None, shift=1):
    """weights: dict lane -> np.array(n). pos_mat: (bars, n) internal positions for
    NETTED fee accounting (JP 2026-10-14): fees apply only to changes of the NET
    market exposure sum_i w_i * pos_i — internal-ledger netting, not per-specialist trades.
    shift=1 is HONEST pairing (CRITICAL-1 fix, 2026-10-16): lane label at bar t is
    computed from close[t], so it may only act on returns from bar t+1 onward —
    weights applied to rets[t] are those decided on information through close[t-1].
    shift=0 reproduces the ORIGINAL LOOKAHEAD pairing (forensic use ONLY)."""
    W = np.zeros((len(LANES), n_specialists))
    for li, lane in enumerate(LANES):
        if lane in weights:
            W[li] = weights[lane]
    # exposure per lane
    for li in range(len(LANES)):
        if np.abs(W[li]).sum() > 1.0 + 1e-9:
            return -np.inf, "lane exposure >1"
    if pos_mat is not None and float(pos_mat.to_numpy().__abs__().sum()) == 0.0:
        raise AssertionError("position coverage zero — parse bug class (2026-10-16): "
                             "a zero-exposure portfolio is impossible over a full span")
    wl = np.zeros((len(rets), n_specialists))
    lob = lane_of_bar if str(lane_of_bar.dtype).startswith("int") else None
    for li, lane in enumerate(LANES):
        mask = (lane_of_bar == li) if lob is not None else (lane_of_bar == lane)
        wl[mask] = W[li]
    if shift > 0:  # HONEST pairing: labels lag by `shift` bars before touching returns
        wl = np.vstack([wl[:shift], wl[:-shift]])
    w_ret = (wl * rets.to_numpy()).sum(axis=1)
    if pos_mat is not None:
        net_expo = (wl * pos_mat.to_numpy()).sum(axis=1)
        turn = np.abs(np.diff(net_expo, prepend=0.0))
    else:
        turn = np.abs(np.diff(wl.sum(axis=1), prepend=0.0))
    port_ret = w_ret - FEE * turn
    port_eq = pd.Series(np.cumprod(1 + port_ret), index=rets.index)

    excesses, wm_list = [], []
    worst_mdd = 0.0

    ga = g_anchor if g_anchor else 9.0  # per-market anchor passed by callers; ETH p25 approx
    def _soft_shield(bdd, sdd):
        frac = float(np.interp(bdd, [10.0, 50.0], [0.7, 0.5]))
        allowed = frac * bdd
        if sdd <= allowed or bdd <= 1.0:
            return 0.0
        x_pct = (sdd - allowed) / allowed * 100.0  # JP-confirmed reading (C): relative to allowance
        g = float(np.interp(bdd, [ga, 50.0], [0.05, 1.0]))  # data-anchored (JP 2026-10-15)
        return x_pct * g
    for (s, e) in months:
        wv = window_metrics(port_eq, bench_close, s, e)
        if wv is None:
            continue
        excesses.append(wv["excess"])
        wm_list.append(wv)
        worst_mdd = max(worst_mdd, wv["mdd"])
        # SOFT crash-shield (JP 2026-10-15): allowance frac 0.7@BDD<=10 -> 0.5@BDD>=50;
        # excess x pts penalizes score pct at rate 0.1x@BDD<=10 -> x@BDD>=50. No veto.
    shield_pen = 0.0  # summed score-percentage penalty (soft law)
    mean_exc = float(np.mean(excesses))
    t_stat = float(np.mean(excesses) / (np.std(excesses, ddof=1) / np.sqrt(len(excesses)))) if len(excesses) > 2 else 0.0
    run_mdd = worst_mdd  # JP law v2: no run-MDD veto; linear haircut applies
    net_abs = np.abs((wl * pos_mat.to_numpy()).sum(axis=1)) if pos_mat is not None else np.abs(wl.sum(axis=1))
    time_out = float((net_abs < 0.05).mean() * 100)
    pen_out = out_penalty_pct(time_out)
    mdd_frac = mdd_penalty(run_mdd)
    shield_pen = 0.0
    for w in wm_list:
        if w.get("bench_dn_mdd"):
            shield_pen += _soft_shield(w["bench_dn_mdd"], w["dn_mdd"])
    shield_pen = min(shield_pen, 100.0)
    # segment terms
    dn_ex = [w["strat_down"] - w["bench_down"] for w in wm_list]
    caps = [w["up_capture"] for w in wm_list if w["up_capture"] is not None]
    seg_dn = float(np.mean(dn_ex))
    seg_up = float(np.mean(caps)) if caps else 0.0
    # parsimony: count active specialists
    active = sum(1 for li in range(len(LANES)) for i in range(n_specialists) if abs(W[li][i]) > 0.02)
    par = 0.05 * max(active - 6, 0)
    raw = (1.0 * mean_exc + 0.3 * max(t_stat, 0) + 0.3 * seg_dn + 0.3 * seg_up
           - pen_out - par)
    score = raw * (1.0 - mdd_frac) * (1.0 - shield_pen / 100.0)  # law v2 x soft shield
    return score, {"mean_excess": mean_exc, "t": t_stat, "seg_dn": seg_dn, "seg_up": seg_up,
                   "run_mdd": run_mdd, "time_out": time_out, "active": active,
                   "windows": wm_list}


def flip_rent(weights, rets, lane_of_bar, bench_close, months, n_specialists, pos_mat, g_anchor):
    """CRITICAL-1 guard: how much of the edge is SAME-BAR label rent (lookahead value)?
    Compares mean excess under shift=0 (act on the label the instant it exists — illegal)
    vs shift=1 (honest). If >25% of the edge vanishes... no: if >25% of the shift0 edge
    IS the rent, the candidate is lookahead-flattered -> ALARM. Run on every winner."""
    s0 = evaluate(weights, rets, lane_of_bar, bench_close, months, n_specialists, pos_mat=pos_mat, g_anchor=g_anchor, shift=0)[1]["mean_excess"]
    s1 = evaluate(weights, rets, lane_of_bar, bench_close, months, n_specialists, pos_mat=pos_mat, g_anchor=g_anchor, shift=1)[1]["mean_excess"]
    share = (s0 - s1) / s0 if abs(s0) > 1e-9 else 0.0
    return {"edge_if_samebar": round(s0, 2), "edge_honest": round(s1, 2),
            "rent_share_pct": round(share * 100, 1), "alarm": bool(share > 0.25)}


def relabel_invariance(weights, rets, lane_of_bar, bench_close, months, n_specialists, pos_mat, g_anchor):
    """CRITICAL-1 guard: does the edge survive acting one bar LATER than assumed?
    shift=1 vs shift=2. A real edge decays gently; a timing illusion collapses.
    Retention < 0.25 -> ALARM (edge lives on a knife-edge of execution speed)."""
    s1 = evaluate(weights, rets, lane_of_bar, bench_close, months, n_specialists, pos_mat=pos_mat, g_anchor=g_anchor, shift=1)[1]["mean_excess"]
    s2 = evaluate(weights, rets, lane_of_bar, bench_close, months, n_specialists, pos_mat=pos_mat, g_anchor=g_anchor, shift=2)[1]["mean_excess"]
    retention = (s2 / s1) if s1 > 1e-9 else 0.0
    return {"edge_shift1": round(s1, 2), "edge_shift2": round(s2, 2),
            "retention": round(retention, 3), "alarm": bool(retention < 0.25)}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3000)
    ap.add_argument("--label", default="blender_v1")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rets, names, POS = load_specialists()
    bench = pd.read_csv(EXEC_CSV, parse_dates=["timestamp"], index_col="timestamp").sort_index()
    bench = bench.loc[rets.index[0]:]
    lane = regime_series(bench).loc[rets.index]
    lane_of_bar = lane.to_numpy()

    # monthly windows across the sealed span
    starts = pd.date_range("2021-04-01", "2026-06-01", freq="MS", tz="UTC")
    months = [(s, s + pd.DateOffset(months=1)) for s in starts]
    GA = shield_anchor(bench["close"], months)
    print(f"shield g-anchor (p25 of this market's window BDDs): {GA:.1f}%")

    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    # v2.1: detector grid (48 precomputed lane series) as a searchable dim
    GRID_NPZ = os.path.join(REPO, "data", "precompute", "regime_grid.npz")
    grid_codes = None
    n_det = 1
    default_det = 0
    if os.path.exists(GRID_NPZ):
        z = np.load(GRID_NPZ)
        gidx = pd.DatetimeIndex(z["index"].astype("int64"))
        pos = gidx.asi8.searchsorted(pd.DatetimeIndex(rets.index).asi8)
        grid_codes = z["lanes"][:, pos]  # align columns to specialist-curve bars
        n_det = grid_codes.shape[0]
        meta = json.load(open(os.path.join(REPO, "data", "precompute", "regime_grid.json")))
        for m in meta:  # router v2.2 defaults
            if (m["donchian"], m["confirm"], (m["vol_enter"], m["vol_exit"]),
                (m["grind_slope"], m["grind_confirm"])) == (192, 96, (0.75, 0.85), (96, 48)):
                default_det = m["i"]
                break
        print(f"detector grid: {n_det} series; v2.2-default = index {default_det}")

    TRIAL_LOG = []
    def objective(trial):
        det = trial.suggest_categorical("detector", list(range(n_det))) if n_det > 1 else default_det
        lob = grid_codes[det] if grid_codes is not None else None
        weights = {}
        for lane_name in ("confirmed_bearish", "vol_compressed", "expansion"):
            w = np.zeros(len(names))
            for i, nm in enumerate(names):
                on = trial.suggest_categorical(f"{lane_name[:3]}_{nm}", [0, 1])
                if on:
                    w[i] = trial.suggest_float(f"w_{lane_name[:3]}_{nm}", 0.0, 1.0)
            s = w.sum()  # long-only exposure cap (anti-specialists banned: curves are not shortable instruments)
            if s > 1.0:
                w = w / s
            weights[lane_name] = w
        lob_use = lob if lob is not None else lane_of_bar
        score, det = evaluate(weights, rets, lob_use, bench["close"], months, len(names), pos_mat=POS, g_anchor=GA)
        if score == -np.inf:
            TRIAL_LOG.append({"score": -50.0, "vetoed": det, "excesses": None})
            return -50.0  # below any real score, visible-but-vetoed
        TRIAL_LOG.append({"score": score, "vetoed": None,
                           "excesses": [w["excess"] for w in det["windows"]]})
        return score

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=args.seed))
    # v2.1: enqueue the standing champion's exact weights (guaranteed >= its score)
    champ_path = os.path.join(REPO, "tuner", "runs", "blender_v1b.json")
    if os.path.exists(champ_path):
        champ = json.load(open(champ_path))
        params = {"detector": default_det}
        for nm in names:
            for lane_name in ("confirmed_bearish", "vol_compressed", "expansion"):
                w = champ["weights"].get(lane_name, {}).get(nm)
                params[f"{lane_name[:3]}_{nm}"] = 1 if w else 0
                if w:
                    params[f"w_{lane_name[:3]}_{nm}"] = w
        study.enqueue_trial(params)
        print("enqueued v1b champion as trial 1")
    study.optimize(objective, n_trials=args.trials, show_progress_bar=False)

    # reconstruct best
    bp = study.best_params
    best_det = bp.get("detector", default_det)
    lob_best = grid_codes[best_det] if grid_codes is not None else lane_of_bar
    weights = {}
    for lane_name in ("confirmed_bearish", "vol_compressed", "expansion"):
        w = np.zeros(len(names))
        for i, nm in enumerate(names):
            if bp.get(f"{lane_name[:3]}_{nm}", 0):
                w[i] = bp[f"w_{lane_name[:3]}_{nm}"]
        s = w.sum()
        if s > 1.0:
            w = w / s
        weights[lane_name] = w
    score, det = evaluate(weights, rets, lob_best, bench["close"], months, len(names), pos_mat=POS, g_anchor=GA)
    if score == -np.inf:
        raise SystemExit(f"RECONSTRUCTION VETOED: {det} (should not happen — investigate)")

    # HONESTY GATES on the winner (CRITICAL-1 guards, 2026-10-16) + July partial disclosure
    fr = flip_rent(weights, rets, lob_best, bench["close"], months, len(names), POS, GA)
    ri = relabel_invariance(weights, rets, lob_best, bench["close"], months, len(names), POS, GA)
    july = evaluate(weights, rets, lob_best, bench["close"],
                    [(pd.Timestamp("2026-07-01", tz="UTC"), pd.Timestamp("2026-07-28", tz="UTC"))],
                    len(names), pos_mat=POS, g_anchor=GA)[1]["mean_excess"]
    print(f"HONESTY | flip-rent share {fr['rent_share_pct']}% (alarm >25%: {fr['alarm']}) | "
          f"relabel retention {ri['retention']} (alarm <0.25: {ri['alarm']}) | "
          f"July-2026 partial excess {july:+.2f}%")

    out = {"label": args.label, "detector": int(best_det), "score": round(score, 3),
           "weights": {ln: {nm: round(float(w[i]), 3) for i, nm in enumerate(names) if abs(w[i]) > 0.02}
                        for ln, w in weights.items()},
           "details": {k: v for k, v in det.items() if k != "windows"},
           "honesty": {"flip_rent": fr, "relabel_invariance": ri,
                       "july26_partial_excess": round(july, 2)},
           "windows": [{"month": str(s.date()), **{k: (round(v, 2) if isinstance(v, float) else v)
                     for k, v in w.items()}} for (s, e), w in zip(months, det["windows"])]}
    json.dump(TRIAL_LOG, open(os.path.join(REPO, "tuner", "runs", f"{args.label}_trials.json"), "w"))
    path = os.path.join(REPO, "tuner", "runs", f"{args.label}.json")
    json.dump(out, open(path, "w"), indent=1)
    print(f"BEST score {score:+.2f} | mean excess {det['mean_excess']:+.2f}% | t {det['t']:+.2f} | "
          f"seg_dn {det['seg_dn']:+.1f} | up_cap {det['seg_up']:+.2f} | MDD {det['run_mdd']:.1f}% | "
          f"out {det['time_out']:.0f}% | specialists {det['active']}")
    print("weights:", json.dumps(out["weights"]))
    print("->", path)


if __name__ == "__main__":
    main()
