#!/usr/bin/env python3
"""alpha_076c PRE-REGISTERED PILOT (spec: reports/router_nn_ideas_20261022/REPORT.md §3, frozen 2026-10-22).

v2 — collision-hardened: isolated scratch (/tmp/z076c_sub/), formula template
snapshotted once + content asserts on every derived variant (a concurrent
process clobbered /tmp/pilot076c formula files during the v1 run).

Battery (all grading via tools.stats_canonical.grade ONLY):
  a. canonical grade: 076c engine curve (fee=0.0 pool convention) — fee-free,
     netted-fees (0.0008x|dpos|), net-of-costs (+avg funding at 8h boundaries) —
     vs alpha_076a same path.
  b. jitter: 076c BTC window {25.5,34.5}d x thr {0.90,1.00,1.10} (engine);
     alpha_076a jitter: buf {0.85,1.15}, N {163,221}, gate {0.5,0.8} (engine).
  c. shift-2 retention for 076c.
  d. anchored exam v3.2 soft scores (theta 0.598, sigma 0.22) 076c vs 076a.
Plus: bar-arithmetic cross-check (compose_portfolio law, entry-gated state
machine, fees+funding) vs the 2026-10-22 ledger reference +3.16 t1.53.
"""
import os, sys, json, time, hashlib
import numpy as np
import pandas as pd

REPO = "/home/node/.openclaw/workspace/crypto"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.stats_canonical import grade, load_bench, load_curve, monthly_excesses, bench_monthly, sigma_m, soft_scores, calibrate_theta
from tuner.alpha_orchestrator import run_backtest, _fund_pct_for
from models.wq_alpha_miner import WQAlphaParams
from models.wq_alpha_fast import prepare_fast_context
from calibrate import (load_exec, load_funding_avg, fund_to_bars, latch, sim_curve,
                       bench_close, btc_mom_series, netting_on_curve, EX, SEAL, FEE)

OUT = os.path.join(REPO, "reports/alpha_076c_pilot")
RES = os.path.join(OUT, "results")
CUR = os.path.join(OUT, "curves")
SCRATCH = "/tmp/z076c_sub"      # collision-isolated scratch (twin-proof)
os.makedirs(RES, exist_ok=True)
os.makedirs(CUR, exist_ok=True)
os.makedirs(SCRATCH, exist_ok=True)
START = "2021-01-01T00:00:00+00:00"
END = "2026-07-28T00:00:00+00:00"
KEYS = ("mean_excess_pct_mo", "t", "worst_window_pct", "best_window_pct", "first_half_pct",
        "second_half_pct", "concentration", "neg_windows", "n_windows", "continuous_dd_pct",
        "july26_partial_pct", "time_in_pct", "worst_absolute_month_pct")

T0 = time.time()
def log(*a):
    print(f"[{time.time()-T0:6.0f}s]", *a, flush=True)

R = {}


def snapshot(path, markers):
    src = open(path).read()
    for m in markers:
        assert m in src, f"marker missing in {path}: {m}"
    return src, hashlib.md5(src.encode()).hexdigest()[:12]


def write_variant(name, src, must_contain):
    p = os.path.join(SCRATCH, name)
    with open(p, "w") as f:
        f.write(src)
    back = open(p).read()
    for m in must_contain:
        assert m in back, f"variant {name} lost marker {m} (clobber?)"
    return p


# ── engine runs ───────────────────────────────────────────────────────
def engine_run(formula_path, btc_mom=None, fund_pctl=0.7, tag=""):
    """Production harness: fast path, fee=0.0 pool convention, full span,
    allow_shorts=False (the exact alpha_076a production recipe)."""
    ctx = prepare_fast_context(EX, None, formula_path)
    if ctx.fund_pct is None:
        ctx.fund_pct = _fund_pct_for(EX, "binance")
    ctx.btc_mom = btc_mom
    p = WQAlphaParams(
        formula_path=formula_path, long_threshold=0.5, short_threshold=0.55,
        signal_smoothing=1, atr_period=14, atr_stop_mult=50.0, atr_take_mult=50.0,
        max_position_pct=1.0, warmup_candles=100, use_bias_filter=False,
        signal_exit_threshold=0.5, use_funding_gate=True, funding_gate_pctl=fund_pctl,
        funding_input="binance", funding_gate_mode="formula",
        use_btc_mom_gate=btc_mom is not None)
    eq = run_backtest(p, "ETH/USDT", "15m", "15m", {"15m": EX}, START, END,
                      ctx=ctx, allow_shorts=False, fee=0.0)
    if eq is None:
        raise RuntimeError(f"engine run failed: {tag}")
    t = pd.to_datetime(eq["timestamp"], utc=True)
    eqs = pd.Series(eq["equity"].astype(float).values, index=t)
    pv = eq["position"]
    if pv.dtype == object or str(pv.dtype) in ("string", "str") or pv.map(type).eq(str).any():
        pv = pv.map({"long": 1.0, "short": -1.0}).fillna(0.0)
    poss = pd.Series(pv.astype(float).values, index=t)
    return eqs, poss


def three_books(eq_free, pos, x_index, fr_bar, bench, name):
    eq_nf = netting_on_curve(eq_free, pos, fr_bar, x_index, fund=False)
    eq_nfund = netting_on_curve(eq_free, pos, fr_bar, x_index, fund=True)
    dpos_mo = FEE * pos.diff().abs().fillna(0.0).resample("MS").sum().mean() * 100
    g_ff = grade(eq_free, bench, f"{name}_feefree", pos=pos)
    g_nf = grade(eq_nf, bench, f"{name}_netted", pos=pos)
    g_nfund = grade(eq_nfund, bench, f"{name}_netfund", pos=pos)
    return ({k: g_ff[k] for k in KEYS},
            {k: g_nf[k] for k in KEYS},
            {k: g_nfund[k] for k in KEYS},
            round(float(dpos_mo), 2),
            eq_nfund)


def main():
    x = load_exec()
    bench = bench_close()
    fr_bar = fund_to_bars(x, load_funding_avg())
    x_index = x.index

    mom30 = btc_mom_series(x, 30)
    mom255 = btc_mom_series(x, 25.5)
    mom345 = btc_mom_series(x, 34.5)

    # template snapshot (repo canonical file, read ONCE)
    C_CANON = os.path.join(REPO, "models/alpha_formulas/alpha_076c.py")
    c_src, c_hash = snapshot(C_CANON, ["BTC_MOM_THRESHOLD = 1.00",
                                       "btc_up = (mom > BTC_MOM_THRESHOLD).shift(1).fillna(False)",
                                       "use_btc_mom_gate=True"])
    R["formula"] = {"alpha_076c_md5": c_hash,
                    "gate_state": "mom>thr shifted 1 bar inside formula (frozen spec causality)",
                    "warmup": "closed (NaN -> False)"}
    A_CANON = os.path.join(REPO, "models/alpha_formulas/alpha_076a.py")
    a_src, a_hash = snapshot(A_CANON, ["fund < 0.7", "tl - 1.0 * atr",
                                       "high.rolling(192, min_periods=96)"])
    R["formula"]["alpha_076a_md5"] = a_hash

    # ── (0) A center: engine rerun (validates vs stored production curve) ──
    log("A center engine run...")
    eqA_e, posA_e = engine_run(A_CANON, tag="A")
    eq_st, pos_st = load_curve(os.path.join(REPO, "data/precompute/alpha_076a.csv.gz"))
    eq_st = eq_st[eq_st.index <= SEAL]
    agree = float((pos_st.reindex(posA_e.index).fillna(0.0).values == posA_e.values).mean()) * 100
    R["A_center_validation"] = {"position_agreement_vs_stored_pct": round(agree, 4)}
    log("A position agreement vs stored curve:", agree)
    assert agree >= 99.9, "A engine rerun diverges from stored production curve"

    ffA, nfA, nfundA, feeA, eqA_nfund = three_books(eqA_e, posA_e, x_index, fr_bar, bench, "A_engine")
    R["A_engine"] = {"feefree": ffA, "netted": nfA, "netfund": nfundA, "fee_mo": feeA}

    # ── (1) 076c center engine run ──
    log("076c center engine run...")
    eqC_e, posC_e = engine_run(C_CANON, btc_mom=mom30, tag="C")
    ffC, nfC, nfundC, feeC, eqC_nfund = three_books(eqC_e, posC_e, x_index, fr_bar, bench, "C_engine")
    R["C_engine"] = {"feefree": ffC, "netted": nfC, "netfund": nfundC, "fee_mo": feeC}
    eqC_nfund.to_csv(os.path.join(CUR, "C_engine_netfund.csv.gz"), compression="gzip")
    eqA_nfund.to_csv(os.path.join(CUR, "A_engine_netfund.csv.gz"), compression="gzip")
    pd.DataFrame({"pos": posC_e}).to_pickle(os.path.join(SCRATCH, "C_pos.pkl"))
    pd.DataFrame({"pos": posA_e}).to_pickle(os.path.join(SCRATCH, "A_pos.pkl"))

    # engine-vs-bar-arithmetic position agreement (decision lag 1)
    fund_eng = _fund_pct_for(EX, "binance").reindex(x_index)
    gm = (fund_eng < 0.7).fillna(False)
    posC_ba = latch(x, entry_mask=(gm & (mom30.shift(1) > 1.00).fillna(False)))
    lag_ok = float((posC_ba.shift(1).fillna(0.0).reindex(posC_e.index).fillna(0.0).values == posC_e.values).mean()) * 100
    R["C_engine_vs_bararith_pos_agreement_pct"] = round(lag_ok, 4)
    log("076c engine-vs-bararith (shift-aligned) agreement:", lag_ok)

    # ── (2) 076c jitter: window {25.5,34.5}d x thr {0.90,1.00,1.10} (engine) ──
    log("076c jitter engine runs...")
    R["C_jitter"] = {}
    for thr, thr_tag in ((0.90, "090"), (1.10, "110")):
        vsrc = c_src.replace("BTC_MOM_THRESHOLD = 1.00", f"BTC_MOM_THRESHOLD = {thr}")
        assert f"BTC_MOM_THRESHOLD = {thr}" in vsrc
        vpath = write_variant(f"z_formula_thr{thr_tag}.py", vsrc, [f"BTC_MOM_THRESHOLD = {thr}"])
        for days, mser in ((25.5, mom255), (34.5, mom345)):
            tag = f"w{days}_thr{thr}"
            eqj, posj = engine_run(vpath, btc_mom=mser, tag=tag)
            ffj, nfj, nfundj, feej, _ = three_books(eqj, posj, x_index, fr_bar, bench, f"CJ_{tag}")
            R["C_jitter"][tag] = {"feefree": ffj, "netted": nfj, "netfund": nfundj, "fee_mo": feej}
            log("  jitter", tag, "netfund", nfundj["mean_excess_pct_mo"], "t", nfundj["t"])
    # window jitter at the center threshold (thr 1.00)
    for days, mser in ((25.5, mom255), (34.5, mom345)):
        tag = f"w{days}_thr1.00"
        eqj, posj = engine_run(C_CANON, btc_mom=mser, tag=tag)
        ffj, nfj, nfundj, feej, _ = three_books(eqj, posj, x_index, fr_bar, bench, f"CJ_{tag}")
        R["C_jitter"][tag] = {"feefree": ffj, "netted": nfj, "netfund": nfundj, "fee_mo": feej}
        log("  jitter", tag, "netfund", nfundj["mean_excess_pct_mo"], "t", nfundj["t"])

    # ── (3) alpha_076a jitter: buf/N/gate (engine, one-at-a-time) ──
    log("A jitter engine runs...")
    R["A_jitter"] = {}
    avars = []
    for buf in (0.85, 1.15):
        v = a_src.replace("tl - 1.0 * atr", f"tl - {buf} * atr")
        avars.append((f"buf{buf}", v, f"tl - {buf} * atr"))
    for N in (163, 221):
        v = (a_src.replace("high.rolling(192, min_periods=96)", f"high.rolling({N}, min_periods={N//2})")
                  .replace("low.rolling(192, min_periods=96)", f"low.rolling({N}, min_periods={N//2})"))
        avars.append((f"N{N}", v, f"low.rolling({N}, min_periods={N//2})"))
    for gp in (0.5, 0.8):
        v = a_src.replace("fund < 0.7", f"fund < {gp}")
        avars.append((f"gate{gp}", v, f"fund < {gp}"))
    for tag, vsrc, marker in avars:
        vpath = write_variant(f"z_formula_A_{tag}.py", vsrc, [marker])
        eqj, posj = engine_run(vpath, tag=f"A_{tag}")
        ffj, nfj, nfundj, feej, _ = three_books(eqj, posj, x_index, fr_bar, bench, f"AJ_{tag}")
        R["A_jitter"][tag] = {"feefree": ffj, "netted": nfj, "netfund": nfundj, "fee_mo": feej}
        log("  A jitter", tag, "netfund", nfundj["mean_excess_pct_mo"], "t", nfundj["t"])

    # ── (4) shift-2 retention (076c) ──
    log("shift-2...")
    pos2 = posC_e.shift(2).fillna(0.0)
    eqC2_nfund = netting_on_curve(eqC_e, pos2, fr_bar, x_index, fund=True)
    eqC2_nf = netting_on_curve(eqC_e, pos2, fr_bar, x_index, fund=False)
    g2_nfund = grade(eqC2_nfund, bench, "C_shift2_netfund", pos=pos2)
    g2_nf = grade(eqC2_nf, bench, "C_shift2_netted", pos=pos2)
    base_netfund = R["C_engine"]["netfund"]["mean_excess_pct_mo"]
    base_netted = R["C_engine"]["netted"]["mean_excess_pct_mo"]
    R["C_shift2"] = {
        "netfund": {k: g2_nfund[k] for k in KEYS},
        "netted": {k: g2_nf[k] for k in KEYS},
        "retention_netfund_pct": round(g2_nfund["mean_excess_pct_mo"] / base_netfund * 100, 1),
        "retention_netted_pct": round(g2_nf["mean_excess_pct_mo"] / base_netted * 100, 1),
    }

    # ── (5) anchored exam v3.2 soft scores (theta 0.598, sigma 0.22) ──
    bm = bench_monthly(bench)
    sig = sigma_m(bench)
    exA = monthly_excesses(eqA_nfund, bench)
    exC = monthly_excesses(eqC_nfund, bench)
    theta_check = calibrate_theta(exA, bm.values, sig, target=0.3)
    sA = soft_scores(exA, bm.values, 0.598, 0.22)
    sC = soft_scores(exC, bm.values, 0.598, 0.22)
    R["anchored_exam"] = {
        "sigma_m_bench": round(sig, 4),
        "theta_inversion_check_on_A": theta_check,
        "theta_frozen": 0.598, "sigma_frozen": 0.22,
        "A_soft_mean": round(float(sA.mean()), 3),
        "A_soft_t": round(float(sA.mean() / sA.std(ddof=1)), 3) if sA.std(ddof=1) > 0 else None,
        "C_soft_mean": round(float(sC.mean()), 3),
        "C_soft_t": round(float(sC.mean() / sC.std(ddof=1)), 3) if sC.std(ddof=1) > 0 else None,
        "C_minus_A": round(float(sC.mean() - sA.mean()), 3),
        "bar": "C_soft >= A_soft + 0.3",
    }

    # ── (6) verbatim slices: 2021-04/05 mania-whipsaw, 2022-07 counter ──
    def month_exc(eq):
        rows = {}
        for s in (pd.Timestamp("2021-04-01", tz="UTC"), pd.Timestamp("2021-05-01", tz="UTC"),
                  pd.Timestamp("2022-07-01", tz="UTC")):
            e = s + pd.DateOffset(months=1)
            wa = eq[(eq.index >= s) & (eq.index < e)]; wb = bench[(bench.index >= s) & (bench.index < e)]
            if len(wa) >= 2 and len(wb) >= 2:
                rows[str(s.date())] = round((wa.iloc[-1] / wa.iloc[0] - wb.iloc[-1] / wb.iloc[0]) * 100, 2)
        return rows
    R["verbatim_slices_netfund"] = {"A": month_exc(eqA_nfund), "C": month_exc(eqC_nfund)}

    # ── (7) bar-arithmetic cross-check (compose_portfolio reference) ──
    log("bar-arithmetic cross-check...")
    posA_ba = latch(x, entry_mask=gm)
    eqA_ba = sim_curve(x, posA_ba, fr_bar)
    gA_ba = grade(eqA_ba, bench, "BA_A_static", pos=posA_ba)
    posC_ba_lag0 = latch(x, entry_mask=(gm & (mom30 > 1.00).fillna(False)))
    eqC_ba_lag0 = sim_curve(x, posC_ba_lag0, fr_bar)
    gC_ba_lag0 = grade(eqC_ba_lag0, bench, "BA_C_state0", pos=posC_ba_lag0)
    eqC_ba = sim_curve(x, posC_ba, fr_bar)
    gC_ba = grade(eqC_ba, bench, "BA_C_state_shift1", pos=posC_ba)
    R["bar_arithmetic_reference"] = {
        "A_static": {k: gA_ba[k] for k in KEYS},
        "C_state_shift1": {k: gC_ba[k] for k in KEYS},
        "C_state_shift0_sensitivity": {k: gC_ba_lag0[k] for k in KEYS},
        "ledger_reference_20261022": {
            "A_static": {"net": 2.06, "t": 1.35, "dd": -50.4},
            "C_entry_gated": {"net": 3.16, "t": 1.53, "worst": -40.5, "dd": -43.4}},
        "delta_C_vs_3.16_state_shift1": round(gC_ba["mean_excess_pct_mo"] - 3.16, 2),
        "delta_C_vs_3.16_state_shift0": round(gC_ba_lag0["mean_excess_pct_mo"] - 3.16, 2),
        "delta_A_vs_2.06": round(gA_ba["mean_excess_pct_mo"] - 2.06, 2),
    }

    json.dump(R, open(os.path.join(RES, "pilot_results.json"), "w"), indent=1)
    log("DONE -> results/pilot_results.json")


if __name__ == "__main__":
    main()
