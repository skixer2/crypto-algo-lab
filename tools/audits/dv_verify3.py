#!/usr/bin/env python3
"""Part 3: where exactly does the transition rent sit? Per-flip decomposition."""
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
                    parse_dates=["timestamp"], index_col="timestamp").sort_index().loc[eq.index[0]:eq.index[-1]]

z = np.load(os.path.join(PRE, "regime_grid.npz"))
gidx = pd.DatetimeIndex(z["index"].astype("int64"))
pos_in_full = gidx.asi8.searchsorted(pd.DatetimeIndex(eq.index).asi8)
lane_of_bar = z["lanes"][:, pos_in_full][DET]

nsp = len(names)
W = np.zeros((4, nsp))
for ln in V21G["weights"]:
    for a, w in V21G["weights"][ln].items():
        W[LANES.index(ln)][names.index(a)] = w
ls = W.sum(axis=1); Wr = W / np.where(ls[:, None] > 1.0, ls[:, None], 1.0)

def wl_of(la):
    wl = np.zeros((len(la), nsp))
    for li in range(4): wl[la == li] = Wr[li]
    return wl

wl_t = wl_of(lane_of_bar)
wl_l1 = wl_of(np.roll(lane_of_bar, 1)); wl_l1[0] = 0.0
R = rets.to_numpy()
dW = wl_t - wl_l1
trans = (dW * R).sum(axis=1)

flip = lane_of_bar != np.roll(lane_of_bar, 1); flip[0] = False
print("flip bars:", flip.sum(), "| sum trans term: ", f"{trans.sum()*100:+.1f}%")
print("gross arith as-built:", f"{(wl_t*R).sum()*100:+.1f}%", "| lag1:", f"{(wl_l1*R).sum()*100:+.1f}%")

# per (old->new) lane pair
br = bench["close"].pct_change().fillna(0.0)
print("\nper (old->new): n | trans-term sum | mean bench ret on those bars")
for o in range(4):
    for n_ in range(4):
        if o == n_: continue
        m = flip & (np.roll(lane_of_bar, 1) == o) & (lane_of_bar == n_)
        if m.sum() == 0: continue
        print(f"  {LANES[o]:>17} -> {LANES[n_]:<16} n={m.sum():5d}  trans {(trans[m].sum()*100):+8.1f}%  bench {br[m].mean()*100:+.3f}%/bar  contrib/flip {(trans[m].sum()/m.sum()*100):+.3f}%")

# top 25 flip bars by contribution
idx = eq.index
df = pd.DataFrame({"trans": trans, "old": np.where(flip, np.roll(lane_of_bar,1), -1),
                   "new": np.where(flip, lane_of_bar, -1), "bench": br},
                  index=idx)
top = df[flip].reindex(df["trans"].abs().sort_values(ascending=False).index)[:25]
print("\ntop-25 flip bars by |contribution|:")
for ts, r in top.iterrows():
    print(f"  {ts.date()} {ts.time()}  {LANES[int(r['old'])]:>17}->{LANES[int(r['new'])]:<16} contrib {r['trans']*100:+8.2f}%  bench {r['bench']*100:+.2f}%")
print("\nshare of total |trans| in top-25:", f"{top['trans'].abs().sum()/np.abs(trans).sum()*100:.1f}%",
      "| in top-100:", f"{np.sort(np.abs(trans[flip]))[-100:].sum()/np.abs(trans).sum()*100:.1f}%")

# what if we lag by ONE bar but keep specialists' own same-bar fill (i.e. the engine-consistent fix)? already done: -5.29
# what if the ENTIRE system (specialists included) were lagged one bar (proxy: rets shifted +1)?
R_lag = np.roll(R, 1, axis=0); R_lag[0] = 0.0
POSl = np.roll(POS.to_numpy(), 1, axis=0)
wl_all_lag = wl_of(lane_of_bar)  # lane as-of t decides; specialists one bar late
w_ret = (wl_all_lag * R_lag).sum(axis=1)
ne = (wl_all_lag * POSl).sum(axis=1)
pr = w_ret - FEE * np.abs(np.diff(ne, prepend=0.0))
pe = pd.Series(np.cumprod(1 + pr), index=eq.index)
starts = pd.date_range("2021-04-01", "2026-06-01", freq="MS", tz="UTC")
exc = []
for s in starts:
    e = s + pd.DateOffset(months=1)
    m = pe[(pe.index >= s) & (pe.index < e)]
    b = bench["close"][(bench.index >= s) & (bench.index < e)]
    exc.append((m.iloc[-1]/m.iloc[0]-1)*100 - (b.iloc[-1]/b.iloc[0]-1)*100)
exc = np.array(exc)
print(f"\neverything-lagged-1-bar variant (lane as-is, rets+pos shifted): {exc.mean():+.3f}%/mo  t={exc.mean()/(exc.std(ddof=1)/np.sqrt(len(exc))):+.2f}")
