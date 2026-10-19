#!/usr/bin/env python3
"""Bull mining round 3 lab — solid bases only.

Engine law: mining runs on bar arithmetic (compose_portfolio convention).
Grading law: ONLY tools.stats_canonical.grade. No self-written stats.
Read-only repo. Writes: /tmp/bull_r3/out and reports/bull_mining_r3/.
"""
import os, sys, json
import numpy as np
import pandas as pd

REPO = "/home/node/.openclaw/workspace/crypto"
sys.path.insert(0, REPO)
os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl")

DATA = os.path.join(REPO, "framework", "data_cache")
EXEC_CSV = os.path.join(DATA, "okx_ETH_USDT_15m_20210101_20260928.csv")
FUND_CSVS = {
    "bin": os.path.join(DATA, "binance_ETHUSDT_funding_proxy_202101_202610.csv"),
    "byb": os.path.join(DATA, "bybit_ETHUSDT_funding_202101_202610.csv"),
}
SEAL = pd.Timestamp("2026-07-28", tz="UTC")
FEE = 0.0008
OUT = "/tmp/bull_r3/out"
os.makedirs(OUT, exist_ok=True)

from tools.stats_canonical import grade, load_bench  # canonical ruler


def to_ns(s):
    try:
        a = pd.to_datetime(s, utc=True)
    except ValueError:
        a = pd.to_datetime(s, utc=True, format="mixed")
    return a.astype("datetime64[ns, UTC]")


def load_exec():
    df = pd.read_csv(EXEC_CSV)
    df["timestamp"] = to_ns(df["timestamp"])
    df = df[(df.timestamp >= pd.Timestamp("2021-01-01", tz="UTC")) & (df.timestamp <= SEAL)]
    df = df.reset_index(drop=True)
    df.index = df["timestamp"]
    return df


def load_funding(key):
    """key in {bin, byb, avg}: per-8h-settlement rates + causal 30d percentile (no bfill)."""
    def rd(p, tcol, rcol):
        d = pd.read_csv(p)
        t = to_ns(d[tcol])
        return pd.DataFrame({"bucket": t.dt.floor("8h"), "rate": d[rcol].astype(float)})
    if key == "avg":
        a, b = rd(FUND_CSVS["bin"], "ts", "rate"), rd(FUND_CSVS["byb"], "ts", "fundingRate")
        m = a.merge(b, on="bucket", suffixes=("_bin", "_byb"), how="outer")
        m["rate"] = m[["rate_bin", "rate_byb"]].mean(axis=1, skipna=True)
        m = m.sort_values("bucket").reset_index(drop=True)
    else:
        tcol, rcol = ("ts", "rate") if key == "bin" else ("ts", "fundingRate")
        m = rd(FUND_CSVS[key], tcol, rcol).sort_values("bucket").reset_index(drop=True)
    r = m["rate"].values
    pctl = np.full(len(r), np.nan)
    W = 90
    for i in range(W, len(r)):
        pctl[i] = (r[i - W:i] <= r[i]).mean()
    m["fpct"] = pctl
    return m


def fund_to_bars(exec_df, fund):
    """Per exec bar: latest SETTLED rate/fpct (settlement ts <= bar close ts)."""
    bar_close = (exec_df["timestamp"] + pd.Timedelta("15min")).astype("int64").values
    fb = fund["bucket"].astype("int64").values
    idx = np.searchsorted(fb, bar_close, side="right") - 1
    ok = idx >= 0
    idxc = np.clip(idx, 0, len(fund) - 1)
    cols = {}
    for c in ("rate", "fpct"):
        v = fund[c].values[idxc].astype(float)
        v[~ok] = np.nan
        cols[c] = v
    return cols


def atr96(df):
    """Round-1 convention: SMA of TR, n=96, min_periods=32."""
    h, l, c = df["high"], df["low"], df["close"]
    prev = c.shift(1)
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(96, min_periods=32).mean()


def turtle_latch(df, N=192, buf=1.0, entry_mask=None):
    """Round-1 latch: ev[exit]=0, ev[entry]=1 (entry precedence), ffill->0.
    Returns DECISION position series (decided at close t, effective t+1)."""
    c = df["close"]
    th = df["high"].rolling(N, min_periods=N // 2).max().shift(1)
    tl = df["low"].rolling(N, min_periods=N // 2).min().shift(1)
    a = atr96(df)
    above = (c > th)
    if entry_mask is not None:
        above = above & entry_mask
    below = (c < tl - buf * a)
    ev = pd.Series(np.nan, index=c.index)
    ev[below] = 0.0
    ev[above] = 1.0
    return ev.ffill().fillna(0.0)


def confirmed_breakout_pos(df, N, m, entry_mask=None):
    c = df["close"]
    th = df["high"].rolling(N, min_periods=N // 2).max().shift(1)
    above = (c > th)
    if entry_mask is not None:
        above = above & entry_mask
    run = np.zeros(len(c), dtype=int)
    r = 0
    ab = above.values
    for i in range(len(ab)):
        r = r + 1 if ab[i] else 0
        run[i] = r
    entry = pd.Series(run >= m, index=c.index)
    # latch: entry event raises, turtle exit lowers
    tl = df["low"].rolling(N, min_periods=N // 2).min().shift(1)
    a = atr96(df)
    below = (c < tl - 1.0 * a)
    ev = pd.Series(np.nan, index=c.index)
    ev[below] = 0.0
    ev[entry] = 1.0
    return ev.ffill().fillna(0.0)


def vol_scaled(pos, df, sigma_target, smin):
    sigma = atr96(df) / df["close"]
    size = (sigma_target / sigma).clip(lower=smin, upper=1.0)
    return (pos * size.fillna(0.0)).where(pos > 0, 0.0)


def sim_curve(exec_df, pos, fund_rate_bar):
    """compose_portfolio substrate. pos = decision series; eff = shift(1)."""
    c = exec_df["close"]
    eff = pos.shift(1).fillna(0.0)
    ret1 = c.pct_change().fillna(0.0)
    gross = eff * ret1
    fee = FEE * eff.diff().abs().fillna(0.0)
    is_settle = (exec_df["timestamp"].dt.hour % 8 == 0) & (exec_df["timestamp"].dt.minute == 0)
    fr = pd.Series(np.where(is_settle, np.nan_to_num(fund_rate_bar), 0.0), index=c.index)
    fc = fr * eff  # long pays positive funding
    net = gross - fee - fc
    return pd.Series(np.cumprod(1.0 + net.values), index=c.index, name="equity")


def bench_close():
    b = load_bench(EXEC_CSV)
    return b[b.index <= SEAL].sort_index()


# ── stage: anchor ────────────────────────────────────────────────
def stage_anchor():
    x = load_exec()
    b = bench_close()
    out = {}
    pos = turtle_latch(x)  # raw turtle192
    eq_gross = sim_curve(x, pos, np.zeros(len(x)))
    out["A1_gross_fees_only"] = grade(eq_gross, b, name="anchor_A1_raw_turtle192_gross", pos=pos)
    fb = fund_to_bars(x, load_funding("bin"))
    eq_net = sim_curve(x, pos, fb["rate"])
    out["A2_net_binance_funding"] = grade(eq_net, b, name="anchor_A2_raw_turtle192_funding_charged", pos=pos)
    save = pd.DataFrame({"timestamp": x["timestamp"], "equity": eq_net.values, "position": pos.values})
    save.to_pickle("/home/node/.openclaw/workspace/crypto/reports/bull_mining_r3/curves/anchor_raw192_net.pkl")
    print(json.dumps(out, indent=1))
    json.dump(out, open(f"{OUT}/anchor.json", "w"), indent=1)
    return out


# ── stage: lanes ─────────────────────────────────────────────────
def lane_months():
    from tools.regime_grid import regime_array
    bench = pd.read_csv(EXEC_CSV, parse_dates=["timestamp"], index_col="timestamp").sort_index()
    meta = json.load(open(os.path.join(REPO, "data/precompute/regime_grid.json")))
    m = [x for x in meta if x["i"] == 7][0]
    arr = regime_array(bench, m["donchian"], m["confirm"], m["vol_enter"], m["vol_exit"],
                       m["grind_slope"], m["grind_confirm"])
    lane = pd.Series(arr, index=bench.index)
    months = pd.date_range("2021-04-01", "2026-07-01", freq="MS", tz="UTC")
    dom, exp_months, other = [], [], []
    for s in months:
        e = s + pd.DateOffset(months=1)
        w = lane[(lane.index >= s) & (lane.index < e)]
        d = int(w.mode().iloc[0])
        dom.append((str(s.date()), d, round(float((w == d).mean()), 3)))
        (exp_months if d == 3 else other).append(s)
    return exp_months, other, dom


def stage_lanes():
    exp_months, other, dom = lane_months()
    print(f"expansion-dominant months: {len(exp_months)} / {len(dom)}")
    print("non-expansion months:", [d[0] for d in dom if d[1] != 3])
    json.dump({"expansion_months": [str(m.date()) for m in exp_months],
               "other_months": [str(m.date()) for m in other],
               "dominant": dom}, open(f"{OUT}/lanes.json", "w"), indent=1)


# ── stage: mine ──────────────────────────────────────────────────
def run_one(tag, exec_df, pos, b, exp_months, fund_key_cost="avg"):
    eq_gross = sim_curve(exec_df, pos, np.zeros(len(exec_df)))
    fr = fund_to_bars(exec_df, load_funding(fund_key_cost))["rate"]
    eq_net = sim_curve(exec_df, pos, fr)
    g_gross = grade(eq_gross, b, name=f"{tag}_gross")
    g_net = grade(eq_net, b, name=tag)
    g_lane = grade(eq_net, b, name=f"{tag}_inlane", months_mask=exp_months)
    return {"tag": tag, "gross": g_gross, "net": g_net, "inlane": g_lane}


def stage_mine():
    x = load_exec()
    b = bench_close()
    exp_months, _, _ = lane_months()
    funds = {k: fund_to_bars(x, load_funding(k)) for k in ("bin", "byb", "avg")}
    results = []

    # C: funding-gated turtle192, per-input gates (0.5 / 0.7)
    for inp in ("bin", "byb", "avg"):
        fp = funds[inp]["fpct"]
        fpi = pd.Series(fp, index=x.index)
        for g in (0.5, 0.7):
            mask = (fpi < g).fillna(False)
            pos = turtle_latch(x, entry_mask=mask)
            r = run_one(f"C_t192_{inp}_g{g}", x, pos, b, exp_months)
            results.append(r)

    # A: confirmed breakout N x m, ungated
    for N in (144, 192, 288):
        for m in (2, 3):
            pos = confirmed_breakout_pos(x, N, m)
            results.append(run_one(f"A_cb_N{N}_m{m}", x, pos, b, exp_months))

    # B: vol-scaled turtle192, ungated
    for st in (0.004, 0.005, 0.006):
        for smin in (0.25, 0.5):
            pos0 = turtle_latch(x)
            pos = vol_scaled(pos0, x, st, smin)
            results.append(run_one(f"B_vs_st{st}_smin{smin}", x, pos, b, exp_months))

    # D: washout-restart turtle192 (NEW family)
    c = x["close"]
    hi90 = c.rolling(90 * 96, min_periods=45 * 96).max()
    rel = c / hi90
    for K in (30, 60):
        relmin = rel.rolling(K * 96, min_periods=K * 48).min()
        for D in (0.20, 0.30):
            wash = (relmin <= 1.0 - D).fillna(False)
            pos = turtle_latch(x, entry_mask=wash)
            results.append(run_one(f"D_wash_K{K}_D{D}", x, pos, b, exp_months))

    json.dump(results, open(f"{OUT}/mine_stage1.json", "w"), indent=1)
    # compact view
    for r in results:
        n, i = r["net"], r["inlane"]
        print(f"{r['tag']:24s} net {n['mean_excess_pct_mo']:+.2f} t {n['t']} | "
              f"inlane {i['mean_excess_pct_mo']:+.2f} t {i['t']} halves {i['first_half_pct']:+.1f}/{i['second_half_pct']:+.1f} "
              f"worst {i['worst_window_pct']:+.1f} | abs_worst {n['worst_absolute_month_pct']:+.1f} | jul {n['july26_partial_pct']:+.1f}")


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "anchor"
    {"anchor": stage_anchor, "lanes": stage_lanes, "mine": stage_mine}[stage]()
