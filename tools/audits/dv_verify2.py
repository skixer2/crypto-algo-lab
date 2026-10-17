#!/usr/bin/env python3
"""Part 2: mechanism decomposition + bounds + selection bias + DD episodes + holdout."""
import json, os
import numpy as np
import pandas as pd

REPO = "/home/node/.openclaw/workspace/crypto"
PRE = os.path.join(REPO, "data/precompute")
FEE = 0.0008
LANES = ["confirmed_bearish", "grind_down", "vol_compressed", "expansion"]
V21G = json.load(open(f"{REPO}/tuner/runs/blender_v21g.json"))
DET = V21G["detector"]

man = json.load(open(os.path.join(PRE, "manifest.json")))
curves, names, pos = [], [], {}
for f in sorted(man.keys()):
    df = pd.read_csv(os.path.join(PRE, f"{f}.csv.gz"))
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    d = df.set_index("timestamp")
    curves.append(d["equity"]); pos[f] = d["position"]; names.append(f)
eq = pd.concat(curves, axis=1); eq.columns = names
P = pd.concat([pos[n] for n in names], axis=1); P.columns = names
rets = eq.pct_change().fillna(0.0); POS = P.fillna(0.0)
bench = pd.read_csv(os.path.join(REPO, "framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv"),
                    parse_dates=["timestamp"], index_col="timestamp").sort_index()
bench_full = bench.copy()
bench = bench.loc[eq.index[0]:eq.index[-1]]

z = np.load(os.path.join(PRE, "regime_grid.npz"))
gidx = pd.DatetimeIndex(z["index"].astype("int64"))
pos_in_full = gidx.asi8.searchsorted(pd.DatetimeIndex(eq.index).asi8)
lane_of_bar = z["lanes"][:, pos_in_full][DET]

starts = pd.date_range("2021-04-01", "2026-06-01", freq="MS", tz="UTC")
months = [(s, s + pd.DateOffset(months=1)) for s in starts]

nsp = len(names)
W = np.zeros((4, nsp))
for ln in V21G["weights"]:
    for a, w in V21G["weights"][ln].items():
        W[LANES.index(ln)][names.index(a)] = w
lane_sums = W.sum(axis=1)
Wr = W / np.where(lane_sums[:, None] > 1.0, lane_sums[:, None], 1.0)

def wl_of(lane_arr):
    wl = np.zeros((len(lane_arr), nsp))
    for li in range(4):
        wl[lane_arr == li] = Wr[li]
    return wl

def stats(wl, pos_mat=POS.to_numpy(), rets_mat=rets.to_numpy()):
    w_ret = (wl * rets_mat).sum(axis=1)
    ne = (wl * pos_mat).sum(axis=1)
    turn = np.abs(np.diff(ne, prepend=0.0))
    pr = w_ret - FEE * turn
    pe = pd.Series(np.cumprod(1 + pr), index=eq.index)
    exc = []
    for s, e in months:
        m = pe[(pe.index >= s) & (pe.index < e)]
        b = bench["close"][(bench.index >= s) & (bench.index < e)]
        if len(m) < 2 or len(b) < 2: continue
        exc.append((m.iloc[-1]/m.iloc[0]-1)*100 - (b.iloc[-1]/b.iloc[0]-1)*100)
    exc = np.array(exc)
    t = exc.mean()/(exc.std(ddof=1)/np.sqrt(len(exc)))
    return exc.mean(), t

wl_t = wl_of(lane_of_bar)
m0, t0 = stats(wl_t)
print(f"as-built wl[t]*rets[t]:        {m0:+.3f}%/mo  t={t0:+.2f}")

# transition-bar decomposition: as-built = lag1 + (wl[t]-wl[t-1])*rets[t]
wl_l1 = wl_of(np.roll(lane_of_bar, 1)); wl_l1[0] = 0.0
m1, t1 = stats(wl_l1)
delta_wl = wl_t - wl_l1
trans_term = (delta_wl * rets.to_numpy()).sum(axis=1)
n_trans = int((delta_wl.sum(axis=1) != 0).sum())  # bars where allocation changed
print(f"lag-1   wl[t-1]*rets[t]:       {m1:+.3f}%/mo  t={t1:+.2f}")
print(f"transition bars: {n_trans} ({n_trans/len(lane_of_bar)*100:.2f}%)")
print(f"transition term arith total: {trans_term.sum()*100:+.1f}% over span = {trans_term.sum()*100/65:+.2f} pts/mo (the lookahead rent)")

# direction test: flip-to-bear bars' bench return vs all bars
bench_ret = bench["close"].pct_change().fillna(0.0)
flip_bear = (lane_of_bar == 0) & (np.roll(lane_of_bar, 1) != 0)
flip_exp = (lane_of_bar == 3) & (np.roll(lane_of_bar, 1) != 3)
print(f"P(bench ret<0 | flip->bear bar): {bench_ret[flip_bear].lt(0).mean():.3f}  (uncond {bench_ret.lt(0).mean():.3f}), n={flip_bear.sum()}")
print(f"P(bench ret>0 | flip->exp bar): {bench_ret[flip_exp].gt(0).mean():.3f}  (uncond {bench_ret.gt(0).mean():.3f}), n={flip_exp.sum()}")
print(f"mean bench ret on flip->bear bars: {bench_ret[flip_bear].mean()*100:+.3f}%  vs uncond {bench_ret.mean()*100:+.4f}%")
print(f"mean bench ret on flip->exp bars : {bench_ret[flip_exp].mean()*100:+.3f}%  vs uncond {bench_ret.mean()*100:+.4f}%")
# and the NEXT bar after flips (what the honest version gets):
print(f"mean bench ret 1 bar AFTER flip->bear: {bench_ret[flip_bear].shift(-1).mean()*100:+.3f}%")
print(f"mean bench ret 1 bar AFTER flip->exp : {bench_ret[flip_exp].shift(-1).mean()*100:+.3f}%")

# perfect-foresight bound (roll -1): upper sensitivity bound
wl_f = wl_of(np.roll(lane_of_bar, -1)); wl_f[-1] = 0.0
mf, tf = stats(wl_f, pos_mat=np.roll(POS.to_numpy(), -1, axis=0))
print(f"foresight wl[t+1]*rets[t]:     {mf:+.3f}%/mo  t={tf:+.2f}  (upper sensitivity bound)")

# no-netted-fee variant (per-specialist fees only, i.e. curves as-is, blend free)
pr_nonet = (wl_t * rets.to_numpy()).sum(axis=1)
pe_nonet = pd.Series(np.cumprod(1 + pr_nonet), index=eq.index)
exc_nonet = []
for s, e in months:
    m = pe_nonet[(pe_nonet.index >= s) & (pe_nonet.index < e)]
    b = bench["close"][(bench.index >= s) & (bench.index < e)]
    exc_nonet.append((m.iloc[-1]/m.iloc[0]-1)*100 - (b.iloc[-1]/b.iloc[0]-1)*100)
exc_nonet = np.array(exc_nonet)
print(f"as-built WITHOUT netted fee:   {exc_nonet.mean():+.3f}%/mo (netted fee drag {m0-exc_nonet.mean():+.2f} pts/mo)")

# continuous DD episodes (top 5) on as-built curve
w_ret = (wl_t * rets.to_numpy()).sum(axis=1)
ne = (wl_t * POS.to_numpy()).sum(axis=1)
pr = w_ret - FEE * np.abs(np.diff(ne, prepend=0.0))
pe = pd.Series(np.cumprod(1 + pr), index=eq.index)
peak = pe.cummax()
dd = (pe/peak - 1)
print("\ntop-5 continuous DD episodes (as-built, pre-funding):")
episodes = []
in_ep = False
for ts, v in dd.items():
    if v < -0.03 and not in_ep:
        in_ep, trough_v, trough_ts, start_ts = True, v, ts, ts
    elif in_ep:
        if v < trough_v: trough_v, trough_ts = v, ts
        if v >= -1e-12:
            in_ep = False
            episodes.append((trough_v, start_ts, trough_ts, ts))
if in_ep: episodes.append((trough_v, start_ts, trough_ts, dd.index[-1]))
for v, s0, t0_, e0 in sorted(episodes)[:5]:
    print(f"  {v*100:6.2f}%  start {s0.date()}  trough {t0_.date()}  recovered {e0.date() if e0!=dd.index[-1] else 'NOT YET'}")

# holdout with FULL bench (to 2026-09-28) — does the fixed blend clear Aug/Sep?
bf = bench_full["close"]
def wstats(pe, s, e):
    m = pe[(pe.index >= s) & (pe.index < e)]
    b = bf[(bf.index >= s) & (bf.index < e)]
    if len(m) < 2 or len(b) < 2: return None
    return {"strat": round((m.iloc[-1]/m.iloc[0]-1)*100, 2), "bench": round((b.iloc[-1]/b.iloc[0]-1)*100, 2),
            "excess": round((m.iloc[-1]/m.iloc[0]-b.iloc[-1]/b.iloc[0])*100, 2)}
print("\nmonthly results as-built, 2026-05..2026-09 (bench full):")
for s in pd.date_range("2026-05-01", "2026-09-01", freq="MS", tz="UTC"):
    e = s + pd.DateOffset(months=1)
    r = wstats(pe, s, min(e, bf.index[-1] + pd.Timedelta(minutes=15)))
    print(f"  {s.date()}: {r}")

# selection bias: trial score distribution
import glob
tr = sorted(glob.glob(os.path.join(REPO, "tuner/runs/blender_v21g*_trials.json")))
print("\ntrials files:", tr)
if tr:
    tl = json.load(open(tr[0]))
    sc = np.array([t["score"] for t in tl if not t.get("vetoed")])
    print(f"n trials={len(tl)} non-vetoed={len(sc)} max={sc.max():.2f} p50={np.percentile(sc,50):.2f} "
          f"p90={np.percentile(sc,90):.2f} p99={np.percentile(sc,99):.2f} "
          f"share>7.33 (champ mean_exc): {(sc>7.33).mean()*100:.1f}%  share>0: {(sc>0).mean()*100:.1f}%")
    # per-trial excesses of top trials: distribution of mean excess
    me = [np.mean(t["excesses"]) for t in tl if t.get("excesses")]
    me = np.array(me)
    print(f"trial mean-excess: max={me.max():.2f} p90={np.percentile(me,90):.2f} p99={np.percentile(me,99):.2f} share>7.33: {(me>7.33).mean()*100:.1f}%")
