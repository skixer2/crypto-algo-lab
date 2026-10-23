#!/usr/bin/env python3
"""alpha_076c pre-registered pilot — calibration stage (cross-check anchors).

Reproduces, BEFORE the battery:
  (1) stored A production curve netting: fee-free +2.89 -> netted +2.47 / +2.06 w/ funding
  (2) bar-arithmetic A static (compose_portfolio law): target +2.06 t1.35 DD-50.4
  (3) bar-arithmetic 076c entry-gated machine: target +3.16 t1.53 worst-40.5 DD-43.4
Convention search spaces (disclosed): fund gate series (engine vs lab 90-settle),
BTC momentum lag (shift 0 vs 1 at decision time).
"""
import os, sys, json
import numpy as np
import pandas as pd

REPO = "/home/node/.openclaw/workspace/crypto"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl")

from tools.stats_canonical import grade, load_bench, load_curve
from tuner.alpha_orchestrator import _fund_pct_for
from tuner.alpha_orchestrator import build_fund_pct

DATA = os.path.join(REPO, "framework", "data_cache")
EX = os.path.join(DATA, "okx_ETH_USDT_15m_20210101_20260928.csv")
BTC15 = os.path.join(DATA, "okx_BTC_USDT_15m_20210101_20260928.csv")
FUND_CSVS = {
    "bin": os.path.join(DATA, "binance_ETHUSDT_funding_proxy_202101_202610.csv"),
    "byb": os.path.join(DATA, "bybit_ETHUSDT_funding_202101_202610.csv"),
}
SEAL = pd.Timestamp("2026-07-28", tz="UTC")
FEE = 0.0008


def to_ns(s):
    try:
        a = pd.to_datetime(s, utc=True)
    except ValueError:
        a = pd.to_datetime(s, utc=True, format="mixed")
    return a.astype("datetime64[ns, UTC]")


def load_exec():
    df = pd.read_csv(EX)
    df["timestamp"] = to_ns(df["timestamp"])
    df = df[(df.timestamp >= pd.Timestamp("2021-01-01", tz="UTC")) & (df.timestamp <= SEAL)].reset_index(drop=True)
    df.index = df["timestamp"]
    return df


def load_funding_avg():
    """lab.py convention: avg(binance,bybit) per-8h-settlement rates."""
    def rd(p, tcol, rcol):
        d = pd.read_csv(p)
        t = to_ns(d[tcol])
        return pd.DataFrame({"bucket": t.dt.floor("8h"), "rate": d[rcol].astype(float)})
    a, b = rd(FUND_CSVS["bin"], "ts", "rate"), rd(FUND_CSVS["byb"], "ts", "fundingRate")
    m = a.merge(b, on="bucket", suffixes=("_bin", "_byb"), how="outer")
    m["rate"] = m[["rate_bin", "rate_byb"]].mean(axis=1, skipna=True)
    return m.sort_values("bucket").reset_index(drop=True)


def fund_to_bars(exec_df, fund):
    bar_close = (exec_df["timestamp"] + pd.Timedelta("15min")).astype("int64").values
    fb = fund["bucket"].astype("int64").values
    idx = np.searchsorted(fb, bar_close, side="right") - 1
    ok = idx >= 0
    idxc = np.clip(idx, 0, len(fund) - 1)
    v = fund["rate"].values[idxc].astype(float)
    v[~ok] = np.nan
    return v


def latch(x, entry_mask=None, N=192, buf=1.0):
    """alpha_076a state machine (bar arithmetic): ev[exit]=0, ev[entry]=1, ffill->0."""
    c, h, l = x["close"], x["high"], x["low"]
    th = h.rolling(N, min_periods=N // 2).max().shift(1)
    tl = l.rolling(N, min_periods=N // 2).min().shift(1)
    prev = c.shift(1)
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(96, min_periods=32).mean()
    above = (c > th)
    if entry_mask is not None:
        above = above & entry_mask
    below = (c < tl - buf * atr)
    ev = pd.Series(np.nan, index=c.index)
    ev[below] = 0.0
    ev[above] = 1.0
    return ev.ffill().fillna(0.0)


def sim_curve(x, pos, fund_rate_bar):
    """compose_portfolio substrate: decision@close t -> eff t+1; fee |dEff|;
    funding -rate*eff at 00/08/16 bars. Long pays positive funding."""
    c = x["close"]
    eff = pos.shift(1).fillna(0.0)
    ret1 = c.pct_change().fillna(0.0)
    gross = eff * ret1
    fee = FEE * eff.diff().abs().fillna(0.0)
    is_settle = (x["timestamp"].dt.hour % 8 == 0) & (x["timestamp"].dt.minute == 0)
    fr = pd.Series(np.where(is_settle, np.nan_to_num(fund_rate_bar), 0.0), index=c.index)
    fc = fr * eff
    net = gross - fee - fc
    return pd.Series(np.cumprod(1.0 + net.values), index=c.index, name="equity")


def bench_close():
    b = load_bench(EX)
    return b[b.index <= SEAL].sort_index()


def btc_mom_series(x, days):
    btc = pd.read_csv(BTC15, usecols=["timestamp", "close"])
    btc["timestamp"] = to_ns(btc["timestamp"])
    btc = btc.set_index("timestamp")["close"].sort_index()
    btc = btc.reindex(x.index).ffill()
    return btc / btc.shift(int(round(96 * days)))


def netting_on_curve(eq_free, pos, fr_bar, x_index, fee=True, fund=True):
    """netting layer on an ENGINE curve (decomp/overlays convention)."""
    ret = eq_free.pct_change().fillna(0.0)
    net = ret.copy()
    if fee:
        net = net - FEE * pos.diff().abs().fillna(0.0)
    if fund:
        is_settle = (x_index.hour % 8 == 0) & (x_index.minute == 0)
        fr = pd.Series(np.where(is_settle, np.nan_to_num(fr_bar), 0.0), index=x_index)
        net = net - fr * pos
    return pd.Series(np.cumprod(1.0 + net.values), index=x_index) * eq_free.iloc[0]


def main():
    x = load_exec()
    b = bench_close()
    out = {}

    # (1) stored A curve netting check
    eq_a, pos_a = load_curve(os.path.join(REPO, "data/precompute/alpha_076a.csv.gz"))
    eq_a = eq_a[eq_a.index <= SEAL]
    pos_a = pos_a.reindex(eq_a.index).fillna(0.0)
    fr_bar = fund_to_bars(x, load_funding_avg())
    out["A_stored_feefree"] = grade(eq_a, b, "A_stored_ff", pos=pos_a)
    out["A_stored_netted"] = grade(netting_on_curve(eq_a, pos_a, fr_bar, eq_a.index, fund=False), b, "A_stored_netted", pos=pos_a)
    out["A_stored_netfund"] = grade(netting_on_curve(eq_a, pos_a, fr_bar, eq_a.index), b, "A_stored_netfund", pos=pos_a)

    # (2) bar-arithmetic A static — engine-convention fund gate
    fund_eng = _fund_pct_for(EX, "binance").reindex(x.index)
    mask_eng = (fund_eng < 0.7).fillna(False)
    posA = latch(x, entry_mask=mask_eng)
    eqA = sim_curve(x, posA, fr_bar)
    out["BA_A_static_engfund"] = grade(eqA, b, "BA_A_static", pos=posA)

    # also: no funding gate at all (raw turtle) for reference
    posA_raw = latch(x)
    out["BA_A_raw_turtle"] = grade(sim_curve(x, posA_raw, fr_bar), b, "BA_A_raw", pos=posA_raw)

    # (3) bar-arithmetic 076c — BTC lag convention search
    for lag in (0, 1):
        mom = btc_mom_series(x, 30)
        if lag:
            mom = mom.shift(1)
        gate = (mom > 1.00).fillna(False)
        posC = latch(x, entry_mask=(mask_eng & gate))
        eqC = sim_curve(x, posC, fr_bar)
        out[f"BA_076c_lag{lag}"] = grade(eqC, b, f"BA_076c_lag{lag}", pos=posC)

    print(json.dumps(out, indent=1, default=str))
    json.dump(out, open("/tmp/pilot076c_calibration.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
