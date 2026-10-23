#!/usr/bin/env python3
"""alpha_076a ETH HOLDOUT READOUT — the irreversible read (operator-directed).

Pre-registered (RESEARCH_LEDGER 2026-10-23 15:0x, JP plan of record 13:13 UTC;
both per-asset portability legs no-pass -> holdout path fires):

  DEFINITION : holdout = post-GRID segment of the ETH cache, 2026-07-01 ->
               2026-09-28. Windows (stats_canonical machinery, [s, e) half-open):
                 Jul: ruler JULY tuple [2026-07-01, 2026-07-28) — 28-day PARTIAL,
                      caveat: defined in blend era, never quoted for 076 family.
                 Aug: [2026-08-01, 2026-09-01) — full month.
                 Sep: [2026-09-01, 2026-09-28) — partial to cache end.
               The 63-month GRID (2021-04..2026-06) is the exam window: NOT
               re-graded, NOT touched, nothing adjusted based on it.
  BAR        : PASS = holdout mean excess > 0 AND worst holdout month >= -40
               (same floor logic as Entry Exam v3.2 floor 2: worst ABSOLUTE
               strat month, not excess). Reported PASS/FAIL per item. No
               interpretation beyond the bar, no tuning, no variants, no re-runs.
  RUN        : frozen alpha_076a verbatim (md5 137ce302a6c4, params == manifest),
               exact portability-076a engine path — this script IMPORTS
               tools/portability_076a.py and calls its engine_run /
               funding plumbing / netting_on_curve unchanged; END extended to
               the cache end (2026-09-28). ETH production funding convention:
               gate = binance settled proxy (build_fund_pct), cost = binance+bybit
               elementwise avg; fee 0.0008 netted on |dpos|; funding at 00/08/16
               bars. Headline book = netfund; feefree/netted disclosed.
  GATE FIRST : feefree full-curve grade MUST reproduce manifest production grade
               (+2.89 t1.96 DD-46.2 worst-abs -18.47) — abort otherwise, before
               any holdout number is computed.

  SEAL       : the engine path enforces tuner/holdout.py SEAL_DATE 2026-07-28.
               This readout is the "final holdout verification run" the seal was
               built for; bypass follows the seal's own documented discipline:
               tuner/.holdout_final_run created (logged) -> final_run=True ->
               deleted immediately after the single engine run (one-shot;
               guard re-arms itself: it checks the flag on disk). Creation and
               deletion timestamps are recorded in results.json and REPORT.md.

  Readout    : stats_canonical machinery ONLY (sc._win_ret / monthly-excess
               arithmetic / sc.continuous_dd / grade time-in convention /
               _boundary_pct percent boundary with audit trail) applied to the
               holdout windows. Activity sanity so a lucky flat line cannot fake
               a pass: time-in, funding-gate states on holdout bars, latch
               entries/exits.

Outputs: reports/holdout_076a/results.json, curves/*.csv.gz, REPORT.md
         (written by hand from this script's printed output).
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

REPO = "/home/node/.openclaw/workspace/crypto"
sys.path.insert(0, REPO)
os.chdir(REPO)

from tools.stats_canonical import (grade, load_bench, load_curve,  # noqa: E402
                                   _boundary_pct, _win_ret, continuous_dd)
import tools.stats_canonical as sc                                  # noqa: E402
import tools.portability_076a as P76                                # noqa: E402  (exact engine path)
from tuner.alpha_orchestrator import build_fund_pct                 # noqa: E402
from tuner import holdout as TH                                     # noqa: E402
import tuner.alpha_orchestrator as AO                               # noqa: E402

OUT = os.path.join(REPO, "reports/holdout_076a")
CUR = os.path.join(OUT, "curves")
os.makedirs(CUR, exist_ok=True)

HO_START = pd.Timestamp("2026-07-01", tz="UTC")
HO_END = pd.Timestamp("2026-09-28", tz="UTC")          # cache end; windows [s, e)
END_STR = "2026-09-28T00:00:00+00:00"
WINDOWS = [
    ("2026-07_partial_JULY_tuple", sc.JULY[0], sc.JULY[1]),
    ("2026-08", pd.Timestamp("2026-08-01", tz="UTC"), pd.Timestamp("2026-09-01", tz="UTC")),
    ("2026-09_to_cache_end", pd.Timestamp("2026-09-01", tz="UTC"), HO_END),
]

T0 = time.time()
def log(*a):
    print(f"[{time.time()-T0:6.0f}s]", *a, flush=True)


def pct_with_audit(x, audit):
    """Strict percent boundary (sc._boundary_pct); out-of-band values recorded,
    never silently accepted (portability GuardRelease precedent, disclosed)."""
    p = float(x) * 100.0
    if not (-100.0 < p < 1000.0):
        audit.append(round(p, 2))
    return round(p, 2)


def holdout_stats(eq, bench, pos, name, audit):
    """Pre-registered readout, stats_canonical machinery only."""
    per_window = []
    exs, strats, benches = [], [], []
    for wname, s, e in WINDOWS:
        r_s, r_b = _win_ret(eq, s, e), _win_ret(bench, s, e)
        assert r_s is not None and r_b is not None, f"window {wname} ungradeable"
        exs.append(r_s - r_b)
        strats.append(r_s)
        benches.append(r_b)
        per_window.append({
            "window": wname, "start": str(s), "end": str(e),
            "strat_pct": pct_with_audit(r_s, audit), "bench_pct": pct_with_audit(r_b, audit),
            "excess_pct": pct_with_audit(r_s - r_b, audit),
            "strat_frac": round(r_s, 6), "bench_frac": round(r_b, 6),
            "excess_frac": round(r_s - r_b, 6)})
    seg = eq[eq.index >= HO_START]
    pos_seg = pos[pos.index >= HO_START]
    bseg = bench[bench.index >= HO_START]
    prev = pos.shift(1)
    in_win = pos.index >= HO_START
    entries = int(((prev == 0) & (pos != 0))[in_win].sum())
    exits = int(((prev != 0) & (pos == 0))[in_win].sum())
    carried_in = bool(pos[pos.index < HO_START].iloc[-1] != 0) if (pos.index < HO_START).any() else False
    return {
        "book": name,
        "windows": per_window,
        "mean_excess_pct": pct_with_audit(float(np.mean(exs)), audit),
        "mean_excess_frac": round(float(np.mean(exs)), 6),
        "worst_absolute_month_pct": pct_with_audit(min(strats), audit),
        "worst_absolute_month_frac": round(min(strats), 6),
        "worst_excess_pct": pct_with_audit(min(exs), audit),
        "best_excess_pct": pct_with_audit(max(exs), audit),
        "continuous_dd_pct_in_holdout": continuous_dd(seg),
        "bench_continuous_dd_pct_in_holdout": continuous_dd(bseg),
        "time_in_pct": round(float((pos_seg.abs() > 0.05).mean()) * 100.0, 1),
        "latch_entries_in_holdout": entries,
        "latch_exits_in_holdout": exits,
        "carried_in_position_at_holdout_start": carried_in,
    }


def main():
    R = {
        "run": "alpha_076a ETH HOLDOUT READOUT (the seal) — operator-directed, one-shot",
        "date": "2026-10-23",
        "definition": "post-GRID segment of the ETH cache 2026-07-01 -> 2026-09-28; "
                      "Jul = ruler JULY tuple partial [07-01, 07-28); Aug full; "
                      "Sep partial to cache end [09-01, 09-28). GRID 2021-04..2026-06 "
                      "not re-graded, not touched.",
        "bar_pre_registered": "PASS = holdout mean excess > 0 AND worst holdout "
                              "(absolute, strat) month >= -40",
        "engine": "tools/portability_076a.py path imported verbatim (engine_run, "
                  "funding plumbing, netting_on_curve); END extended to cache end; "
                  "decide@close fill@next-open, 2x rails 50/50 (effectively off), "
                  "allow_shorts=False, engine fee=0.0, warmup CLOSED",
        "costs": "headline netfund: fee 0.0008 netted on |dpos| + funding at "
                 "00/08/16 UTC bars (ETH production convention: gate binance "
                 "settled proxy, cost binance+bybit avg)",
        "ruler": "tools/stats_canonical machinery on holdout windows; bench = "
                 "same-asset buy-hold close",
    }

    # ── frozen-asset guards (same as portability) ────────────────────────
    R["formula_md5"] = P76.snapshot_formula()
    assert R["formula_md5"] == "137ce302a6c4", f"formula drift: {R['formula_md5']}"
    R["params_frozen"] = P76.check_manifest()
    log("formula md5", R["formula_md5"], "; params == manifest:",
        json.dumps(R["params_frozen"]))

    # ── holdout seal: the designed one-shot bypass, auditable on disk ────
    assert not os.path.exists(TH._FLAG_PATH), \
        "holdout final-run flag already exists — another authorization in flight; abort"
    flag_created = TH.authorize_final_run()
    R["seal"] = {"seal_date": str(TH.SEAL_DATE), "flag": flag_created,
                 "flag_created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "discipline": "one-shot: flag deleted immediately after the single "
                               "engine run; guard re-arms (checks flag on disk)"}
    log("SEAL: final-run flag created (one-shot authorization, logged):", flag_created)
    _real_guard = TH.guard_data_end
    AO._holdout_guard = lambda end, final_run=False: _real_guard(end, final_run=True)

    # ── ONE canonical run, full span incl. holdout ───────────────────────
    P76.END = END_STR  # extend the portability span to the cache end (only delta)
    log("engine run ETH, START", P76.START, "-> END", P76.END, "(seal crossed, authorized)")
    try:
        eq_free, pos = P76.engine_run(P76.ASSETS["ETH"])
    finally:
        if os.path.exists(TH._FLAG_PATH):
            os.remove(TH._FLAG_PATH)
            R["seal"]["flag_deleted_at_utc"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            log("SEAL: flag deleted — holdout re-sealed")
    assert eq_free is not None and len(eq_free) > 0, "engine run failed"
    assert eq_free.index.max() >= pd.Timestamp("2026-09-27", tz="UTC"), \
        "curve does not reach the holdout end"
    R["seal"]["engine_run_executed_once"] = True

    bench = load_bench(P76.ASSETS["ETH"]["csv"])  # full cache close (buy-hold)

    # ── VALIDATION GATE FIRST: feefree full-curve == manifest production ─
    g_ff = grade(eq_free, bench, "076a_ETH_feefree_fullcurve_holdoutrun", pos=pos)
    man = json.load(open(os.path.join(REPO, "data/precompute/manifest.json")))
    mg = man["alpha_076a"]["grade_fee_free"]
    gate = {
        "manifest_grade": mg,
        "run_grade": {k: (float(g_ff[k]) if g_ff[k] is not None else None) for k in
                      ("mean_excess_pct_mo", "t", "continuous_dd_pct",
                       "worst_absolute_month_pct", "july26_partial_pct", "time_in_pct")},
        "checks": {
            "mean_exc": bool(g_ff["mean_excess_pct_mo"] == mg["mean_exc"]),
            "t": bool(g_ff["t"] == mg["t"]),
            "dd": bool(g_ff["continuous_dd_pct"] == mg["dd"]),
            "worst_abs": bool(g_ff["worst_absolute_month_pct"] == mg["worst_abs_month"]),
        },
    }
    gate["PASS"] = all(gate["checks"].values())
    R["validation_gate"] = gate
    log("VALIDATION GATE:", "PASS" if gate["PASS"] else "FAIL", json.dumps(gate["run_grade"]))
    if not gate["PASS"]:
        json.dump(R, open(os.path.join(OUT, "results.json"), "w"), indent=1)
        log("ABORT: extended-curve feefree grade != manifest production grade. "
            "No holdout numbers computed. results.json (gate only) written.")
        sys.exit(2)

    # diagnostic (not the gate): pre-seal positions vs the stored portability curve
    try:
        pos_st = pd.read_csv(os.path.join(REPO, "reports/portability_076a/curves/"
                                          "076a_ETH_pos.csv.gz"), index_col=0)
        pos_st.index = pd.to_datetime(pos_st.index, utc=True, format="ISO8601")
        overlap = pos_st.index.intersection(pos.index)
        agree = float((pos_st["pos"].reindex(overlap).fillna(0.0).values
                       == pos.reindex(overlap).fillna(0.0).values).mean()) * 100
        R["diagnostic_pos_agreement_vs_portability_pct"] = round(agree, 4)
        log("diagnostic: pre-seal position agreement vs portability curve:", agree)
    except Exception as e:  # diagnostic only — never blocks the readout
        R["diagnostic_pos_agreement_vs_portability_pct"] = f"unavailable: {e}"

    # ── costs (ETH production convention, portability plumbing verbatim) ─
    x = pd.read_csv(P76.ASSETS["ETH"]["csv"])
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
    x = x[(x.timestamp >= pd.Timestamp(P76.START))
          & (x.timestamp <= HO_END)].reset_index(drop=True)
    x.index = x["timestamp"]
    fund = P76.funding_cost_buckets(P76.ASSETS["ETH"])
    fr_bar = P76.fund_to_bars(x, fund)
    eq_nfund = P76.netting_on_curve(eq_free, pos, fr_bar, eq_free.index, fund=True)
    eq_net = P76.netting_on_curve(eq_free, pos, fr_bar, eq_free.index, fund=False)

    # ── gate states on holdout bars (activity sanity) ────────────────────
    df_full = pd.read_csv(P76.ASSETS["ETH"]["csv"], parse_dates=["timestamp"],
                          index_col="timestamp")
    df_full.sort_index(inplace=True)
    fp = build_fund_pct(df_full, "binance", P76.ASSETS["ETH"]["symbol"])
    fp_ho = fp.reindex(pos.index[pos.index >= HO_START])
    open_ = int((fp_ho < 0.7).sum()); closed = int((fp_ho >= 0.7).sum())
    nan_ = int(fp_ho.isna().sum()); n = len(fp_ho)
    R["gate_states_holdout"] = {
        "definition": "fund_pct (30d rolling pctl-rank, binance settled proxy) on "
                      "holdout decision bars; gate open = fund_pct < 0.7 (entry "
                      "eligible); gate applies at ENTRY only, exit never gated",
        "bars": n,
        "open_pct": round(open_ / n * 100.0, 1),
        "closed_pct": round(closed / n * 100.0, 1),
        "nan_pct": round(nan_ / n * 100.0, 1),
        "fund_pct_mean": round(float(fp_ho.mean()), 3),
        "fund_pct_min": round(float(fp_ho.min()), 3),
        "fund_pct_max": round(float(fp_ho.max()), 3),
    }

    # ── THE READOUT (headline netfund; variants disclosed, not graded) ───
    audit = []
    R["holdout_netfund"] = holdout_stats(eq_nfund, bench, pos,
                                         "netfund (fee+funding, headline)", audit)
    R["holdout_feefree"] = holdout_stats(eq_free, bench, pos, "feefree (disclosed)", audit)
    R["holdout_netted"] = holdout_stats(eq_net, bench, pos, "netted fees only (disclosed)", audit)
    R["percent_boundary_audit_out_of_band"] = audit or None

    hn = R["holdout_netfund"]
    R["bar_verdict"] = {
        "mean_excess_gt_0": "PASS" if hn["mean_excess_pct"] > 0 else "FAIL",
        "worst_abs_month_gte_minus40":
            "PASS" if hn["worst_absolute_month_pct"] >= -40.0 else "FAIL",
    }
    R["bar_verdict"]["HOLDOUT"] = ("PASS" if "FAIL" not in R["bar_verdict"].values()
                                   else "FAIL")

    # ── curves ───────────────────────────────────────────────────────────
    eq_nfund.to_csv(os.path.join(CUR, "076a_ETH_holdout_netfund.csv.gz"),
                    compression="gzip")
    eq_free.to_csv(os.path.join(CUR, "076a_ETH_holdout_feefree.csv.gz"),
                   compression="gzip")
    eq_net.to_csv(os.path.join(CUR, "076a_ETH_holdout_netted.csv.gz"),
                  compression="gzip")
    pos.to_frame("pos").to_csv(os.path.join(CUR, "076a_ETH_holdout_pos.csv.gz"),
                               compression="gzip")

    json.dump(R, open(os.path.join(OUT, "results.json"), "w"), indent=1)

    # ── report-ready print ───────────────────────────────────────────────
    log("=== HOLDOUT READOUT (headline: netfund) ===")
    for w in hn["windows"]:
        log(f"  {w['window']}: strat {w['strat_pct']:+.2f}%  bench {w['bench_pct']:+.2f}%"
            f"  excess {w['excess_pct']:+.2f}%")
    log(f"  mean excess      : {hn['mean_excess_pct']:+.2f}%/mo  (bar > 0 -> "
        f"{R['bar_verdict']['mean_excess_gt_0']})")
    log(f"  worst ABS month  : {hn['worst_absolute_month_pct']:+.2f}%  (bar >= -40 -> "
        f"{R['bar_verdict']['worst_abs_month_gte_minus40']})")
    log(f"  worst excess     : {hn['worst_excess_pct']:+.2f}%   best excess "
        f"{hn['best_excess_pct']:+.2f}%")
    log(f"  DD within holdout: {hn['continuous_dd_pct_in_holdout']}%   "
        f"(bench {hn['bench_continuous_dd_pct_in_holdout']}%)")
    log(f"  time-in          : {hn['time_in_pct']}%   entries {hn['latch_entries_in_holdout']}"
        f"  exits {hn['latch_exits_in_holdout']}   carried-in {hn['carried_in_position_at_holdout_start']}")
    log(f"  gate states      : open {R['gate_states_holdout']['open_pct']}% / closed "
        f"{R['gate_states_holdout']['closed_pct']}% / nan {R['gate_states_holdout']['nan_pct']}%"
        f"  (fund_pct mean {R['gate_states_holdout']['fund_pct_mean']})")
    log(f"  disclosed books  : feefree mean {R['holdout_feefree']['mean_excess_pct']:+.2f} "
        f"worst_abs {R['holdout_feefree']['worst_absolute_month_pct']:+.2f}; "
        f"netted mean {R['holdout_netted']['mean_excess_pct']:+.2f} "
        f"worst_abs {R['holdout_netted']['worst_absolute_month_pct']:+.2f}")
    log(f"=== BAR VERDICT: {R['bar_verdict']['HOLDOUT']} ===")
    log("DONE -> reports/holdout_076a/results.json + curves/")


if __name__ == "__main__":
    main()
