# Bull mining round 2 — honest-lab harness
# Laws (2026-10-18 honest engine): decisions at bar close, fills at NEXT bar open;
# normal SL/TP close-evaluated; catastrophic intrabar stop at 2x stop distance, gap-aware;
# bias-TF candles only after completion. This file SUBCLASSES/copies the engine logic with a
# fill_lag guard knob (default 1 = honest; 0/2 only for flip-rent analysis). Validated against
# framework/simulation.py to 1e-9 before use. framework/ is NEVER modified.
import os, sys, json
import numpy as np
import pandas as pd

REPO = "/home/node/.openclaw/workspace/crypto"
DATA = os.path.join(REPO, "framework", "data_cache")
SEAL = pd.Timestamp("2026-07-28", tz="UTC")
FEE = 0.0008
OUT = os.path.dirname(os.path.abspath(__file__))

EXEC_CSV = os.path.join(DATA, "okx_ETH_USDT_15m_20210101_20260928.csv")
H1_CSV = os.path.join(DATA, "okx_ETH_USDT_1h_20210101_20260928.csv")
FUND_BIN = os.path.join(DATA, "binance_ETHUSDT_funding_proxy_202101_202610.csv")
FUND_BYB = os.path.join(DATA, "bybit_ETHUSDT_funding_202101_202610.csv")

DATA_START = pd.Timestamp("2021-01-01", tz="UTC")   # warmup feed
GRID_START = pd.Timestamp(pd.Timestamp("2021-04-01", tz="UTC").to_datetime64().astype("datetime64[ns]")).tz_localize("UTC")   # first graded month (ns)
GRID_END_EX = pd.Timestamp(pd.Timestamp("2026-07-01", tz="UTC").to_datetime64().astype("datetime64[ns]")).tz_localize("UTC")  # months 2021-04..2026-06 = 63


def to_ns(s):
    """Force tz-aware datetime64[ns, UTC] (pandas 2.x parses these CSVs as us)."""
    try:
        a = pd.to_datetime(s, utc=True)
    except ValueError:
        a = pd.to_datetime(s, utc=True, format="mixed")
    return a.astype("datetime64[ns, UTC]")


def load_exec():
    df = pd.read_csv(EXEC_CSV)
    df["timestamp"] = to_ns(df["timestamp"])
    df = df[(df.timestamp >= DATA_START) & (df.timestamp <= SEAL)].reset_index(drop=True)
    return df


def load_1h():
    df = pd.read_csv(H1_CSV)
    df["timestamp"] = to_ns(df["timestamp"])
    df = df[(df.timestamp >= DATA_START) & (df.timestamp <= SEAL)].reset_index(drop=True)
    return df


def load_funding_avg():
    """Averaged input: mean of Binance-proxy + Bybit per 8h settlement bucket (causal use only)."""
    def rd(p):
        d = pd.read_csv(p)
        tcol = "ts" if "ts" in d.columns else d.columns[0]
        rcol = "rate" if "rate" in d.columns else "fundingRate"
        t = to_ns(d[tcol])
        return pd.DataFrame({"bucket": t.dt.floor("8h"), "rate": d[rcol].astype(float)})
    a, b = rd(FUND_BIN), rd(FUND_BYB)
    m = a.merge(b, on="bucket", suffixes=("_bin", "_byb"), how="outer")
    m["rate"] = m[["rate_bin", "rate_byb"]].mean(axis=1, skipna=True)
    m = m.sort_values("bucket").reset_index(drop=True)
    # causal 30d rolling percentile (90 settlements; window strictly BEFORE current, no bfill)
    r = m["rate"].values
    n = len(r)
    pctl = np.full(n, np.nan)
    W = 90
    for i in range(W, n):
        w = r[i - W:i]
        pctl[i] = (w <= r[i]).mean()
    m["fpct"] = pctl
    return m


def align_funding_to_bars(exec_df, fund):
    """Per exec bar: latest SETTLED funding value + fpct (settlement ts <= bar close ts)."""
    bar_close = (exec_df["timestamp"] + pd.Timedelta("15min")).astype("int64").values
    fb = fund["bucket"].astype("int64").values
    idx = np.searchsorted(fb, bar_close, side="right") - 1
    idx = np.clip(idx, 0, len(fund) - 1)
    cols = {}
    for c in ("rate", "fpct"):
        v = fund[c].values[idx]
        v[idx < 0] = np.nan
        cols[c] = v
    # fpct k settlements back (for gradient), aligned to bars
    for k in (9, 21):
        pk = np.full(len(fund), np.nan)
        pk[k:] = fund["fpct"].values[:-k]
        v = pk[idx]
        v[idx < k] = np.nan
        cols[f"fpct_lag{k}"] = v
    return cols


def wilder_atr(h, l, c, n):
    tr = np.maximum(h, np.roll(c, 1)) - np.minimum(l, np.roll(c, 1))
    tr[0] = h[0] - l[0]
    s = pd.Series(tr).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean().values
    return s


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False, min_periods=n).mean().values


def rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.maximum(d, 0.0)).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    dn = pd.Series(np.maximum(-d, 0.0)).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0.0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0).values


# ── Models (predict only when flat; manage_position for exits) ──────────────
class Model:
    def __init__(self, x, fund_cols=None):
        self.x = x  # exec arrays dict
        self.ts2i = {t: i for i, t in enumerate(x["ts"])}
        self.fund = fund_cols or {}
        self.i = -1
    def update(self, row, tf):
        self.i += 1  # exec bars arrive in order, one per tick
    def get_indicators(self):
        return {}


class TurtleLatch(Model):
    """entry: close > trailing N-high ; exit: close < trailing N-low - buf*ATR.
    Optional funding gate/gradient on entries (gate on fpct, gradient fpct>fpct_lagK)."""
    def __init__(self, x, N=192, atr_n=96, buf=1.0, size_fn=None, gate=None, grad_k=None, fund_cols=None, sl_atr=4.0):
        super().__init__(x, fund_cols)
        h, l, c = x["high"], x["low"], x["close"]
        self.rh = pd.Series(h).rolling(N).max().shift(1).values
        self.rl = pd.Series(l).rolling(N).min().shift(1).values
        self.atr = wilder_atr(h, l, c, atr_n)
        self.N, self.buf, self.gate, self.grad_k = N, buf, gate, grad_k
        self.size_fn, self.sl_atr = size_fn, sl_atr
    def _gate_ok(self, i):
        if self.gate is not None:
            g = self.fund["fpct"][i]
            if not np.isfinite(g) or g >= self.gate:
                return False
        if self.grad_k is not None:
            a, b = self.fund["fpct"][i], self.fund[f"fpct_lag{self.grad_k}"][i]
            if not (np.isfinite(a) and np.isfinite(b) and a > b):
                return False
        return True
    def predict(self, allow_shorts=True):
        i, c = self.i, self.x["close"][self.i]
        if not np.isfinite(self.rh[i]) or not np.isfinite(self.atr[i]):
            return "flat", 0.0, {}
        if c > self.rh[i] and self._gate_ok(i):
            size = self.size_fn(i) if self.size_fn else 1.0
            sl = c - self.sl_atr * self.atr[i]
            return "long", float(size), {"stop_loss": sl, "take_profit": c * 10.0}
        return "flat", 0.0, {}
    def manage_position(self, direction, price, ts):
        i = self.i
        if np.isfinite(self.rl[i]) and np.isfinite(self.atr[i]):
            if price < self.rl[i] - self.buf * self.atr[i]:
                return "turtle_exit"
        return None


class PullbackTrend(Model):
    """1h trend on (EMA50>EMA200 and close>EMA200, merged causally) + 15m RSI dip-recovery entry.
    Exit: close < exit_ema (15m)."""
    def __init__(self, x, x1h, theta=35.0, exit_ema_n=200, rsi_n=14, atr_n=96, sl_atr=4.0):
        super().__init__(x)
        c = x["close"]
        # 1h indicators, valid AFTER the 1h bar closes -> shift 1, merge onto bar-close times
        c1 = x1h["close"].values
        e50, e200 = ema(c1, 50), ema(c1, 200)
        trend1h = (e50 > e200) & (c1 > e200)
        trend_s = pd.Series(trend1h).shift(1)  # bar h usable at close h+1h
        bclose = x["ts"].astype("int64") + 15 * 60 * 10**9
        t1 = pd.to_datetime(x1h["timestamp"], utc=True).astype("int64").values + 3600 * 10**9
        j = np.searchsorted(t1, bclose, side="right") - 1
        j = np.clip(j, 0, len(trend1h) - 1)
        self.trend = np.where(j >= 0, trend_s.fillna(False).values[j], False)
        self.rsi = rsi(c, rsi_n)
        self.eexit = ema(c, exit_ema_n)
        self.atr = wilder_atr(x["high"], x["low"], c, atr_n)
        self.theta, self.sl_atr = theta, sl_atr
    def predict(self, allow_shorts=True):
        i = self.i
        if not self.trend[i] or not np.isfinite(self.atr[i]) or not np.isfinite(self.eexit[i]):
            return "flat", 0.0, {}
        if i > 0 and self.rsi[i - 1] < self.theta <= self.rsi[i]:
            c = self.x["close"][i]
            return "long", 1.0, {"stop_loss": c - self.sl_atr * self.atr[i], "take_profit": c * 10.0}
        return "flat", 0.0, {}
    def manage_position(self, direction, price, ts):
        if np.isfinite(self.eexit[self.i]) and price < self.eexit[self.i]:
            return "ema_exit"
        return None


class VolSizeMixin:
    """Continuous vol-scaled sizing for any latch-style entry model."""
    def _size(self, i):
        s = self.sigma[i]
        if not np.isfinite(s) or s <= 0:
            return 0.0
        return float(np.clip(self.sigma_target / s, self.smin, 1.0))
    def predict(self, allow_shorts=True):
        a, sz, ind = super().predict(allow_shorts)
        if a == "long":
            sz = self._size(self.i)
            if sz <= 0:
                return "flat", 0.0, {}
            ind = dict(ind)
            ind["__size_override"] = sz
        return a, sz, ind


class VolScaledTurtle(VolSizeMixin, TurtleLatch):
    """turtle192 latch with continuous vol-scaled size: clip(sigma_target/sigma, smin, 1)."""
    def __init__(self, x, sigma_target=0.006, smin=0.25, **kw):
        super().__init__(x, **kw)
        self.sigma_target, self.smin = sigma_target, smin
        self.sigma = self.atr / x["close"]


class ConfirmedBreakout(TurtleLatch):
    """Breakout with m-bar follow-through hold: last m closes each above their own trailing N-high,
    current close above its level. Exit: turtle exit."""
    def __init__(self, x, m=4, **kw):
        super().__init__(x, **kw)
        c = x["close"]
        rh = pd.Series(x["high"]).rolling(self.N).max().shift(1)
        above = (c > rh).values
        self.hold = above.copy()
        run = 0
        for i in range(len(above)):
            run = run + 1 if above[i] else 0
            self.hold[i] = run >= m
    def predict(self, allow_shorts=True):
        i, c = self.i, self.x["close"][self.i]
        if not self.hold[i] or not np.isfinite(self.atr[i]):
            return "flat", 0.0, {}
        if self._gate_ok(i):
            return "long", 1.0, {"stop_loss": c - self.sl_atr * self.atr[i], "take_profit": c * 10.0}
        return "flat", 0.0, {}


class VolScaledCB(VolSizeMixin, ConfirmedBreakout):
    """Time-confirmed breakout entry + vol-scaled size (+ optional funding gate via kw)."""
    def __init__(self, x, sigma_target=0.005, smin=0.25, **kw):
        super().__init__(x, **kw)
        self.sigma_target, self.smin = sigma_target, smin
        self.sigma = self.atr / x["close"]


class MomentumBlend(Model):
    """Multi-horizon momentum: mean of z-scored returns over ~8h/24h/96h; enter when score>theta.
    Exit: score<0 (mode='mom') or turtle exit (mode='turtle')."""
    def __init__(self, x, theta=0.75, mode="mom", atr_n=96, N=192, buf=1.0, z_win=17280, sl_atr=4.0):
        super().__init__(x)
        c = x["close"]
        zs = []
        for h in (32, 96, 384):
            r = pd.Series(c).pct_change(h)
            z = (r - r.rolling(z_win, min_periods=h * 4).mean()) / r.rolling(z_win, min_periods=h * 4).std()
            zs.append(z)
        self.score = pd.concat(zs, axis=1).mean(axis=1).values
        self.theta, self.mode = theta, mode
        self.atr = wilder_atr(x["high"], x["low"], c, atr_n)
        self.rl = pd.Series(x["low"]).rolling(N).min().shift(1).values
        self.buf, self.sl_atr = buf, sl_atr
    def predict(self, allow_shorts=True):
        i, c = self.i, self.x["close"][self.i]
        s = self.score[i]
        if not np.isfinite(s) or not np.isfinite(self.atr[i]):
            return "flat", 0.0, {}
        if s > self.theta:
            return "long", 1.0, {"stop_loss": c - self.sl_atr * self.atr[i], "take_profit": c * 10.0}
        return "flat", 0.0, {}
    def manage_position(self, direction, price, ts):
        i = self.i
        if self.mode == "mom" and np.isfinite(self.score[i]) and self.score[i] < 0:
            return "mom_exit"
        if np.isfinite(self.rl[i]) and np.isfinite(self.atr[i]) and price < self.rl[i] - self.buf * self.atr[i]:
            return "turtle_exit"
        return None


# ── Honest engine copy (validated vs framework/simulation.py) ───────────────
class HonestEngine:
    """Copy of SimulationEngine.run loop; fill_lag=1 default == framework behavior.
    fill_lag 0/2 ONLY for flip-rent analysis."""
    def __init__(self, model, exec_df, fee=FEE, fill_lag=1, initial_capital=10_000.0, size_col=False):
        self.model, self.fee, self.fill_lag = model, fee, fill_lag
        self.ts = exec_df["timestamp"].values
        self.o = exec_df["open"].values.astype(float)
        self.h = exec_df["high"].values.astype(float)
        self.l = exec_df["low"].values.astype(float)
        self.c = exec_df["close"].values.astype(float)
        self.cap = initial_capital
        self.rec_pos = size_col
    def run(self):
        m = self.model
        cash, qty = self.cap, 0.0
        pos = None; ep = sl = tp = 0.0
        pend = None
        recs_ts, recs_eq, recs_pos, recs_qty = [], [], [], []
        n = len(self.c)
        for i in range(n):
            o, hi, lo, c = self.o[i], self.h[i], self.l[i], self.c[i]
            m.update(None, "15m")
            # step 0a: pending fills at this open
            if pend is not None:
                kind, direction, size_pct, psl, ptp, reason, fill_i = pend
                if fill_i <= i:
                    pend = None
                    if kind == "enter" and pos is None:
                        eq = cash + qty * o
                        val = eq * size_pct
                        fee_ = val * self.fee
                        pos = direction; ep = o; sl = psl; tp = ptp
                        qty = (val - fee_) / o
                        cash -= val
                    elif kind == "exit" and pos is not None:
                        eq_b = cash + qty * o
                        fee_ = abs(qty) * o * self.fee
                        cash += qty * o - fee_
                        qty = 0.0; pos = None
            # step 0b: catastrophic intrabar (2x stop distance, gap-aware)
            if pos is not None and ep:
                cat = 2.0 * sl - ep
                if pos == "long" and lo <= cat:
                    px = min(o, cat)
                    fee_ = abs(qty) * px * self.fee
                    cash += qty * px - fee_
                    qty = 0.0; pos = None
                elif pos == "short" and hi >= cat:
                    px = max(o, cat)
                    fee_ = abs(qty) * px * self.fee
                    cash -= abs(qty) * px + fee_
                    qty = 0.0; pos = None
            # step 1: close-based SL/TP + model exits
            exited = False
            if pos is not None:
                if pos == "long" and c <= sl:
                    if self.fill_lag == 0:
                        fee_ = abs(qty) * c * self.fee; cash += qty * c - fee_; qty = 0.0; pos = None
                    else:
                        pend = ("exit", None, 0.0, 0.0, 0.0, "stop_loss", i + self.fill_lag)
                    exited = True
                elif pos == "long" and c >= tp:
                    if self.fill_lag == 0:
                        fee_ = abs(qty) * c * self.fee; cash += qty * c - fee_; qty = 0.0; pos = None
                    else:
                        pend = ("exit", None, 0.0, 0.0, 0.0, "take_profit", i + self.fill_lag)
                    exited = True
                if not exited and pos is not None:
                    reason = m.manage_position(pos, c, self.ts[i])
                    if reason:
                        if self.fill_lag == 0:
                            fee_ = abs(qty) * c * self.fee; cash += qty * c - fee_; qty = 0.0; pos = None
                        else:
                            pend = ("exit", None, 0.0, 0.0, 0.0, "model_exit:" + reason, i + self.fill_lag)
                        exited = True
            # step 2: entry
            if pos is None and not exited and pend is None:
                action, size_pct, ind = m.predict()
                if action == "long":
                    size_pct = ind.get("__size_override", size_pct)
                    psl, ptp = ind.get("stop_loss", 0.0), ind.get("take_profit", 0.0)
                    if psl > 0 and ptp > 0 and size_pct > 0:
                        if self.fill_lag == 0:
                            eq = cash + qty * c
                            val = eq * size_pct
                            fee_ = val * self.fee
                            pos = "long"; ep = c; sl = psl; tp = ptp
                            qty = (val - fee_) / c
                            cash -= val
                        else:
                            pend = ("enter", "long", size_pct, psl, ptp, None, i + self.fill_lag)
            # step 3: record
            eq = cash + qty * c
            recs_ts.append(self.ts[i]); recs_eq.append(eq); recs_pos.append(pos == "long"); recs_qty.append(qty)
        cur = pd.DataFrame({"timestamp": pd.to_datetime(recs_ts, utc=True), "equity": recs_eq,
                            "in_pos": recs_pos, "qty": recs_qty, "close": self.c})
        return cur


def build_exec_and_fund():
    x = load_exec()
    fund = load_funding_avg()
    fcols = align_funding_to_bars(x, fund)
    arr = {"ts": x["timestamp"].values, "open": x["open"].values.astype(float),
           "high": x["high"].values.astype(float), "low": x["low"].values.astype(float),
           "close": x["close"].values.astype(float)}
    return x, arr, fund, fcols
