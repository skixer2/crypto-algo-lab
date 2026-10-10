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
    for f in sorted(man.keys()):
        df = pd.read_csv(os.path.join(PRE, f"{f}.csv.gz"))
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        curves.append(df.set_index("timestamp")["equity"])
        names.append(f)
    eq = pd.concat(curves, axis=1)
    eq.columns = names
    return eq.pct_change().fillna(0.0), names


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


def out_penalty_pct(t):  # JP law 2026-10-09 (10% band)
    return 0.0 if (t != t or t <= 10.0) else ((t - 10.0) / 10.0) ** 1.5


def mdd_penalty(mdd):  # JP law 2026-10-05
    return (mdd / 5.0) ** 1.5


def evaluate(weights, rets, lane_of_bar, bench_close, months, n_specialists):
    """weights: dict lane -> np.array(n). Returns (score, details) or (-inf, reason)."""
    W = np.zeros((len(LANES), n_specialists))
    for li, lane in enumerate(LANES):
        if lane in weights:
            W[li] = weights[lane]
    # exposure per lane
    for li in range(len(LANES)):
        if np.abs(W[li]).sum() > 1.0 + 1e-9:
            return -np.inf, "lane exposure >1"
    wl = np.zeros((len(rets), n_specialists))
    for li, lane in enumerate(LANES):
        mask = lane_of_bar == lane
        wl[mask] = W[li]
    expo = wl.sum(axis=1)
    port_ret = (wl * rets.to_numpy()).sum(axis=1)
    # turnover cost on exposure changes
    turn = np.abs(np.diff(expo, prepend=0.0))
    port_ret = port_ret - FEE * turn
    port_eq = pd.Series(np.cumprod(1 + port_ret), index=rets.index)

    excesses, wm_list = [], []
    vetoed = None
    worst_mdd = 0.0
    for (s, e) in months:
        wv = window_metrics(port_eq, bench_close, s, e)
        if wv is None:
            continue
        excesses.append(wv["excess"])
        wm_list.append(wv)
        worst_mdd = max(worst_mdd, wv["mdd"])
        # vetoes (law)
        if wv["mdd"] > 15.0:
            vetoed = f"window MDD {wv['mdd']:.1f}%"
        if wv["bench_dn_mdd"] > 20.0 and wv["dn_mdd"] > 0.5 * wv["bench_dn_mdd"]:
            vetoed = f"crash-shield {wv['dn_mdd']:.1f} vs bench {wv['bench_dn_mdd']:.1f}"
    if vetoed:
        return -np.inf, vetoed
    mean_exc = float(np.mean(excesses))
    t_stat = float(np.mean(excesses) / (np.std(excesses, ddof=1) / np.sqrt(len(excesses)))) if len(excesses) > 2 else 0.0
    run_mdd = worst_mdd
    if run_mdd > 25.0:
        return -np.inf, f"run MDD {run_mdd:.1f}%"
    # out-penalty: time with |exposure| < 0.05
    time_out = float((np.abs(expo) < 0.05).mean() * 100)
    pen_out = out_penalty_pct(time_out)
    pen_mdd = mdd_penalty(run_mdd)
    # segment terms
    dn_ex = [w["strat_down"] - w["bench_down"] for w in wm_list]
    caps = [w["up_capture"] for w in wm_list if w["up_capture"] is not None]
    seg_dn = float(np.mean(dn_ex))
    seg_up = float(np.mean(caps)) if caps else 0.0
    # parsimony: count active specialists
    active = sum(1 for li in range(len(LANES)) for i in range(n_specialists) if abs(W[li][i]) > 0.02)
    par = 0.05 * max(active - 6, 0)
    score = (1.0 * mean_exc + 0.3 * max(t_stat, 0) + 0.3 * seg_dn + 0.3 * seg_up
             - pen_mdd - pen_out - par)
    return score, {"mean_excess": mean_exc, "t": t_stat, "seg_dn": seg_dn, "seg_up": seg_up,
                   "run_mdd": run_mdd, "time_out": time_out, "active": active,
                   "windows": wm_list}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3000)
    ap.add_argument("--label", default="blender_v1")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rets, names = load_specialists()
    bench = pd.read_csv(EXEC_CSV, parse_dates=["timestamp"], index_col="timestamp").sort_index()
    bench = bench.loc[rets.index[0]:]
    lane = regime_series(bench).loc[rets.index]
    lane_of_bar = lane.to_numpy()

    # monthly windows across the sealed span
    starts = pd.date_range("2021-04-01", "2026-06-01", freq="MS", tz="UTC")
    months = [(s, s + pd.DateOffset(months=1)) for s in starts]

    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
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
        score, det = evaluate(weights, rets, lane_of_bar, bench["close"], months, len(names))
        if score == -np.inf:
            return -50.0  # below any real score, visible-but-vetoed
        return score

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=args.seed))
    study.optimize(objective, n_trials=args.trials, show_progress_bar=False)

    # reconstruct best
    bp = study.best_params
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
    score, det = evaluate(weights, rets, lane_of_bar, bench["close"], months, len(names))

    out = {"label": args.label, "score": round(score, 3),
           "weights": {ln: {nm: round(float(w[i]), 3) for i, nm in enumerate(names) if abs(w[i]) > 0.02}
                        for ln, w in weights.items()},
           "details": {k: v for k, v in det.items() if k != "windows"},
           "windows": [{"month": str(s.date()), **{k: (round(v, 2) if isinstance(v, float) else v)
                     for k, v in w.items()}} for (s, e), w in zip(months, det["windows"])]}
    path = os.path.join(REPO, "tuner", "runs", f"{args.label}.json")
    json.dump(out, open(path, "w"), indent=1)
    print(f"BEST score {score:+.2f} | mean excess {det['mean_excess']:+.2f}% | t {det['t']:+.2f} | "
          f"seg_dn {det['seg_dn']:+.1f} | up_cap {det['seg_up']:+.2f} | MDD {det['run_mdd']:.1f}% | "
          f"out {det['time_out']:.0f}% | specialists {det['active']}")
    print("weights:", json.dumps(out["weights"]))
    print("->", path)


if __name__ == "__main__":
    main()
