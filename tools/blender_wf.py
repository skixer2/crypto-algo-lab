#!/usr/bin/env python3
"""blender_wf.py — WALK-FORWARD SELECTION for the blend (v3j). 2026-10-20.

Blender Law (RESEARCH_LEDGER 2026-10-19, JP-approved): "walk-forward selection
only — v3h/v3i were the last full-span breeds."

Design:
  - Rolling windows: train 12 months -> test 3 months, slide 3 months.
    Scheme region 2021-10 .. 2026-07-01 (full months only; the July-26 partial
    is never in aggregates). First test window comes after the first 12-month
    train (warmup): first test = [2022-10, 2023-01), last = [2026-04, 2026-07)
    -> 15 test windows (>= 12 required).
  - Per window: Optuna TPE (seeded, ~300 trials) selects lane weights +
    detector from the 48-series precomputed regime grid. Fitness = evaluate()
    on the TRAIN span only — semantics UNCHANGED (imported from tools.blender),
    just fewer months passed. g_anchor (crash-shield) re-anchored per window
    from TRAIN months only (no future data), frozen with the pick.
  - Warm start: window 0 enqueues the standing champion (v3i -> v3h -> v1b);
    window k>0 enqueues window k-1's exact best params as trial 0.
  - Frozen winner graded on its UNSEEN 3-month test span via evaluate()
    (canonical) + per-window flip-rent / relabel-invariance guards.
  - Stitched result: contiguous deployable equity path over all test months
    (ONE global shift=1 honest pairing; boundary rebalance fees charged;
    each window's weights first act one bar into its test span — conservative
    adoption lag). Stats via tools.stats_canonical conventions (canonical
    grade() when >= 8 stitched windows; same-arithmetic inline stats otherwise).
  - Winner guards on the final stitched result: flip-rent + relabel retention
    (same formulas/thresholds as blender.py) on stitched means; July-26 partial
    disclosed separately (latest frozen pick = the going-forward book).

This tool never modifies evaluate() semantics; tools/blender.py stays untouched.

Usage:
  python3 tools/blender_wf.py                       # full 15-window run
  python3 tools/blender_wf.py --smoke               # 1 window, end-to-end
  python3 tools/blender_wf.py --selftest            # month-subset sanity (b)
Output: <outdir>/<label>.json + <label>_equity.csv.gz (stitched path).
Default outdir: tuner/runs (repo); /tmp/wf_impl for --smoke.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from tools.blender import (EXEC_CSV, FEE, LANES, REPO, _renorm, evaluate,
                           flip_rent, load_specialists, relabel_invariance,
                           shield_anchor)
from tools.stats_canonical import _boundary_pct, grade, monthly_excesses

TRAIN_MONTHS, TEST_MONTHS, SLIDE = 12, 3, 3
FIRST_TRAIN = pd.Timestamp("2021-10-01", tz="UTC")
LAST_TEST_END = pd.Timestamp("2026-07-01", tz="UTC")  # full months only; July = disclosed partial
SEARCH_LANES = ("confirmed_bearish", "vol_compressed", "expansion")  # grind_down = cash (blender law)
DEFAULT_CHAMPS = ["blender_v3i.json", "blender_v3h.json", "blender_v1b.json"]


# ---------------------------------------------------------------- windows ----
def build_windows(first_train=FIRST_TRAIN, n_train=TRAIN_MONTHS, n_test=TEST_MONTHS,
                  slide=SLIDE, last_test_end=LAST_TEST_END):
    out, t = [], first_train
    while True:
        train_end = t + pd.DateOffset(months=n_train)
        test_end = train_end + pd.DateOffset(months=n_test)
        if test_end > last_test_end:
            break
        out.append({
            "train": [(t + pd.DateOffset(months=i), t + pd.DateOffset(months=i + 1)) for i in range(n_train)],
            "test": [(train_end + pd.DateOffset(months=i), train_end + pd.DateOffset(months=i + 1)) for i in range(n_test)],
        })
        t = t + pd.DateOffset(months=slide)
    return out


def month_starts(months):
    return [s for (s, _e) in months]


# ------------------------------------------------------------ search space ---
def load_detector_grid(rets):
    """48 precomputed lane-code series (v2.1 searchable dim), aligned to rets bars."""
    path = os.path.join(REPO, "data", "precompute", "regime_grid.npz")
    grid_codes, n_det, default_det = None, 0, 0
    if os.path.exists(path):
        z = np.load(path)
        gidx = pd.DatetimeIndex(z["index"].astype("int64"))
        col = gidx.asi8.searchsorted(pd.DatetimeIndex(rets.index).asi8)
        grid_codes = z["lanes"][:, col]
        meta = json.load(open(os.path.join(REPO, "data", "precompute", "regime_grid.json")))
        n_det = grid_codes.shape[0]
        for m in meta:  # router v2.2 defaults
            if (m["donchian"], m["confirm"], (m["vol_enter"], m["vol_exit"]),
                (m["grind_slope"], m["grind_confirm"])) == (192, 96, (0.75, 0.85), (96, 48)):
                default_det = m["i"]
                break
    return grid_codes, n_det, default_det


def weights_from_params(bp, names, default_det):
    """Reconstruct weights + detector from a trial param dict (mirrors blender.main)."""
    det = bp.get("detector", default_det)
    weights = {}
    for lane_name in SEARCH_LANES:
        w = np.zeros(len(names))
        for i, nm in enumerate(names):
            if bp.get(f"{lane_name[:3]}_{nm}", 0):
                w[i] = bp[f"w_{lane_name[:3]}_{nm}"]
        s = w.sum()
        if s > 1.0:
            w = w / s
        weights[lane_name] = w
    return weights, det


def params_from_weights(weights, det, names, default_det=0):
    """Inverse mapping for Optuna enqueue_trial (mirrors blender.main champion enqueue).
    Accepts champion-JSON form {lane: {name: w}} or array form {lane: np.array}."""
    if det is None:
        det = default_det
    params = {"detector": int(det)}
    for lane_name in SEARCH_LANES:
        lane_w = weights.get(lane_name, {})
        for i, nm in enumerate(names):
            w = lane_w.get(nm, 0.0) if isinstance(lane_w, dict) else float(lane_w[i])
            params[f"{lane_name[:3]}_{nm}"] = 1 if w else 0
            if w:
                params[f"w_{lane_name[:3]}_{nm}"] = float(w)
    return params


def weights_to_json(weights, names):
    return {ln: {nm: round(float(w[i]), 3) for i, nm in enumerate(names) if abs(w[i]) > 0.02}
            for ln, w in weights.items()}


def json_safe(o):
    if isinstance(o, dict):
        return {str(k): json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [json_safe(v) for v in o]
    if isinstance(o, np.floating):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, pd.Timestamp):
        return str(o)
    if isinstance(o, float):
        return None if o != o else o
    return o


# ------------------------------------------------------------ per-window WF --
def search_window(win, k, rets, names, POS, bench_close, grid_codes, n_det, default_det,
                  trials, seed, warm_params=None, champ_params=None):
    """Optuna TPE over lane weights x detector; fitness = evaluate() on TRAIN months only."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    train_months = win["train"]
    ga = shield_anchor(bench_close, train_months)  # data-anchored on TRAIN only

    def objective(trial):
        det = trial.suggest_categorical("detector", list(range(n_det))) if n_det > 1 else default_det
        weights = {}
        for lane_name in SEARCH_LANES:
            w = np.zeros(len(names))
            for i, nm in enumerate(names):
                on = trial.suggest_categorical(f"{lane_name[:3]}_{nm}", [0, 1])
                if on:
                    w[i] = trial.suggest_float(f"w_{lane_name[:3]}_{nm}", 0.0, 1.0)
            s = w.sum()  # long-only exposure cap (blender law; grind lane = cash)
            if s > 1.0:
                w = w / s
            weights[lane_name] = w
        score, _det = evaluate(weights, rets, grid_codes[det], bench_close, train_months,
                               len(names), pos_mat=POS, g_anchor=ga)
        return -50.0 if score == -np.inf else score  # below any real score, visible-but-vetoed

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=seed + k))
    if k == 0 and champ_params is not None:
        study.enqueue_trial(champ_params)   # standing champion guaranteed >= its train score
    if warm_params is not None:
        study.enqueue_trial(warm_params)    # previous window's best (walk-forward anchor)
    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    bp = study.best_params
    weights, det = weights_from_params(bp, names, default_det)
    score, train_det = evaluate(weights, rets, grid_codes[det], bench_close, train_months,
                                len(names), pos_mat=POS, g_anchor=ga)
    assert np.isfinite(score), f"window {k}: non-finite reconstructed train score"
    return {"k": k, "params": bp, "weights": weights, "detector": det, "train_score": score,
            "train_details": train_det, "g_anchor_train": ga,
            "best_value": float(study.best_value), "n_trials": trials}


def test_window(pick, win, rets, names, POS, bench_close):
    """Grade the FROZEN winner on its UNSEEN 3-month test span (canonical evaluate)."""
    lob, ga, test_months = pick["lob"], pick["g_anchor_train"], win["test"]
    ts, te = test_months[0][0], test_months[-1][1]
    _s_blk, blk = evaluate(pick["weights"], rets, lob, bench_close, [(ts, te)], len(names),
                           pos_mat=POS, g_anchor=ga)
    _s_mon, mon = evaluate(pick["weights"], rets, lob, bench_close, test_months, len(names),
                           pos_mat=POS, g_anchor=ga)
    excesses = [float(w["excess"]) for w in mon["windows"]]
    assert len(excesses) == TEST_MONTHS and np.isfinite(excesses).all(), \
        f"window {pick['k']}: NaN/missing test windows {excesses}"
    guards = {"flip_rent": flip_rent(pick["weights"], rets, lob, bench_close, test_months,
                                     len(names), POS, ga),
              "relabel_invariance": relabel_invariance(pick["weights"], rets, lob, bench_close,
                                                       test_months, len(names), POS, ga)}
    return {"excesses_pct": [_boundary_pct(e / 100.0) for e in excesses],
            "block_excess_pct": round(float(blk["mean_excess"]), 2),
            "block_strat_pct": round(float(blk["windows"][0]["strat"]), 2),
            "block_bench_pct": round(float(blk["windows"][0]["bench"]), 2),
            "block_mdd_pct": round(float(blk["windows"][0]["mdd"]), 2),
            "guards": guards}


# ---------------------------------------------------------------- stitching --
def stitch_equity(picks, wins, rets, POS, names, shift=1):
    """Contiguous deployable equity over all test bars, mirroring evaluate()'s bar
    arithmetic: lane-mask -> per-window weights, ONE global shift across the whole
    stitched span (honest pairing), netted turnover fees with prepend=0.0 at the
    stitched start -> initial deployment AND boundary rebalances are charged.
    Each window's weights first act one bar into its test span (conservative
    adoption lag). Returns (equity, net_exposure) indexed on stitched bars."""
    idx = rets.index
    in_test = np.zeros(len(idx), dtype=bool)
    win_id = np.full(len(idx), -1, dtype=np.int64)
    for pick, win in zip(picks, wins):
        ts, te = win["test"][0][0], win["test"][-1][1]
        m = (idx >= ts) & (idx < te)
        assert not in_test[m].any(), "test windows overlap — scheme bug"
        in_test[m] = True
        win_id[m] = pick["k"]
    bars = np.where(in_test)[0]
    assert len(bars) > 0 and np.all(np.diff(bars) == 1), \
        "test windows are not contiguous over the stitched span"

    lob_st = np.empty(len(bars), dtype=np.int64)
    w_st = np.zeros((len(bars), len(names)), dtype=np.float64)
    for pick, win in zip(picks, wins):
        sel = np.where(win_id[bars] == pick["k"])[0]
        lob_st[sel] = pick["lob"][bars[sel]]
        W = np.zeros((len(LANES), len(names)))
        for li, ln in enumerate(LANES):
            if ln in pick["weights"]:  # grind_down absent -> zeros (cash lane)
                W[li] = pick["weights"][ln]
        w_st[sel] = W[pick["lob"][bars[sel]]]

    rets_st = rets.to_numpy()[bars]
    pos_st = POS.to_numpy()[bars]
    if shift > 0:  # ONE global honest pairing: rets[t] carries labels decided at t-1
        lob_st = np.concatenate([lob_st[:shift], lob_st[:-shift]])
        w_st = np.vstack([w_st[:shift], w_st[:-shift]])
    w_ret = (w_st * rets_st).sum(axis=1)
    net_expo = (w_st * pos_st).sum(axis=1)
    turn = np.abs(np.diff(net_expo, prepend=0.0))
    port_ret = w_ret - FEE * turn
    eq = pd.Series(np.cumprod(1.0 + port_ret), index=idx[bars])
    return eq, pd.Series(net_expo, index=idx[bars])


def stitched_excess_by_shift(picks, wins, rets, POS, names, bench_close, st_months,
                             shifts=(0, 1, 2)):
    """Stitched mean excess per shift — inputs for the stitched-level guards."""
    out = {}
    for sh in shifts:
        eq, _ne = stitch_equity(picks, wins, rets, POS, names, shift=sh)
        ex = monthly_excesses(eq, bench_close, grid=st_months)
        out[sh] = {"mean_excess_pct": _boundary_pct(float(np.mean(ex)) / 100.0) if len(ex) else None,
                   "n": int(len(ex)),
                   "excesses_pct": [_boundary_pct(e / 100.0) for e in ex]}
    return out


def stitched_guards(shift_stats):
    """Same formulas/thresholds as blender.flip_rent / relabel_invariance, stitched."""
    s0 = shift_stats[0]["mean_excess_pct"] or 0.0
    s1 = shift_stats[1]["mean_excess_pct"] or 0.0
    s2 = shift_stats[2]["mean_excess_pct"] or 0.0
    share = (s0 - s1) / s0 if abs(s0) > 1e-9 else 0.0
    meaningful = s1 > 0.5
    retention = (s2 / s1) if meaningful else None
    return {"flip_rent": {"edge_if_samebar_pct": round(s0, 2), "edge_honest_pct": round(s1, 2),
                          "rent_share_pct": round(share * 100, 1) if meaningful else None,
                          "alarm": bool(meaningful and share > 0.25), "edge_negative": not meaningful},
            "relabel_invariance": {"edge_shift1_pct": round(s1, 2), "edge_shift2_pct": round(s2, 2),
                                   "retention": round(retention, 3) if retention is not None else None,
                                   "alarm": bool(meaningful and retention < 0.25),
                                   "edge_negative": not meaningful}}


def inline_stitched_stats(eq, bench_close, months):
    """stats_canonical arithmetic for < 8-month stitches (smoke): same formulas,
    without grade()'s 8-window floor assert."""
    starts = month_starts(months) if (months and isinstance(months[0], tuple)) else list(months)
    ex = monthly_excesses(eq, bench_close, grid=starts)
    mean_f = float(ex.mean()) if len(ex) else float("nan")
    std = float(ex.std(ddof=1)) if len(ex) > 1 else 0.0
    t = (mean_f / (std / np.sqrt(len(ex)))) if (len(ex) > 2 and std > 0) else None
    half = len(ex) // 2
    return {"n_windows": len(ex), "mean_excess_pct_mo": _boundary_pct(mean_f),
            "t": round(t, 2) if t is not None else None,
            "worst_window_pct": _boundary_pct(float(ex.min())) if len(ex) else None,
            "first_half_pct": _boundary_pct(float(ex[:half].mean())) if half else None,
            "second_half_pct": _boundary_pct(float(ex[half:].mean())) if half else None}


# --------------------------------------------------------------------- run ---
def find_champion():
    for f in DEFAULT_CHAMPS:
        p = os.path.join(REPO, "tuner", "runs", f)
        if os.path.exists(p):
            return json.load(open(p)), f
    return None, None


def run(args):
    t_start = time.time()
    rets, names, POS = load_specialists()
    bench = pd.read_csv(EXEC_CSV, parse_dates=["timestamp"], index_col="timestamp").sort_index()
    bench_close = bench.loc[rets.index[0]:]["close"]
    grid_codes, n_det, default_det = load_detector_grid(rets)
    assert grid_codes is not None, "regime grid required"
    wins = build_windows()
    if args.smoke:
        wins = wins[:1]
    if args.windows:
        wins = wins[:args.windows]
    print(f"WF scheme: {len(wins)} windows | train {TRAIN_MONTHS}mo -> test {TEST_MONTHS}mo "
          f"| slide {SLIDE}mo | region {wins[0]['train'][0][0].date()} .. {wins[-1]['test'][-1][1].date()}")
    print(f"pool: {len(names)} specialists | detector grid: {n_det} | trials/window: {args.trials}")

    champ, champ_file = (None, None) if args.no_champ else find_champion()
    champ_params = None
    if champ is not None:
        champ_params = params_from_weights(champ["weights"], champ.get("detector"), names,
                                           default_det=default_det)
        print(f"window-0 warm start: standing champion {champ_file} (detector {champ.get('detector')})")

    picks, win_records = [], []
    for k, win in enumerate(wins):
        t0 = time.time()
        warm = picks[-1]["params"] if picks else None
        pick = search_window(win, k, rets, names, POS, bench_close, grid_codes, n_det,
                             default_det, args.trials, args.seed, warm_params=warm,
                             champ_params=champ_params)
        pick["lob"] = grid_codes[pick["detector"]]
        grade_res = test_window(pick, win, rets, names, POS, bench_close)
        picks.append(pick)
        tr = pick["train_details"]
        rec = {"k": k,
               "train_span": [str(win["train"][0][0].date()), str(win["train"][-1][1].date())],
               "test_span": [str(win["test"][0][0].date()), str(win["test"][-1][1].date())],
               "detector": int(pick["detector"]), "g_anchor_train": round(pick["g_anchor_train"], 2),
               "train_fitness": {"score": round(pick["train_score"], 3),
                                 "mean_excess_pct_mo": round(float(tr["mean_excess"]), 2),
                                 "t": round(float(tr["t"]), 2), "seg_dn": round(float(tr["seg_dn"]), 2),
                                 "seg_up": round(float(tr["seg_up"]), 2),
                                 "run_mdd_pct": round(float(tr["run_mdd"]), 1),
                                 "time_out_pct": round(float(tr["time_out"]), 1),
                                 "active_specialists": int(tr["active"])},
               "weights": weights_to_json(pick["weights"], names),
               "test_grade": grade_res, "search_sec": round(time.time() - t0, 1)}
        win_records.append(rec)
        tg = grade_res
        fr, ri = tg["guards"]["flip_rent"], tg["guards"]["relabel_invariance"]
        print(f"[win {k:02d}/{len(wins)}] det {pick['detector']:2d} "
              f"| train score {pick['train_score']:+7.2f} "
              f"(exc {rec['train_fitness']['mean_excess_pct_mo']:+5.2f} t {rec['train_fitness']['t']:+5.2f}) "
              f"| test 3mo exc {tg['block_excess_pct']:+6.2f}% months {tg['excesses_pct']} "
              f"| rent {fr['rent_share_pct']}% ret {ri['retention']} | {rec['search_sec']}s")

    # ---- stitched result over all test months ----
    eq, net_expo = stitch_equity(picks, wins, rets, POS, names, shift=1)
    st_months = [s for w in wins for s in month_starts(w["test"])]
    ex = monthly_excesses(eq, bench_close, grid=st_months)
    assert len(ex) == len(st_months) and np.isfinite(ex).all(), "NaN/missing stitched windows"
    shift_stats = stitched_excess_by_shift(picks, wins, rets, POS, names, bench_close, st_months)
    guards_st = stitched_guards(shift_stats)
    if len(st_months) >= 8:
        canon = grade(eq, bench_close, name=args.label, pos=net_expo, months_mask=st_months)
        stitched_stats = {"canonical_grade": canon, "stitched_months": len(st_months),
                          "excess_series_pct": [_boundary_pct(e / 100.0) for e in ex]}
    else:
        stitched_stats = {"canonical_grade": None,
                          "canonical_skipped": "fewer than 8 stitched windows (smoke)",
                          "inline_stats": inline_stitched_stats(eq, bench_close, st_months),
                          "stitched_months": len(st_months),
                          "excess_series_pct": [_boundary_pct(e / 100.0) for e in ex]}
    stitched_stats["guards"] = guards_st
    stitched_stats["shift_sweep"] = shift_stats

    # July-26 partial, disclosed separately: the LATEST frozen pick (going-forward book)
    last = picks[-1]
    july_ts, july_te = pd.Timestamp("2026-07-01", tz="UTC"), pd.Timestamp("2026-07-28", tz="UTC")
    _s, jm = evaluate(last["weights"], rets, last["lob"], bench_close,
                      [(july_ts, july_te)], len(names), pos_mat=POS, g_anchor=last["g_anchor_train"])
    july_disclosure = {"pick_window": last["k"], "test_span_of_pick": win_records[-1]["test_span"],
                       "july26_partial_excess_pct": round(float(jm["mean_excess"]), 2)}

    # cross-check: stitched per-window excess vs canonical evaluate() per-window excess
    diffs = []
    for win, rec in zip(wins, win_records):
        s, e = win["test"][0][0], win["test"][-1][1]
        wv = eq[(eq.index >= s) & (eq.index < e)]
        strat = (float(wv.iloc[-1]) / float(wv.iloc[0]) - 1) * 100
        b = bench_close[(bench_close.index >= s) & (bench_close.index < e)]
        benchr = (float(b.iloc[-1]) / float(b.iloc[0]) - 1) * 100
        diffs.append(abs((strat - benchr) - rec["test_grade"]["block_excess_pct"]))
    xcheck = {"max_abs_block_excess_diff_pct": round(float(max(diffs)), 4),
              "note": "stitched adds boundary rebalance fee + 1-bar adoption lag per window; "
                      "canonical per-window grades do not. Diff = disclosed convention delta, "
                      "expected small (hard assert < 0.5%)."}
    assert max(diffs) < 0.5, f"stitched vs canonical per-window divergence {max(diffs):.3f}% — investigate"

    no_nan = bool(np.isfinite(ex).all()
                  and all(np.isfinite(r["test_grade"]["excesses_pct"]).all() for r in win_records)
                  and all(np.isfinite(r["train_fitness"]["mean_excess_pct_mo"]) for r in win_records))

    out = {"label": args.label, "generated": pd.Timestamp.now(tz="UTC").isoformat(),
           "law": "Blender Law 2026-10-19: walk-forward selection only",
           "scheme": {"train_months": TRAIN_MONTHS, "test_months": TEST_MONTHS, "slide_months": SLIDE,
                      "first_train": str(wins[0]["train"][0][0].date()),
                      "last_test_end": str(wins[-1]["test"][-1][1].date()),
                      "n_windows": len(wins), "trials_per_window": args.trials, "seed": args.seed,
                      "champion_warm_start": champ_file,
                      "conventions": {
                          "fitness": "evaluate() on train months only (semantics unchanged)",
                          "g_anchor": "shield_anchor on train months only, frozen with the pick",
                          "stitched": "one global shift=1; boundary rebalance fees charged; "
                                      "weights adopt one bar into their test span",
                          "july26": "disclosed separately, never in aggregates"}},
           "windows": win_records,
           "stitched": stitched_stats,
           "july26_partial_disclosure": july_disclosure,
           "checks": {"no_nan_windows": no_nan, "stitched_vs_canonical_xcheck": xcheck},
           "run_meta": {"elapsed_sec": round(time.time() - t_start, 1),
                        "stitched_equity": os.path.basename(args.equity_path)}}

    os.makedirs(os.path.dirname(os.path.abspath(args.out_path)), exist_ok=True)
    with open(args.out_path, "w") as f:
        json.dump(json_safe(out), f, indent=1)
    eq.rename("equity").to_frame().assign(net_exposure=net_expo.round(6)).to_csv(
        args.equity_path, compression="gzip", index_label="timestamp")

    mean_pct = float(np.mean(ex)) * 100.0
    print(f"STITCHED ({len(st_months)} months) | mean excess {mean_pct:+.2f}%/mo "
          f"| rent {guards_st['flip_rent']['rent_share_pct']}% "
          f"(alarm {guards_st['flip_rent']['alarm']}) "
          f"| retention {guards_st['relabel_invariance']['retention']} "
          f"(alarm {guards_st['relabel_invariance']['alarm']})")
    print(f"July-26 partial (latest pick, disclosed): "
          f"{july_disclosure['july26_partial_excess_pct']:+.2f}%")
    print(f"checks: no_nan_windows={no_nan} | xcheck max block diff "
          f"{xcheck['max_abs_block_excess_diff_pct']}%")
    print(f"-> {args.out_path}")
    print(f"-> {args.equity_path}")
    return out


# ---------------------------------------------------------------- selftest ---
def selftest():
    """Constraint (b): evaluate-on-train-months == full-grid evaluate on those months.

    Fixed weight vectors (v3i + v3h champions + a synthetic dense vector), three
    train windows each, every window metric compared. Tolerance 1e-9.
    Also previews the no-NaN guard on the full grid."""
    rets, names, POS = load_specialists()
    bench = pd.read_csv(EXEC_CSV, parse_dates=["timestamp"], index_col="timestamp").sort_index()
    bench_close = bench.loc[rets.index[0]:]["close"]
    grid_codes, n_det, default_det = load_detector_grid(rets)
    starts = pd.date_range("2021-04-01", "2026-06-01", freq="MS", tz="UTC")
    months_full = [(s, s + pd.DateOffset(months=1)) for s in starts]
    ga_full = shield_anchor(bench_close, months_full)

    cases = []
    for cf in ["blender_v3i.json", "blender_v3h.json"]:
        c = json.load(open(os.path.join(REPO, "tuner", "runs", cf)))
        W = _renorm({ln: np.array([c["weights"].get(ln, {}).get(nm, 0.0) for nm in names])
                     for ln in SEARCH_LANES})
        cases.append((f"{cf} (det {c['detector']})", W, grid_codes[c["detector"]]))
    rng = np.random.default_rng(11)  # synthetic dense, non-champion
    W = _renorm({ln: rng.random(len(names)) * (rng.random(len(names)) > 0.5) for ln in SEARCH_LANES})
    cases.append((f"synthetic_dense (det {default_det})", W, grid_codes[default_det]))

    wins = build_windows()
    worst, n_checked = 0.0, 0
    for label, W, lob in cases:
        _s, full = evaluate(W, rets, lob, bench_close, months_full, len(names),
                            pos_mat=POS, g_anchor=ga_full)
        assert np.isfinite([w["excess"] for w in full["windows"]]).all(), f"{label}: NaN excesses"
        full_by_start = {s: w for (s, _e), w in zip(months_full, full["windows"])}
        for k in (0, len(wins) // 2, len(wins) - 1):
            train_months = wins[k]["train"]
            ga = shield_anchor(bench_close, train_months)
            _s2, sub = evaluate(W, rets, lob, bench_close, train_months, len(names),
                                pos_mat=POS, g_anchor=ga)
            for (s, _e), w_sub in zip(train_months, sub["windows"]):
                w_full = full_by_start[s]
                for key in w_full:
                    if w_full[key] is None or w_sub[key] is None:
                        assert w_full[key] is None and w_sub[key] is None, \
                            f"{label} k={k} {key}: None mismatch"
                        continue
                    if isinstance(w_full[key], (int, float)) and not isinstance(w_full[key], bool):
                        d = abs(float(w_full[key]) - float(w_sub[key]))
                        worst = max(worst, d)
                        n_checked += 1
                        assert d <= 1e-9, \
                            f"{label} k={k} month {s.date()} metric '{key}' diff {d:.3e} > 1e-9"
        print(f"  case {label:28s} -> 3 train windows x 12 months x metrics: OK")
    print(f"SELFTEST PASS — {n_checked} metric comparisons, "
          f"max |train-subset - full-grid| = {worst:.3e} (tolerance 1e-9)")
    print(f"  scheme: {len(wins)} windows | first test {wins[0]['test'][0][0].date()}.."
          f"{wins[0]['test'][-1][1].date()} | last test {wins[-1]['test'][0][0].date()}.."
          f"{wins[-1]['test'][-1][1].date()}")
    return worst


def main():
    ap = argparse.ArgumentParser(description="Walk-forward blend selection (Blender Law compliant)")
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--label", default="blender_v3j_wf")
    ap.add_argument("--out", default=None, help="output dir (default tuner/runs; /tmp/wf_impl for --smoke)")
    ap.add_argument("--windows", type=int, default=None, help="limit number of windows (debug)")
    ap.add_argument("--smoke", action="store_true", help="single window, end-to-end")
    ap.add_argument("--selftest", action="store_true", help="month-subset sanity check (constraint b)")
    ap.add_argument("--no-champ", action="store_true", help="skip standing-champion enqueue")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    outdir = args.out or ("/tmp/wf_impl" if args.smoke else os.path.join(REPO, "tuner", "runs"))
    args.out_path = os.path.join(outdir, f"{args.label}.json")
    args.equity_path = os.path.join(outdir, f"{args.label}_equity.csv.gz")
    run(args)


if __name__ == "__main__":
    main()
