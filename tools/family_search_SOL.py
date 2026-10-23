#!/usr/bin/env python3
"""076a-FAMILY PARAMETER SEARCH — SOL-USDT 15m (JP-directed per-asset tailoring, 2026-10-23).

Pre-registered grid (reports/family_search_SOL_20261023/REPORT.md, committed
BEFORE this run): N {144,192,288} x ATR-mult {0.85,1.0,1.15} x gate-pctl
{0.5,0.7,0.8} = 27 configs, mp=N/2, warmup CLOSED, long-only, funding = binance
settled proxy (portability-run convention). Engine + costs + ruler: exact
portability-076a path (tools/portability_076a.py is the template — formula-mode
fast engine, fee 0.0008 netted |dpos|, funding at 00/08/16 bars,
stats_canonical grade verbatim, bench = same-asset buy-hold).

SCREEN FLOORS per config (hard): OOS sign > 0, worst absolute month >= -40,
both halves >= 0.
PHASE 2 (survivors only): jitter +/-15% one-at-a-time (6 neighbors) sign-stable
+ halves >= 0; genuine shift-2 retention >= 0.25; anchored exam v3.2 soft scores
(theta 0.598, sigma 0.22 frozen) vs the SAME-ASSET raw-latch anchor (same family
without funding gate, netted). One best-by-exam config max gets a writeup.

Path validation gate: center config (192/1.0/0.7) == frozen alpha_076a MUST
reproduce the portability SOL netfund row to the digit; divergence = abort.

Collision-hardened: isolated /tmp/fsearch_SOL_<pid>/, template snapshotted once,
content asserts on every derived formula (twin-collision lesson). Under
AGENT_CONTRACT.md: one number per candidate from tools.stats_canonical.grade.
"""
import os, sys, json, time, hashlib, csv
import numpy as np
import pandas as pd

REPO = "/home/node/.openclaw/workspace/crypto"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl")

from tools.stats_canonical import (grade, load_bench, monthly_excesses,
                                   bench_monthly, sigma_m, soft_scores)
import tools.stats_canonical as sc

TMP = f"/tmp/fsearch_SOL_{os.getpid()}"
os.makedirs(TMP, exist_ok=True)
OUT = os.path.join(REPO, "reports/family_search_SOL_20261023")
CUR = os.path.join(OUT, "curves")
os.makedirs(CUR, exist_ok=True)

from tuner.alpha_orchestrator import run_backtest, build_fund_pct
from models.wq_alpha_miner import WQAlphaParams
from models.wq_alpha_fast import prepare_fast_context

DATA = os.path.join(REPO, "framework", "data_cache")
SOL_CSV = os.path.join(DATA, "okx_SOL_USDT_15m_20210101_20260928.csv")
SOL_FUND = os.path.join(DATA, "binance_SOLUSDT_funding_proxy_202101_202610.csv")
TEMPLATE = os.path.join(REPO, "models/alpha_formulas/alpha_076a.py")

SEAL = pd.Timestamp("2026-07-28", tz="UTC")
START = "2021-01-01T00:00:00+00:00"
END = "2026-07-28T00:00:00+00:00"
FEE = 0.0008

GRID_N = (144, 192, 288)
GRID_BUF = (0.85, 1.0, 1.15)
GRID_GATE = (0.5, 0.7, 0.8)

# Pre-declared path-validation gate: center config == frozen 076a production.
CENTER_EXPECT = {"mean_excess_pct_mo": -5.17, "t": -1.27, "continuous_dd_pct": -85.6,
                 "worst_absolute_month_pct": -38.51, "first_half_pct": -7.55,
                 "second_half_pct": -2.86}

T0 = time.time()
def log(*a):
    print(f"[{time.time()-T0:6.0f}s]", *a, flush=True)


class GuardRelease:
    """Release ONLY stats_canonical's unit-tripwire (in-process, disclosed).

    Pre-verified lawful in the portability run: SOL same-asset buy-hold returned
    +202.5% in Aug-21 (raw closes, flagship-checked), so out-of-band window
    excesses are real crypto-native extremes, not unit mix. Ruler arithmetic
    stays byte-identical; tools/stats_canonical.py is NOT touched."""
    def __init__(self):
        self.released = []
        self._orig = None
    def __enter__(self):
        self._orig = sc._boundary_pct
        def _relaxed(x):
            p = float(x) * 100.0
            if not (-100.0 < p < 1000.0):
                self.released.append(round(p, 2))
            return round(p, 2)
        sc._boundary_pct = _relaxed
        return self
    def __exit__(self, *a):
        sc._boundary_pct = self._orig
        return False


def grade_canonical(eq, bench, name, pos):
    """Strict ruler first; guard release only on tripwire, with audit trail."""
    try:
        return grade(eq, bench, name, pos=pos), None
    except AssertionError:
        with GuardRelease() as g:
            g_out = grade(eq, bench, name, pos=pos, trap_asserts=False)
        audit = []
        ex = sc.monthly_excesses(eq, bench)
        grid = [s for s in sc.GRID]
        for s, e_frac in zip(grid, ex):
            p = round(e_frac * 100.0, 2)
            if p in g.released:
                e = s + pd.DateOffset(months=1)
                r_s = sc._win_ret(eq, s, e)
                r_b = sc._win_ret(bench, s, e)
                audit.append({"month": s.strftime("%Y-%m"), "excess_pct": p,
                              "strat_pct": round(r_s * 100, 2) if r_s is not None else None,
                              "bench_pct": round(r_b * 100, 2) if r_b is not None else None})
        return g_out, {"released_values_pct": g.released, "windows": audit}


# ── template snapshot + variant writer (twin-proof) ───────────────────
def snapshot_template():
    src = open(TEMPLATE).read()
    for m in ["fund < 0.7", "tl - 1.0 * atr", "high.rolling(192, min_periods=96)",
              "low.rolling(192, min_periods=96)", "tr.rolling(96, min_periods=32)",
              "funding_gate_mode=\"formula\"", "warmup_candles=100"]:
        assert m in src, f"alpha_076a marker missing: {m}"
    return src, hashlib.md5(src.encode()).hexdigest()[:12]


def write_variant(name, src, must_contain):
    p = os.path.join(TMP, name)
    with open(p, "w") as f:
        f.write(src)
    back = open(p).read()
    for m in must_contain:
        assert m in back, f"variant {name} lost marker {m} (clobber?)"
    return p


def make_formula(n, buf, gate, gated=True, tag=""):
    """076a formula variant with N/buf/gate substituted; gated=False = raw latch."""
    src, _ = TEMPLATE_SNAP
    src = (src.replace("high.rolling(192, min_periods=96)", f"high.rolling({n}, min_periods={n//2})")
              .replace("low.rolling(192, min_periods=96)", f"low.rolling({n}, min_periods={n//2})")
              .replace("tl - 1.0 * atr", f"tl - {buf} * atr"))
    markers = [f"high.rolling({n}, min_periods={n//2})",
               f"low.rolling({n}, min_periods={n//2})", f"tl - {buf} * atr"]
    if gated:
        src = src.replace("fund < 0.7", f"fund < {gate}")
        assert f"fund < {gate}" in src
        markers.append(f"fund < {gate}")
    else:
        # raw-latch anchor: funding gate removed from the state machine; the
        # injected-column reference must go too (engine attaches no fund_pct
        # when use_funding_gate=False).
        src = (src.replace("fund = df[\"fund_pct\"]",
                           "fund = None  # raw-latch anchor: funding gate bypassed")
                  .replace("uncrowded = (fund < 0.7).fillna(False)",
                           "uncrowded = pd.Series(True, index=close.index)"))
        assert "fund = None  # raw-latch anchor" in src
        assert "uncrowded = pd.Series(True, index=close.index)" in src
        markers += ["fund = None  # raw-latch anchor",
                    "uncrowded = pd.Series(True, index=close.index)"]
    return write_variant(f"z_f{tag}_N{n}_b{buf}_g{gate}.py", src, markers)


def make_formula_shift2(n, buf, gate, tag="s2"):
    """Genuine shift-2 relabel: the event series is shifted 2 bars INSIDE the
    formula (delay every position change by 2 bars), engine re-run with the
    same costs — the r3/btc_stress relabel convention. (Portability-style
    cost-overlay-only shifting was rejected pre-run: it keeps the ORIGINAL PnL
    stream under the shifted position's costs — an incoherent book.)"""
    src, _ = TEMPLATE_SNAP
    src = (src.replace("high.rolling(192, min_periods=96)", f"high.rolling({n}, min_periods={n//2})")
              .replace("low.rolling(192, min_periods=96)", f"low.rolling({n}, min_periods={n//2})")
              .replace("tl - 1.0 * atr", f"tl - {buf} * atr")
              .replace("fund < 0.7", f"fund < {gate}")
              .replace("    latch = ev.ffill().fillna(0.0)",
                       "    ev = ev.shift(2)  # SHIFT2 relabel\n    latch = ev.ffill().fillna(0.0)"))
    markers = [f"high.rolling({n}, min_periods={n//2})", f"tl - {buf} * atr",
               f"fund < {gate}", "ev = ev.shift(2)  # SHIFT2 relabel"]
    return write_variant(f"z_f{tag}_N{n}_b{buf}_g{gate}.py", src, markers)


# ── funding plumbing (portability convention, verbatim) ──────────────
def _load_settled(path):
    d = pd.read_csv(path)
    try:
        t = pd.to_datetime(d["ts"], utc=True)
    except ValueError:
        t = pd.to_datetime(d["ts"], utc=True, format="mixed")
    rcol = "rate" if "rate" in d.columns else "fundingRate"
    s = pd.Series(d[rcol].astype(float).values, index=t.dt.floor("8h"))
    return s[~s.index.duplicated(keep="last")].sort_index()


def fund_to_bars(exec_df, fund):
    bar_close = (exec_df["timestamp"] + pd.Timedelta("15min")).astype("int64").values
    fb = fund["bucket"].astype("int64").values
    idx = np.searchsorted(fb, bar_close, side="right") - 1
    ok = idx >= 0
    idxc = np.clip(idx, 0, len(fund) - 1)
    v = fund["rate"].values[idxc].astype(float)
    v[~ok] = np.nan
    return v


def netting_on_curve(eq_free, pos, fr_bar, x_index, fee=True, fund=True):
    """Cost overlay on an ENGINE curve (calibrate.py convention, verbatim):
    fee 0.0008 on |dpos|; funding -rate*pos at 00/08/16 bars."""
    ret = eq_free.pct_change().fillna(0.0)
    net = ret.copy()
    if fee:
        net = net - FEE * pos.diff().abs().fillna(0.0)
    if fund:
        is_settle = (x_index.hour % 8 == 0) & (x_index.minute == 0)
        fr = pd.Series(np.where(is_settle, np.nan_to_num(fr_bar), 0.0), index=x_index)
        net = net - fr * pos
    return pd.Series(np.cumprod(1.0 + net.values), index=x_index) * eq_free.iloc[0]


# ── engine run (production recipe, per config) ────────────────────────
def engine_run(formula_path, gated=True, gate=0.7, tag=""):
    """Fast path + fund_pct injection seam; the gate series is built with the
    ASSET's symbol (binance, build_fund_pct) — never the ETH default."""
    ctx = prepare_fast_context(SOL_CSV, None, formula_path)
    if gated and ctx.fund_pct is None:
        ctx.fund_pct = FUND_PCT
    p = WQAlphaParams(
        formula_path=formula_path, long_threshold=0.5, short_threshold=0.55,
        signal_smoothing=1, atr_period=14, atr_stop_mult=50.0, atr_take_mult=50.0,
        max_position_pct=1.0, warmup_candles=100, use_bias_filter=False,
        signal_exit_threshold=0.5, use_funding_gate=gated, funding_gate_pctl=gate,
        funding_input="binance", funding_gate_mode="formula" if gated else "predict",
        use_btc_mom_gate=False)
    eq = run_backtest(p, "SOL/USDT", "15m", "15m", {"15m": SOL_CSV},
                      START, END, ctx=ctx, allow_shorts=False, fee=0.0)
    if eq is None:
        raise RuntimeError(f"engine run failed: {tag}")
    t = pd.to_datetime(eq["timestamp"], utc=True)
    eqs = pd.Series(eq["equity"].astype(float).values, index=t)
    pv = eq["position"]
    if pv.dtype == object or str(pv.dtype) in ("string", "str") or pv.map(type).eq(str).any():
        pv = pv.map({"long": 1.0, "short": -1.0}).fillna(0.0)
    poss = pd.Series(pv.astype(float).values, index=t)
    return eqs, poss


KEYS = ("mean_excess_pct_mo", "t", "worst_window_pct", "best_window_pct", "first_half_pct",
        "second_half_pct", "concentration", "neg_windows", "n_windows", "continuous_dd_pct",
        "july26_partial_pct", "time_in_pct", "worst_absolute_month_pct")

BENCH = None      # same-asset buy-hold
FR_BAR = None     # settled funding aligned to bars
FUND_PCT = None   # gate series (built once, attached to every ctx)
X = None          # exec frame (timestamps for fund_to_bars)


def three_books(eq_free, pos, name):
    x_index = eq_free.index
    g_ff, r1 = grade_canonical(eq_free, BENCH, f"{name}_feefree", pos)
    eq_nf = netting_on_curve(eq_free, pos, FR_BAR, x_index, fund=False)
    g_nf, r2 = grade_canonical(eq_nf, BENCH, f"{name}_netted", pos)
    eq_nfund = netting_on_curve(eq_free, pos, FR_BAR, x_index, fund=True)
    g_nfund, r3 = grade_canonical(eq_nfund, BENCH, f"{name}_netfund", pos)
    fee_mo = FEE * pos.diff().abs().fillna(0.0).resample("MS").sum().mean() * 100
    return ({"feefree": {k: g_ff[k] for k in KEYS}, "netted": {k: g_nf[k] for k in KEYS},
             "netfund": {k: g_nfund[k] for k in KEYS},
             "fee_mo_pct": round(float(fee_mo), 2),
             "guard_release": {"feefree": r1, "netted": r2, "netfund": r3}},
            eq_nfund)


def passes_screen(nf):
    return {"sign": nf["mean_excess_pct_mo"] > 0,
            "worst_abs": nf["worst_absolute_month_pct"] >= -40,
            "halves": nf["first_half_pct"] >= 0 and nf["second_half_pct"] >= 0}


def jitter_neighbors(n, buf, gate):
    """One-at-a-time +/-15%, 6 neighbors. N rounded int, gate 3dp."""
    return [("N-", round(n * 0.85), buf, gate), ("N+", round(n * 1.15), buf, gate),
            ("buf-", n, round(buf * 0.85, 4), gate), ("buf+", n, round(buf * 1.15, 4), gate),
            ("gate-", n, buf, round(gate * 0.85, 4)), ("gate+", n, buf, round(gate * 1.15, 4))]


def main():
    global BENCH, FR_BAR, FUND_PCT, X, TEMPLATE_SNAP
    R = {"run": "076a-family parameter search SOL-USDT 15m (pre-registered)",
         "date": "2026-10-23",
         "pre_registration": "reports/family_search_SOL_20261023/REPORT.md (committed 3cb23c8, before any run)",
         "grid_declared": {"N": list(GRID_N), "buf": list(GRID_BUF), "gate": list(GRID_GATE),
                           "mp": "N/2", "atr": "ATR96=SMA(TR,96,min_periods=32) fixed"},
         "engine": "portability-076a path verbatim: formula-mode fast path, decide@close "
                   "fill@next-open, 2x rails (atr 50/50), allow_shorts=False, engine fee=0.0, warmup_candles=100",
         "costs": "fee 0.0008 netted on |dpos| + funding (binance settled proxy) at 00/08/16 UTC bars; headline = netfund",
         "ruler": "tools/stats_canonical.grade, bench = same-asset buy-hold; GuardRelease in-process (portability-precedent)",
         "outcomes_pre_registered": ["survivor -> flagged for holdout-style confirmation, NOT deployment",
                                     "none -> ledgered no-pass"]}
    TEMPLATE_SNAP = snapshot_template()
    R["template_md5"] = TEMPLATE_SNAP[1]
    log("template md5", R["template_md5"])

    # data + funding once
    X = pd.read_csv(SOL_CSV)
    X["timestamp"] = pd.to_datetime(X["timestamp"], utc=True)
    X = X[(X.timestamp >= pd.Timestamp(START)) & (X.timestamp <= SEAL)].reset_index(drop=True)
    X.index = X["timestamp"]
    fr = _load_settled(SOL_FUND)
    fund = pd.DataFrame({"bucket": fr.index, "rate": fr.values}).sort_values("bucket").reset_index(drop=True)
    FR_BAR = fund_to_bars(X, fund)
    BENCH = load_bench(SOL_CSV)
    BENCH = BENCH[BENCH.index <= SEAL].sort_index()
    log("funding cost series + bench ready; building gate series (fund_pct)...")
    # fund_pct MUST be built on the FULL csv (portability convention): the fast
    # path slices ctx.fund_pct POSITIONALLY (iloc[base:]) against the full
    # dataset the context was built on — a truncated series misaligns the gate.
    df_full = pd.read_csv(SOL_CSV, parse_dates=["timestamp"], index_col="timestamp")
    df_full.sort_index(inplace=True)
    FUND_PCT = build_fund_pct(df_full, "binance", "SOL/USDT")
    log("fund_pct ready:", int(FUND_PCT.notna().sum()), "valid bars /", len(FUND_PCT))

    bm = bench_monthly(BENCH)
    sig_sol = sigma_m(BENCH)
    R["sigma_m_SOL_bench"] = round(sig_sol, 4)
    R["sigma_frozen"] = 0.22
    R["theta_frozen"] = 0.598
    log("sigma_m(SOL bench) =", round(sig_sol, 4), "(frozen sigma 0.22 used verbatim)")

    # ── PHASE 1: grid screen ──
    rows = []
    R["grid"] = {}
    for n in GRID_N:
        for buf in GRID_BUF:
            for gate in GRID_GATE:
                tag = f"N{n}_b{buf}_g{gate}"
                fp = make_formula(n, buf, gate, gated=True, tag="grid")
                eqf, pos = engine_run(fp, gated=True, gate=gate, tag=tag)
                books, eq_nfund = three_books(eqf, pos, tag)
                nf = books["netfund"]
                scr = passes_screen(nf)
                row = {"n": n, "buf": buf, "gate": gate,
                       "mean_excess_pct_mo": nf["mean_excess_pct_mo"], "t": nf["t"],
                       "worst_window_pct": nf["worst_window_pct"],
                       "worst_abs_pct": nf["worst_absolute_month_pct"],
                       "half1_pct": nf["first_half_pct"], "half2_pct": nf["second_half_pct"],
                       "dd_pct": nf["continuous_dd_pct"], "time_in_pct": nf["time_in_pct"],
                       "pass_sign": scr["sign"], "pass_worst_abs": scr["worst_abs"],
                       "pass_halves": scr["halves"], "survivor": all(scr.values())}
                rows.append(row)
                R["grid"][tag] = {"books": books, "screen": scr, "survivor": row["survivor"]}
                log(f"{tag}: exc {nf['mean_excess_pct_mo']} t {nf['t']} worst {nf['worst_absolute_month_pct']} "
                    f"halves {nf['first_half_pct']}/{nf['second_half_pct']} dd {nf['continuous_dd_pct']} "
                    f"=> {'SURVIVOR' if row['survivor'] else 'dead'}")

                # path-validation gate on the center config (frozen 076a)
                if (n, buf, gate) == (192, 1.0, 0.7):
                    ok = all(abs(nf[k] - v) < 0.005 for k, v in CENTER_EXPECT.items())
                    R["center_validation"] = {"expected": CENTER_EXPECT,
                                              "got": {k: nf[k] for k in CENTER_EXPECT},
                                              "match": ok}
                    log("CENTER validation vs portability row:", "MATCH" if ok else "MISMATCH")
                    assert ok, "center config does not reproduce portability SOL row — ABORT"

    # grid.csv (one row per config)
    with open(os.path.join(OUT, "grid.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    survivors = [r for r in rows if r["survivor"]]
    R["n_survivors"] = len(survivors)
    log(f"SCREEN: {len(survivors)}/{len(rows)} survivors")

    # ── PHASE 2: battery for survivors ──
    R["battery"] = {}
    best = None
    for r in survivors:
        n, buf, gate = r["n"], r["buf"], r["gate"]
        tag = f"N{n}_b{buf}_g{gate}"
        B = {"jitter": {}, "shift2": {}, "anchored_exam": {}}

        # jitter: 6 neighbors, one-at-a-time
        j_ok = True
        for jtag, jn, jbuf, jgate in jitter_neighbors(n, buf, gate):
            if (jn, jbuf, jgate) == (n, buf, gate):
                continue  # rounding collapsed the neighbor (no-op) — disclosed
            fp = make_formula(jn, jbuf, jgate, gated=True, tag="jit")
            eqf, pos = engine_run(fp, gated=True, gate=jgate, tag=f"{tag}_{jtag}")
            books, _ = three_books(eqf, pos, f"JIT_{tag}_{jtag}")
            nf = books["netfund"]
            okj = nf["mean_excess_pct_mo"] > 0 and nf["first_half_pct"] >= 0 and nf["second_half_pct"] >= 0
            j_ok &= okj
            B["jitter"][f"{jtag}_N{jn}_b{jbuf}_g{jgate}"] = {
                "netfund": {k: nf[k] for k in KEYS}, "ok": okj}
            log(f"  jitter {tag} {jtag}: exc {nf['mean_excess_pct_mo']} halves "
                f"{nf['first_half_pct']}/{nf['second_half_pct']} => {'ok' if okj else 'FAIL'}")
        B["jitter_pass"] = j_ok

        # shift-2 retention (genuine relabel: decision series shifted 2 bars
        # inside the formula, engine re-run, same costs — pre-run amendment)
        fp2 = make_formula_shift2(n, buf, gate, tag=f"s2_N{n}_b{buf}_g{gate}")
        eqf2, pos2 = engine_run(fp2, gated=True, gate=gate, tag=f"{tag}_s2")
        books2, eq2_nfund = three_books(eqf2, pos2, f"SHIFT2_{tag}")
        g2 = books2["netfund"]
        ret = (g2["mean_excess_pct_mo"] / r["mean_excess_pct_mo"]) if r["mean_excess_pct_mo"] > 0 else 0.0
        B["shift2"] = {"mean_excess_pct_mo": g2["mean_excess_pct_mo"], "t": g2["t"],
                       "retention": round(ret, 4), "pass": ret >= 0.25,
                       "bars_diff": int((pos.values != pos2.values).sum())}
        log(f"  shift2 {tag}: exc {g2['mean_excess_pct_mo']} retention {ret:.2f} "
            f"({B['shift2']['bars_diff']} bars differ) => {'ok' if B['shift2']['pass'] else 'FAIL'}")

        # anchored exam v3.2 vs SAME-ASSET raw latch (no gate), netfund
        fpa = make_formula(n, buf, gate, gated=False, tag="anchor")
        eqfa, posa = engine_run(fpa, gated=False, tag=f"{tag}_anchor")
        booksa, eqa_nfund = three_books(eqfa, posa, f"ANCHOR_{tag}")
        eq_c_nfund = netting_on_curve(eqf, pos, FR_BAR, eqf.index, fund=True)
        ex_c = monthly_excesses(eq_c_nfund, BENCH)
        ex_a = monthly_excesses(eqa_nfund, BENCH)
        s_c = soft_scores(ex_c, bm.values, 0.598, 0.22)
        s_a = soft_scores(ex_a, bm.values, 0.598, 0.22)
        clears = float(s_c.mean()) >= float(s_a.mean())
        B["anchored_exam"] = {
            "theta_frozen": 0.598, "sigma_frozen": 0.22, "sigma_m_SOL_bench": round(sig_sol, 4),
            "config_soft_mean": round(float(s_c.mean()), 3),
            "config_soft_t": round(float(s_c.mean() / s_c.std(ddof=1)), 3) if s_c.std(ddof=1) > 0 else None,
            "anchor_soft_mean": round(float(s_a.mean()), 3),
            "anchor_soft_t": round(float(s_a.mean() / s_a.std(ddof=1)), 3) if s_a.std(ddof=1) > 0 else None,
            "anchor_netfund_exc": booksa["netfund"]["mean_excess_pct_mo"],
            "clears_anchor_line": clears}
        B["battery_pass"] = bool(j_ok and B["shift2"]["pass"] and clears)
        log(f"  anchored {tag}: cfg {B['anchored_exam']['config_soft_mean']} vs anchor "
            f"{B['anchored_exam']['anchor_soft_mean']} => {'clears' if clears else 'BELOW'}; "
            f"battery {'PASS' if B['battery_pass'] else 'FAIL'}")

        # survivor curve artifacts
        eq_c_nfund.to_csv(os.path.join(CUR, f"surv_{tag}_netfund.csv.gz"), compression="gzip")
        eqa_nfund.to_csv(os.path.join(CUR, f"anchor_{tag}_netfund.csv.gz"), compression="gzip")
        pd.DataFrame({"pos": pos}).to_csv(os.path.join(CUR, f"surv_{tag}_pos.csv.gz"),
                                          compression="gzip")
        R["battery"][tag] = B
        if B["battery_pass"] and (best is None or
                                  B["anchored_exam"]["config_soft_mean"] >
                                  R["battery"][best]["anchored_exam"]["config_soft_mean"]):
            best = tag
    R["best_by_exam"] = best

    # verdict (pre-registered branches)
    if best is not None:
        R["verdict"] = (f"survivor ({best}) -> flagged for holdout-style confirmation, NOT deployment")
    else:
        R["verdict"] = "none -> ledgered no-pass"
    log("VERDICT:", R["verdict"])

    json.dump(R, open(os.path.join(OUT, "results.json"), "w"), indent=1, default=str)
    log("DONE -> reports/family_search_SOL_20261023/results.json")


if __name__ == "__main__":
    main()
