#!/usr/bin/env python3
"""Engine validation for bull r3: reality ratios through the REAL engines.

Route 1 (mandated): tuner.alpha_orchestrator.run_backtest, ctx fast path,
formula = reports/bull_mining_r3/formulas/bullr3_latch192.py (ungated latch core).
Route 2 (full recruit config, funding gate included): framework.runner.run_strategy
with a gate-carrying model implementing the Module-3 contract. Engine imported,
never copied.
"""
import os, sys, json
import numpy as np
import pandas as pd

REPO = "/home/node/.openclaw/workspace/crypto"
sys.path.insert(0, REPO)
sys.path.insert(0, "/tmp/bull_r3")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl")

from lab import load_exec, turtle_latch, fund_to_bars, load_funding, sim_curve, bench_close, FEE, EXEC_CSV, SEAL
from tools.stats_canonical import grade

FORMULA = os.path.join(REPO, "reports/bull_mining_r3/formulas/bullr3_latch192.py")
START, END = "2021-01-01T00:00:00Z", "2026-07-28T00:00:00Z"

x = load_exec()
b = bench_close()
funds = {k: fund_to_bars(x, load_funding(k)) for k in ("bin", "avg")}
fr_avg = funds["avg"]["rate"]
fpi_bin = pd.Series(funds["bin"]["fpct"], index=x.index)


def curve_to_series(df):
    s = pd.Series(df["equity"].astype(float).values,
                  index=pd.to_datetime(df["timestamp"], utc=True))
    return s[~s.index.duplicated(keep="last")].sort_index()


# ── arithmetic references (same funding-cost overlay, avg input) ──
pos_raw = turtle_latch(x)
eq_arith_raw = sim_curve(x, pos_raw, fr_avg)
pos_g = turtle_latch(x, entry_mask=(fpi_bin < 0.7).fillna(False))
eq_arith_g = sim_curve(x, pos_g, fr_avg)

out = {}

# ── Route 1: run_backtest (real orchestrator engine, fast ctx path) ──
from tuner.alpha_orchestrator import run_backtest
from models.wq_alpha_miner import WQAlphaParams
from models.wq_alpha_fast import prepare_fast_context

params = WQAlphaParams(
    formula_path=FORMULA, long_threshold=0.5, short_threshold=0.55,
    signal_smoothing=1, atr_period=14, atr_stop_mult=50.0, atr_take_mult=50.0,
    max_position_pct=1.0, warmup_candles=100, buffer_size=1500,
    use_bias_filter=False, signal_exit_threshold=0.5,
)
ctx = prepare_fast_context(EXEC_CSV, None, FORMULA)
df = run_backtest(params, "ETH", "15m", "15m", {"15m": EXEC_CSV}, START, END,
                  ctx=ctx, allow_shorts=False, fee=FEE)
eq_eng = curve_to_series(df)
pos_eng = (df["position"] == "long").astype(float)
pos_eng.index = eq_eng.index
pos_eng = pos_eng.fillna(0.0)
pos_eng = pos_eng.reindex(x.index).fillna(0.0)

# engine funding overlay: charge settlements on engine exposure (same fn)
def add_funding(eq, pos_decision):
    eff = pos_decision.shift(1).fillna(0.0)
    is_settle = (eq.index.hour % 8 == 0) & (eq.index.minute == 0)
    frv = pd.Series(fr_avg, index=x.index).reindex(eq.index).fillna(0.0).values
    r = pd.Series(np.where(is_settle, frv, 0.0), index=eq.index)
    net_bar = -r * eff
    return eq * pd.Series(np.cumprod(1.0 + net_bar.values), index=eq.index)

eq_eng_net = add_funding(eq_eng, pos_eng)
g_eng = grade(eq_eng_net, b, name="engine_raw192_run_backtest_net")
g_ar = grade(eq_arith_raw, b, name="arith_raw192_net")
out["route1_raw192"] = {
    "engine": g_eng, "arithmetic": g_ar,
    "reality_ratio": round(g_eng["mean_excess_pct_mo"] / g_ar["mean_excess_pct_mo"], 3),
    "position_corr": round(float(np.corrcoef(pos_eng.values, pos_raw.values)[0, 1]), 4),
    "pos_match_pct": round(float((pos_eng.values == pos_raw.values).mean()) * 100, 2),
}

# ── Route 2: framework.runner with gate-carrying model (full recruit) ──
class GatedLatchModel:
    """Module-3 contract model: turtle192 + binance-fpct gate, decisions precomputed
    by the SAME arithmetic construction as the substrate (lab.turtle_latch)."""
    def __init__(self, exec_slice, decisions, atr_period=14, sl_mult=50.0):
        self.x = exec_slice
        self.dec = decisions.values
        self.i = -1
        c, h, l = exec_slice["close"], exec_slice["high"], exec_slice["low"]
        prev = c.shift(1)
        tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
        self.atr = tr.ewm(alpha=1.0 / atr_period, adjust=False).mean().bfill().values
        self.sl_mult = sl_mult

    def update(self, candle_row, tf):
        self.i += 1

    def predict(self, allow_shorts=True):
        i = self.i
        if i < 100 or i >= len(self.dec):
            return "flat", 0.0, {}
        c = float(self.x["close"].iat[i])
        if self.dec[i] > 0:
            sl = max(c - self.sl_mult * float(self.atr[i]), 1e-9)
            return "long", 1.0, {"stop_loss": sl, "take_profit": c * 51.0}
        return "flat", 0.0, {}

    def manage_position(self, position, price, ts):
        i = self.i
        if i >= 0 and i < len(self.dec) and self.dec[i] <= 0:
            return "turtle_exit"
        return None

    def get_indicators(self):
        return {}

from framework.runner import RunConfig, run_strategy
# engine's own data selection: >= padded_start, <= end
padded = pd.Timestamp(START) - pd.Timedelta(days=3)
xs = x[(x["timestamp"] >= padded) & (x["timestamp"] <= pd.Timestamp(END))].copy()
dec = turtle_latch(xs, entry_mask=(fpi_bin.reindex(xs.index) < 0.7).fillna(False))
model = GatedLatchModel(xs, dec)
cfg = RunConfig(
    data_files={"15m": EXEC_CSV}, execution_tf="15m", model=model,
    initial_capital=10_000.0, fee=FEE, exchange="simulation", allow_shorts=False,
    data_start=padded.isoformat(), data_end=END,
)
res = run_strategy(cfg)
assert res.success and res.equity_curve is not None
dfg = res.equity_curve.equity_curve
eq_eng_g = curve_to_series(dfg)
pos_eng_g = (dfg["position"] == "long").astype(float)
pos_eng_g.index = eq_eng_g.index
pos_eng_g = pos_eng_g.fillna(0.0).reindex(x.index).fillna(0.0)
eq_eng_g_net = add_funding(eq_eng_g, pos_eng_g)
g_eng_g = grade(eq_eng_g_net, b, name="engine_gated_run_strategy_net")
g_ar_g = grade(eq_arith_g, b, name="arith_gated_net")
out["route2_gated"] = {
    "engine": g_eng_g, "arithmetic": g_ar_g,
    "reality_ratio": round(g_eng_g["mean_excess_pct_mo"] / g_ar_g["mean_excess_pct_mo"], 3),
    "position_corr": round(float(np.corrcoef(pos_eng_g.values, pos_g.values)[0, 1]), 4),
    "pos_match_pct": round(float((pos_eng_g.values == pos_g.reindex(x.index).fillna(0.0).values).mean()) * 100, 2),
    "trades": int(res.metadata.get("total_trades", 0)) if isinstance(res.metadata, dict) else 0,
}

print(json.dumps(out, indent=1, default=str))
json.dump(out, open("/tmp/bull_r3/out/engine_validation.json", "w"), indent=1, default=str)
for k, tag in (("route1_raw192", "raw192"), ("route2_gated", "gated")):
    pd.DataFrame({"timestamp": eq_eng.index if k == "route1_raw192" else eq_eng_g.index,
                  "equity": (eq_eng_net if k == "route1_raw192" else eq_eng_g_net).values}).to_pickle(
        f"/home/node/.openclaw/workspace/crypto/reports/bull_mining_r3/curves/engine_{tag}_net.pkl")
