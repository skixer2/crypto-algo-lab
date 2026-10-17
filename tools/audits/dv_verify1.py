#!/usr/bin/env python3
"""Independent adversarial verification of blender v2.1g — deepseek review 2026-10-16.
Read-only on repo; writes only to /tmp. Verifies by recomputation, not trust.
"""
import json, os, sys
import numpy as np
import pandas as pd

REPO = "/home/node/.openclaw/workspace/crypto"
PRE = os.path.join(REPO, "data/precompute")
FEE = 0.0008
LANES = ["confirmed_bearish", "grind_down", "vol_compressed", "expansion"]

V21G = json.load(open(f"{REPO}/tuner/runs/blender_v21g.json"))
DET = V21G["detector"]

def load_specialists():
    man = json.load(open(os.path.join(PRE, "manifest.json")))
    curves, names, pos = [], [], {}
    for f in sorted(man.keys()):
        df = pd.read_csv(os.path.join(PRE, f"{f}.csv.gz"))
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        d = df.set_index("timestamp")
        curves.append(d["equity"])
        pos[f] = d["position"] if "position" in d.columns else pd.Series(0.0, index=d.index)
        names.append(f)
    eq = pd.concat(curves, axis=1); eq.columns = names
    P = pd.concat([pos[n] for n in names], axis=1); P.columns = names
    return eq, names, P

print("== loading ==")
eq, names, P = load_specialists()
print("specialists:", names)
print("eq index span:", eq.index[0], "->", eq.index[-1], "rows:", len(eq))
print("index monotonic:", eq.index.is_monotonic_increasing, "| dup:", eq.index.duplicated().sum())
gaps = eq.index.to_series().diff().value_counts()
print("bar spacing:", gaps.head(4).to_dict())
print("NaN count in eq:", int(eq.isna().sum().sum()), "| per-col:", eq.isna().sum().to_dict())
print("position dtypes:", P.dtypes.to_dict())
print("position ranges:", {c: (float(P[c].min()), float(P[c].max())) for c in P.columns})
print("zero-position coverage (all flat rows):", int((P.abs().sum(axis=1) == 0).sum()))

# per-specialist warmup check: first non-nan
for c in eq.columns:
    s = eq[c].dropna()
    print(f"  {c}: first {s.index[0]}, last {s.index[-1]}, n={len(s)}")

# bench
bench = pd.read_csv(os.path.join(REPO, "framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv"),
                    parse_dates=["timestamp"], index_col="timestamp").sort_index()
bench = bench.loc[eq.index[0]:]

# regime grid
z = np.load(os.path.join(PRE, "regime_grid.npz"))
gidx = pd.DatetimeIndex(z["index"].astype("int64"))
print("\n== grid alignment ==")
pos_in_full = gidx.asi8.searchsorted(pd.DatetimeIndex(eq.index).asi8)
print("grid covers all rets stamps:", bool((gidx[pos_in_full] == eq.index).all()))
print("grid dup:", gidx.duplicated().sum())
meta = json.load(open(os.path.join(PRE, "regime_grid.json")))
print("detector", DET, "params:", meta[DET])

# replicate blender rets
rets = eq.pct_change().fillna(0.0)
POS = P.fillna(0.0)

# months grid (blender main())
starts = pd.date_range("2021-04-01", "2026-06-01", freq="MS", tz="UTC")
months = [(s, s + pd.DateOffset(months=1)) for s in starts]
print("n windows:", len(months))

# lane-of-bar from grid codes, detector DET
grid_codes = z["lanes"][:, pos_in_full]
lane_of_bar = grid_codes[DET]

# weights matrix from stored (3dp) weights — renormalize lanes like compose does
nsp = len(names)
W = np.zeros((4, nsp))
for ln in V21G["weights"]:
    for a, w in V21G["weights"][ln].items():
        W[LANES.index(ln)][names.index(a)] = w
lane_sums = W.sum(axis=1)
print("lane weight sums:", dict(zip(LANES, lane_sums.round(4))))
Wr = W / np.where(lane_sums[:, None] > 1.0, lane_sums[:, None], 1.0)  # same renorm as blender

def build_wl(lane_arr, Wmat):
    wl = np.zeros((len(lane_arr), nsp))
    for li in range(4):
        wl[lane_arr == li] = Wmat[li]
    return wl

def port_from(wl, rets_mat, pos_mat, fee_term=True):
    w_ret = (wl * rets_mat).sum(axis=1)
    net_expo = (wl * pos_mat).sum(axis=1)
    turn = np.abs(np.diff(net_expo, prepend=0.0))
    pr = w_ret - (FEE * turn if fee_term else 0.0)
    return pd.Series(np.cumprod(1 + pr), index=eq.index), pr, net_expo, turn

def window_metrics(port_eq, bench_close, s, e):
    m = port_eq[(port_eq.index >= s) & (port_eq.index < e)]
    b = bench_close[(bench_close.index >= s) & (bench_close.index < e)]
    if len(m) < 2 or len(b) < 2: return None
    strat = (float(m.iloc[-1]) / float(m.iloc[0]) - 1) * 100
    bret = (float(b.iloc[-1]) / float(b.iloc[0]) - 1) * 100
    return {"strat": strat, "bench": bret, "excess": strat - bret}

def summarize(port_eq, label):
    rows = []
    for (s, e) in months:
        wv = window_metrics(port_eq, bench["close"], s, e)
        if wv: rows.append(wv)
    exc = np.array([r["excess"] for r in rows])
    t = exc.mean() / (exc.std(ddof=1) / np.sqrt(len(exc)))
    peak = port_eq.cummax()
    cmdd = ((peak - port_eq) / peak).max() * 100
    # windowed MDD (blender's run_mdd)
    wmdd = 0.0
    for (s, e) in months:
        m = port_eq[(port_eq.index >= s) & (port_eq.index < e)]
        if len(m) < 2: continue
        pk = m.cummax()
        wmdd = max(wmdd, ((pk - m) / pk).max() * 100)
    print(f"[{label}] n={len(rows)} mean_excess={exc.mean():+.4f}%  t={t:+.3f}  "
          f"winMDD={wmdd:.2f}%  contMDD={cmdd:.2f}%  ann={exc.mean()*12:+.1f}%")
    return exc, rows

wl = build_wl(lane_of_bar, Wr)
port_eq, pr, net_expo, turn = port_from(wl, rets.to_numpy(), POS.to_numpy())
exc0, rows0 = summarize(port_eq, "AS-BUILT wl[t]*rets[t]          ")
print("  official JSON: mean 7.3294 t 2.9607 winMDD 15.008 contMDD~19.5")

# ---- LOOKAHEAD TEST: lane shifted one bar (knowable at t-1 governs return of t)
wl_lag1 = build_wl(np.roll(lane_of_bar, 1), Wr); wl_lag1[0] = 0.0
port_eq_l1, pr_l1, ne_l1, tn_l1 = port_from(wl_lag1, rets.to_numpy(), np.roll(POS.to_numpy(), 1, axis=0))
exc_l1, _ = summarize(port_eq_l1, "FIX wl[t-1]*rets[t] (pos lag1)  ")

# variant: only lane shifted, pos kept as-is (fee timing convention A)
port_eq_l1b, *_ = port_from(wl_lag1, rets.to_numpy(), POS.to_numpy())
summarize(port_eq_l1b, "FIX wl[t-1]*rets[t] (pos as-is) ")

# ---- magnitude of lane flip frequency
flips = (lane_of_bar[1:] != lane_of_bar[:-1]).sum()
print(f"\nlane changes over {len(lane_of_bar)} bars: {flips} ({flips/len(lane_of_bar)*100:.1f}%)")
lane_share = {LANES[i]: round(float((lane_of_bar == i).mean()*100), 1) for i in range(4)}
print("lane shares %:", lane_share)

# ---- fee decomposition (as-built)
w_ret = (wl * rets.to_numpy()).sum(axis=1)
fee_series = FEE * turn
print(f"\n== fees (as-built) ==")
print(f"sum gross w_ret (arith, full span): {(w_ret.sum()*100):+.1f}%")
print(f"sum netted fees (arith): {(fee_series.sum()*100):+.2f}%  -> {fee_series.mean()*100*288*365/12:.4f}%/mo approx drag on mean monthly (arith)")
n_flip_mo = (np.sign(net_expo[1:]) != np.sign(net_expo[:-1])).sum() / ((eq.index[-1]-eq.index[0]).days/30.4)
print(f"net-exposure sign flips per month: {n_flip_mo:.1f}")
print(f"netted fee as % of portfolio notional traded/mo: {turn.mean()*288*30.4*100:.1f} (bars*mo avg turn)")

# ---- embedded per-specialist fees: gross (pos[t-1]*bench_ret) vs actual curve
print("\n== per-specialist embedded fee wedge (full-span arith, pct pts) ==")
bench_ret = bench["close"].pct_change().reindex(eq.index).fillna(0.0)
for c in names:
    gross = (POS[c].shift(1).fillna(0.0) * bench_ret).sum() * 100
    actual = rets[c].sum() * 100
    print(f"  {c}: gross {gross:+9.1f}%  curve {actual:+9.1f}%  wedge {actual-gross:+7.1f} pts "
          f"(fees+intra |pos|<1 + compounding), avg|pos|={POS[c].abs().mean():.2f}, flips/mo={(POS[c].diff().abs()>0).sum()/5.74:.0f}")

# ---- FTX month recomputation (independent slice)
print("\n== FTX month 2022-11 (as-built) ==")
s, e = pd.Timestamp("2022-11-01", tz="UTC"), pd.Timestamp("2022-12-01", tz="UTC")
m = port_eq[(port_eq.index >= s) & (port_eq.index < e)]
b = bench["close"][(bench.index >= s) & (bench.index < e)]
print(f"strat {(m.iloc[-1]/m.iloc[0]-1)*100:+.2f}% vs official JSON 22.15 | bench {(b.iloc[-1]/b.iloc[0]-1)*100:+.2f}% vs -17.74")

# ---- first/last window identity vs JSON
for wi in (0, 62):
    s, e = months[wi]
    wv = window_metrics(port_eq, bench["close"], s, e)
    j = V21G["windows"][wi]
    print(f"window {wi} {s.date()}: recomputed excess {wv['excess']:+.2f} vs JSON {j['excess']:+.2f} | mdd? strat {wv['strat']:+.2f}/{j['strat']:+.2f}")

# ---- t-stat robustness: autocorr + stationary bootstrap
exc = exc0
ac1 = pd.Series(exc).autocorr(1)
print(f"\n== t-stat robustness ==\nautocorr(1) of monthly excess: {ac1:+.3f}")
rng = np.random.default_rng(7)
n = len(exc)
ts_boot, means = [], []
for _ in range(20000):
    idx = rng.integers(0, n, n)
    means.append(exc[idx].mean())
lo, hi = np.percentile(means, [2.5, 97.5])
print(f"iid bootstrap mean-excess 95% CI: [{lo:+.2f}, {hi:+.2f}]  P(mean<=0)={np.mean(np.array(means)<=0)*100:.2f}%")
# block bootstrap (blocks of 3 months)
bs = []
for _ in range(20000):
    nb = int(np.ceil(n/3))
    starts_b = rng.integers(0, n, nb)
    sample = np.concatenate([exc[(s_+np.arange(3)) % n] for s_ in starts_b])[:n]
    bs.append(sample.mean())
lo3, hi3 = np.percentile(bs, [2.5, 97.5])
print(f"block-3 bootstrap mean-excess 95% CI: [{lo3:+.2f}, {hi3:+.2f}]  P(mean<=0)={np.mean(np.array(bs)<=0)*100:.2f}%")
# t with Newey-West style correction lag1
if abs(ac1) < 0.99:
    t_corr = exc.mean() / (exc.std(ddof=1)/np.sqrt(n) * np.sqrt((1+ac1)/(1-ac1)))
    print(f"t with lag-1 correction factor: {t_corr:+.3f} (vs naive {exc.mean()/(exc.std(ddof=1)/np.sqrt(n)):+.3f})")

# ---- 2026-07 data presence / holdout
print("\n== holdout ==")
print("rets index last:", eq.index[-1], "| official months end:", months[-1][1])
jul = window_metrics(port_eq, bench["close"], pd.Timestamp("2026-07-01", tz="UTC"), pd.Timestamp("2026-08-01", tz="UTC"))
aug = window_metrics(port_eq, bench["close"], pd.Timestamp("2026-08-01", tz="UTC"), pd.Timestamp("2026-09-01", tz="UTC"))
sep = window_metrics(port_eq, bench["close"], pd.Timestamp("2026-09-01", tz="UTC"), pd.Timestamp("2026-09-28", tz="UTC"))
print("2026-07 (in-seal, unused by blender):", {k: round(v,2) for k,v in jul.items()})
print("2026-08 (holdout):", {k: round(v,2) for k,v in aug.items()})
print("2026-09 partial (holdout):", {k: round(v,2) for k,v in sep.items()})
