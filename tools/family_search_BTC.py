#!/usr/bin/env python3
"""076a-FAMILY PARAMETER SEARCH — BTC-USDT 15m (JP-directed per-asset tailoring, 2026-10-23).

Pre-registered spec: reports/family_search_BTC_20261023/REPORT.md (written BEFORE
this run; grid = ETH r3 family dimensions recovered from reports/bull_mining_r3/
{REPORT.md §Robustness, jitter_bin_g0.7.json}, 27 configs).

Engine + costs + ruler: exact tools/portability_076a.py path (formula-mode engine,
fund_pct injection seam, decide@close fill@next-open, 2x rails, allow_shorts=False,
engine fee=0.0; fee 0.0008 netted |dpos|; funding = binance settled proxy charged at
00/08/16 UTC bars; stats_canonical.grade ONLY; bench = same-asset buy-hold).

Phase 1: 27-config screen (floors: OOS sign > 0, worst abs month >= -40, halves >= 0).
Phase 2 (passers only): 6-neighbor +/-15% jitter (sign-stable + halves >= 0),
GENUINE shift-2 retention >= 0.25 (substrate relabel, not the vacuous engine-curve
shift — twin lesson 2026-10-23), anchored exam v3.2 soft scores (theta 0.598,
sigma 0.22, frozen) vs the SAME-ASSET raw-latch anchor (N192/buf1.0, gate OFF,
netted). Anchor line = anchor's own anchored score; clears = strictly above.

Outcomes branch (pre-registered): survivor -> flagged for holdout-style
confirmation, NOT deployment; none -> ledgered no-pass.

Twin-collision hardening: all scratch under /tmp/fsearch_BTC_<pid>/ (isolated per
run; concurrent SOL search unaffected). Progress flushed to progress.log every step.
"""
import os, sys, json, time, hashlib
import numpy as np
import pandas as pd

REPO = "/home/node/.openclaw/workspace/crypto"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl")

from tools.stats_canonical import (grade, load_bench, monthly_excesses,
                                   bench_monthly, sigma_m, soft_scores, calibrate_theta)
import tools.stats_canonical as sc
from tuner.alpha_orchestrator import run_backtest, build_fund_pct
from models.wq_alpha_miner import WQAlphaParams
from models.wq_alpha_fast import prepare_fast_context

DATA = os.path.join(REPO, "framework", "data_cache")
BASE_FORMULA = os.path.join(REPO, "models/alpha_formulas/alpha_076a.py")
OUT = os.path.join(REPO, "reports/family_search_BTC_20261023")
CUR = os.path.join(OUT, "curves")
SCRATCH = f"/tmp/fsearch_BTC_{os.getpid()}"
os.makedirs(CUR, exist_ok=True)
os.makedirs(SCRATCH, exist_ok=True)

SEAL = pd.Timestamp("2026-07-28", tz="UTC")
START = "2021-01-01T00:00:00+00:00"
END = "2026-07-28T00:00:00+00:00"
FEE = 0.0008

ASSET = dict(symbol="BTC/USDT",
             csv=os.path.join(DATA, "okx_BTC_USDT_15m_20210101_20260928.csv"),
             cost=[os.path.join(DATA, "binance_BTCUSDT_funding_proxy_202101_202610.csv")])

# pre-registered grid (r3 family dimensions; center = committed 076a spec)
GRID_N = [163, 192, 221]
GRID_BUF = [0.85, 1.0, 1.15]
GRID_GATE = [0.595, 0.7, 0.805]
THETA_FROZEN = 0.598
SIGMA_FROZEN = 0.22

KEYS = ("mean_excess_pct_mo", "t", "worst_window_pct", "best_window_pct", "first_half_pct",
        "second_half_pct", "concentration", "neg_windows", "n_windows", "continuous_dd_pct",
        "july26_partial_pct", "time_in_pct", "worst_absolute_month_pct")

T0 = time.time()
PROG = os.path.join(SCRATCH, "progress.log")
def log(*a):
    line = f"[{time.time()-T0:6.0f}s] " + " ".join(str(x) for x in a)
    print(line, flush=True)
    with open(PROG, "a") as f:
        f.write(line + "\n")


class GuardRelease:
    """Release ONLY stats_canonical's unit-tripwire (in-process, disclosed; the
    portability-076a convention — BTC extremes are less likely than SOL's but the
    lawful release path with audit trail is kept identical). Ruler arithmetic stays
    byte-identical; tools/stats_canonical.py is NOT touched."""
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
    try:
        return grade(eq, bench, name, pos=pos), None
    except AssertionError:
        with GuardRelease() as g:
            g_out = grade(eq, bench, name, pos=pos, trap_asserts=False)
        return g_out, {"released_values_pct": g.released}


def snapshot_base():
    src = open(BASE_FORMULA).read()
    for m in ["fund < 0.7", "tl - 1.0 * atr", "high.rolling(192, min_periods=96)",
              "low.rolling(192, min_periods=96)", "tr.rolling(96, min_periods=32)",
              "funding_gate_pctl=0.7", "funding_gate_mode=\"formula\"", "warmup_candles=100"]:
        assert m in src, f"alpha_076a marker missing: {m}"
    return hashlib.md5(src.encode()).hexdigest()[:12]


def write_variant(name, src, must_contain):
    p = os.path.join(SCRATCH, name)
    with open(p, "w") as f:
        f.write(src)
    back = open(p).read()
    for m in must_contain:
        assert m in back, f"variant {name} lost marker {m} (clobber?)"
    return p


def make_formula(N, buf, gate):
    """076a with N/buf/gate substituted (076c-pilot jitter replacements verbatim).
    gate=None -> raw latch (anchor): gate line replaced by always-True."""
    src = open(BASE_FORMULA).read()
    src = src.replace("high.rolling(192, min_periods=96)",
                      f"high.rolling({N}, min_periods={N//2})")
    src = src.replace("low.rolling(192, min_periods=96)",
                      f"low.rolling({N}, min_periods={N//2})")
    src = src.replace("tl - 1.0 * atr", f"tl - {buf} * atr")
    markers = [f"high.rolling({N}, min_periods={N//2})",
               f"low.rolling({N}, min_periods={N//2})", f"tl - {buf} * atr"]
    if gate is None:
        src = src.replace("uncrowded = (fund < 0.7).fillna(False)",
                          "uncrowded = pd.Series(True, index=close.index)")
        markers.append("uncrowded = pd.Series(True, index=close.index)")
        assert "fund < 0.7" not in src
    else:
        src = src.replace("fund < 0.7", f"fund < {gate}")
        markers.append(f"fund < {gate}")
    name = (f"fam_N{N}_buf{buf}_g{gate}.py" if gate is not None
            else f"anchor_rawlatch_N{N}_buf{buf}.py")
    return write_variant(name, src, markers)


def jitter_neighbors(N, buf, gate):
    """+/-15% per dimension, 6 neighbors. N -> nearest int; buf/gate -> 3 dp."""
    def rn(v): return int(round(v))
    def r3(v): return round(v, 3)
    return [("N_dn", (rn(N * 0.85), buf, gate)), ("N_up", (rn(N * 1.15), buf, gate)),
            ("buf_dn", (N, r3(buf * 0.85), gate)), ("buf_up", (N, r3(buf * 1.15), gate)),
            ("gate_dn", (N, buf, r3(gate * 0.85))), ("gate_up", (N, buf, r3(gate * 1.15)))]


# ── funding plumbing (portability_076a verbatim; BTC = binance proxy only) ──
def _load_settled(path):
    d = pd.read_csv(path)
    try:
        t = pd.to_datetime(d["ts"], utc=True)
    except ValueError:
        t = pd.to_datetime(d["ts"], utc=True, format="mixed")
    rcol = "rate" if "rate" in d.columns else "fundingRate"
    s = pd.Series(d[rcol].astype(float).values, index=t.dt.floor("8h"))
    return s[~s.index.duplicated(keep="last")].sort_index()


def funding_cost_buckets():
    parts = [_load_settled(p).rename(i) for i, p in enumerate(ASSET["cost"])]
    m = pd.concat(parts, axis=1).mean(axis=1, skipna=True)
    return pd.DataFrame({"bucket": m.index, "rate": m.values}).sort_values("bucket").reset_index(drop=True)


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
    """fee 0.0008 on |dpos|; funding -rate*pos at 00/08/16 bars (portability law)."""
    ret = eq_free.pct_change().fillna(0.0)
    net = ret.copy()
    if fee:
        net = net - FEE * pos.diff().abs().fillna(0.0)
    if fund:
        is_settle = (x_index.hour % 8 == 0) & (x_index.minute == 0)
        fr = pd.Series(np.where(is_settle, np.nan_to_num(fr_bar), 0.0), index=x_index)
        net = net - fr * pos
    return pd.Series(np.cumprod(1.0 + net.values), index=x_index) * eq_free.iloc[0]


def substrate_book(pos_eff, close, fr_bar, x_index, fund=True):
    """Genuine-relabel book on the bar-arithmetic substrate (r3 DECLARED_GRID law):
    ret=close.pct_change; strat=eff*ret; fee=0.0008*|d eff|; funding -rate*eff at 8h."""
    r = close.pct_change().fillna(0.0)
    eff = pos_eff.fillna(0.0)
    net = eff * r - FEE * eff.diff().abs().fillna(0.0)
    if fund:
        is_settle = (x_index.hour % 8 == 0) & (x_index.minute == 0)
        fr = pd.Series(np.where(is_settle, np.nan_to_num(fr_bar), 0.0), index=x_index)
        net = net - fr * eff
    eq = pd.Series(np.cumprod(1.0 + net.values), index=x_index)
    return eq * (100.0 / eq.iloc[0])


def engine_run(formula_path, tag=""):
    """Portability-076a engine path, BTC: fast ctx + fund_pct injection seam
    (asset's OWN binance settled series; lazy attach would default to ETH)."""
    ctx = prepare_fast_context(ASSET["csv"], None, formula_path)
    if ctx.fund_pct is None:
        df = pd.read_csv(ASSET["csv"], parse_dates=["timestamp"], index_col="timestamp")
        df.sort_index(inplace=True)
        ctx.fund_pct = build_fund_pct(df, "binance", ASSET["symbol"])
    p = WQAlphaParams(
        formula_path=formula_path, long_threshold=0.5, short_threshold=0.55,
        signal_smoothing=1, atr_period=14, atr_stop_mult=50.0, atr_take_mult=50.0,
        max_position_pct=1.0, warmup_candles=100, use_bias_filter=False,
        signal_exit_threshold=0.5, use_funding_gate=True, funding_gate_pctl=0.7,
        funding_input="binance", funding_gate_mode="formula", use_btc_mom_gate=False)
    eq = run_backtest(p, ASSET["symbol"], "15m", "15m", {"15m": ASSET["csv"]},
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


def close_series():
    x = pd.read_csv(ASSET["csv"])
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
    x = x[(x.timestamp >= pd.Timestamp(START)) & (x.timestamp <= SEAL)].reset_index(drop=True)
    x.index = x["timestamp"]
    return x


def anchored_score(eq_netfund, bench, bm):
    ex = monthly_excesses(eq_netfund, bench)
    s = soft_scores(ex, bm.values, THETA_FROZEN, SIGMA_FROZEN)
    return {"soft_mean": round(float(s.mean()), 3),
            "soft_t": round(float(s.mean() / s.std(ddof=1)), 3) if s.std(ddof=1) > 0 else None}


def main():
    R = {"run": "076a-family parameter search BTC-USDT 15m (pre-registered; "
                "REPORT.md pre-registration section is normative)",
         "date": "2026-10-23",
         "contract": "AGENT_CONTRACT.md in full; ruler = tools/stats_canonical.grade ONLY",
         "engine": "portability_076a path verbatim (formula-mode, fund_pct injection, "
                   "decide@close fill@next-open, 2x rails, long-only, engine fee=0.0, warmup 100)",
         "costs": "fee 0.0008 netted on |dpos|; funding = binance settled proxy "
                  "(binance_BTCUSDT_funding_proxy_202101_202610.csv) at 00/08/16 UTC bars",
         "headline_book": "netfund (netted+funding)",
         "grid_source": "ETH r3 family dimensions recovered: reports/bull_mining_r3/REPORT.md "
                        "§Robustness + jitter_bin_g0.7.json (N{163,192,221} x gate{0.595,0.7,0.805} "
                        "x buf{0.85,1.0,1.15} = 27); mp=N/2 per brief",
         "theta_frozen": THETA_FROZEN, "sigma_frozen": SIGMA_FROZEN}
    R["base_formula_md5"] = snapshot_base()
    log("base formula alpha_076a md5:", R["base_formula_md5"])

    x = close_series()
    close = x["close"]
    bench = load_bench(ASSET["csv"])
    bench = bench[bench.index <= SEAL].sort_index()
    fund = funding_cost_buckets()
    fr_bar = fund_to_bars(x, fund)
    x_index = close.index
    bm = bench_monthly(bench)
    sig_m = sigma_m(bench)
    R["sigma_m_bench_btc"] = round(sig_m, 4)
    log("BTC bench monthly sigma_m:", R["sigma_m_bench_btc"], "(frozen exam sigma:", SIGMA_FROZEN, ")")

    # ── anchor: SAME-ASSET raw latch (gate OFF), netted ──────────────────
    log("anchor run: raw latch N192 buf1.0 gate OFF ...")
    apath = make_formula(192, 1.0, None)
    eqA, posA = engine_run(apath, tag="anchor_raw")
    eqA_nf = netting_on_curve(eqA, posA, fr_bar, x_index, fund=False)
    eqA_nfund = netting_on_curve(eqA, posA, fr_bar, x_index, fund=True)
    gA_nf, relA1 = grade_canonical(eqA_nf, bench, "anchor_rawlatch_netted", posA)
    gA_nfund, relA2 = grade_canonical(eqA_nfund, bench, "anchor_rawlatch_netfund", posA)
    asc = anchored_score(eqA_nfund, bench, bm)
    theta_inv = calibrate_theta(monthly_excesses(eqA_nfund, bench), bm.values, sig_m, target=0.3)
    R["anchor"] = {"spec": "BTC raw turtle192 latch, N192/buf1.0, NO funding gate, netfund",
                   "netted": {k: gA_nf[k] for k in KEYS}, "netfund": {k: gA_nfund[k] for k in KEYS},
                   "anchored_v3_2": asc, "theta_inversion_check_btc": theta_inv,
                   "guard_release": {"netted": relA1, "netfund": relA2}}
    log("anchor netfund:", gA_nfund["mean_excess_pct_mo"], "t", gA_nfund["t"],
        "| anchored score:", asc["soft_mean"], "| theta inversion check:", theta_inv)
    eqA_nfund.to_csv(os.path.join(CUR, "anchor_rawlatch_netfund.csv.gz"), compression="gzip")
    pd.DataFrame({"pos": posA}).to_csv(os.path.join(CUR, "anchor_rawlatch_pos.csv.gz"), compression="gzip")
    ANCHOR_LINE = asc["soft_mean"]

    # ── Phase 1: 27-config screen ────────────────────────────────────────
    R["configs"] = {}
    rows = []
    passers = []
    cache = {}   # tag -> (eq_nfund, pos) — battery reuses the exact screening curve
    for N in GRID_N:
        for buf in GRID_BUF:
            for gate in GRID_GATE:
                tag = f"N{N}_buf{buf}_g{gate}"
                fpath = make_formula(N, buf, gate)
                eq, pos = engine_run(fpath, tag=tag)
                eq_nf = netting_on_curve(eq, pos, fr_bar, x_index, fund=False)
                eq_nfund = netting_on_curve(eq, pos, fr_bar, x_index, fund=True)
                g_nf, rel1 = grade_canonical(eq_nf, bench, f"{tag}_netted", pos)
                g_nfund, rel2 = grade_canonical(eq_nfund, bench, f"{tag}_netfund", pos)
                screen = bool(g_nfund["mean_excess_pct_mo"] > 0
                              and g_nfund["worst_absolute_month_pct"] >= -40
                              and g_nfund["first_half_pct"] >= 0
                              and g_nfund["second_half_pct"] >= 0)
                R["configs"][tag] = {"N": N, "buf": buf, "gate": gate,
                                     "netted_mean_excess_pct_mo": g_nf["mean_excess_pct_mo"],
                                     "netted": {k: g_nf[k] for k in KEYS},
                                     "netfund": {k: g_nfund[k] for k in KEYS},
                                     "screen_pass": screen,
                                     "guard_release": {"netted": rel1, "netfund": rel2}}
                if screen:
                    passers.append(tag)
                    cache[tag] = (eq_nfund, pos)
                    eq_nfund.to_csv(os.path.join(CUR, f"{tag}_netfund.csv.gz"), compression="gzip")
                    pd.DataFrame({"pos": pos}).to_csv(os.path.join(CUR, f"{tag}_pos.csv.gz"),
                                                      compression="gzip")
                g = g_nfund
                rows.append({"config": tag, "N": N, "buf": buf, "gate": gate,
                             "mean_excess_pct_mo": g["mean_excess_pct_mo"], "t": g["t"],
                             "worst_window_pct": g["worst_window_pct"],
                             "worst_absolute_month_pct": g["worst_absolute_month_pct"],
                             "first_half_pct": g["first_half_pct"], "second_half_pct": g["second_half_pct"],
                             "continuous_dd_pct": g["continuous_dd_pct"], "time_in_pct": g["time_in_pct"],
                             "screen_pass": screen})
                log(f"{tag}: netfund {g['mean_excess_pct_mo']} t {g['t']} "
                    f"worstabs {g['worst_absolute_month_pct']} halves "
                    f"{g['first_half_pct']}/{g['second_half_pct']} -> screen {'PASS' if screen else 'fail'}")
                pd.DataFrame(rows).to_csv(os.path.join(OUT, "grid.csv"), index=False)
                json.dump(R, open(os.path.join(OUT, "results.json"), "w"), indent=1)
    log(f"screen: {len(passers)}/{len(rows)} pass -> {passers}")

    # ── Phase 2 battery (passers only) ───────────────────────────────────
    battery = {}
    for tag in passers:
        ent = R["configs"][tag]
        N, buf, gate = ent["N"], ent["buf"], ent["gate"]
        log(f"battery {tag} ...")
        b = {"jitter": {}, "jitter_6of6": None, "shift2": {}, "retention_netfund": None,
             "anchored": None, "clears_anchor_line": None, "battery_pass": None}
        # 1) jitter: 6 neighbors, sign-stable + halves >= 0 (netfund)
        ok = True
        for jtag, (jn, jb, jg) in jitter_neighbors(N, buf, gate):
            jp = make_formula(jn, jb, jg)
            eqj, posj = engine_run(jp, tag=f"{tag}_{jtag}")
            eqj_nfund = netting_on_curve(eqj, posj, fr_bar, x_index, fund=True)
            gj, _ = grade_canonical(eqj_nfund, bench, f"{tag}_{jtag}_netfund", posj)
            stable = bool(gj["mean_excess_pct_mo"] > 0 and gj["first_half_pct"] >= 0
                          and gj["second_half_pct"] >= 0)
            ok = ok and stable
            b["jitter"][jtag] = {"params": {"N": jn, "buf": jb, "gate": jg},
                                 "mean_excess_pct_mo": gj["mean_excess_pct_mo"], "t": gj["t"],
                                 "first_half_pct": gj["first_half_pct"],
                                 "second_half_pct": gj["second_half_pct"], "stable": stable}
            log(f"  jitter {jtag} N{jn} buf{jb} g{jg}: {gj['mean_excess_pct_mo']} "
                f"halves {gj['first_half_pct']}/{gj['second_half_pct']} -> {'ok' if stable else 'FLIP'}")
        b["jitter_6of6"] = ok
        # 2) genuine shift-2 retention (substrate relabel; both legs same substrate)
        eq_nfund, pos = cache[tag]
        eq1 = substrate_book(pos, close, fr_bar, x_index, fund=True)
        eq2 = substrate_book(pos.shift(1), close, fr_bar, x_index, fund=True)
        g1, _ = grade_canonical(eq1, bench, f"{tag}_substrate_center", pos)
        g2, _ = grade_canonical(eq2, bench, f"{tag}_substrate_shift2", pos.shift(1))
        m1, m2 = g1["mean_excess_pct_mo"], g2["mean_excess_pct_mo"]
        ret = round(m2 / m1, 3) if m1 > 0 else None
        b["shift2"] = {"center_mean": m1, "shift2_mean": m2,
                       "retention_netfund": ret, "passes": bool(ret is not None and ret >= 0.25)}
        b["retention_netfund"] = ret
        # 3) anchored exam v3.2 vs same-asset raw-latch anchor line
        asc = anchored_score(eq_nfund, bench, bm)
        b["anchored"] = asc
        b["clears_anchor_line"] = bool(asc["soft_mean"] > ANCHOR_LINE)
        b["battery_pass"] = bool(ok and b["shift2"]["passes"] and b["clears_anchor_line"])
        battery[tag] = b
        R["configs"][tag]["battery"] = b
        log(f"  battery {tag}: jitter {ok} retention {ret} anchored {asc['soft_mean']} "
            f"(anchor line {ANCHOR_LINE}) -> {'PASS' if b['battery_pass'] else 'fail'}")
        json.dump(R, open(os.path.join(OUT, "results.json"), "w"), indent=1)
    R["anchor_line_soft_mean"] = ANCHOR_LINE
    R["battery"] = battery

    # ── best-by-exam + survivor flags (pre-registered branch) ────────────
    full_pass = [t for t, b in battery.items() if b["battery_pass"]]
    R["full_battery_pass"] = full_pass
    best = None
    if full_pass:
        def sort_key(t):
            c = R["configs"][t]
            return (-battery[t]["anchored"]["soft_mean"], c["N"], c["gate"])
        best = sorted(full_pass, key=sort_key)[0]
    R["best_by_exam"] = best
    R["outcome"] = ("survivor -> flagged for holdout-style confirmation, NOT deployment"
                    if full_pass else
                    "no config passed the pre-registered battery -> ledgered no-pass")
    json.dump(R, open(os.path.join(OUT, "results.json"), "w"), indent=1)
    df = pd.DataFrame(rows)
    df["jitter_6of6"] = df["config"].map(lambda t: battery.get(t, {}).get("jitter_6of6"))
    df["retention_sh2"] = df["config"].map(lambda t: battery.get(t, {}).get("retention_netfund"))
    df["anchored_score"] = df["config"].map(
        lambda t: (battery.get(t, {}) or {}).get("anchored") or None)
    df["anchored_score"] = df["anchored_score"].map(lambda a: None if a is None else a.get("soft_mean"))
    df["clears_anchor_line"] = df["config"].map(lambda t: battery.get(t, {}).get("clears_anchor_line"))
    df["battery_pass"] = df["config"].map(lambda t: battery.get(t, {}).get("battery_pass"))
    df["survivor"] = df["battery_pass"].fillna(False).astype(bool)
    df.to_csv(os.path.join(OUT, "grid.csv"), index=False)
    log(f"DONE. passers {len(passers)}, full-battery {full_pass}, best {best}. -> {OUT}")


if __name__ == "__main__":
    main()
