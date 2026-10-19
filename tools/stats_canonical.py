#!/usr/bin/env python3
"""stats_canonical.py — THE canonical grading implementation (2026-10-19).

Born from the round-2 quarantine: an agent's self-graded stats mixed fraction/
percent units and inflated every number 3-4x, producing a fake t=2.05 champion
that its own stored curves refuted (+0.77, t 0.33). From today:

  - Candidate GENERATION may be delegated (agents, loops, DS).
  - Candidate MEASUREMENT is centralized HERE, only.

Laws encoded:
  - 63-window grid 2021-04..2026-06 (monthly, [s, s+1mo)); July-2026 partial
    (to the 07-28 seal) disclosed as a separate field, never in the aggregate.
  - Returns are FRACTIONS internally; PERCENT appears exactly once, at the
    boundary. Sanity asserts on every aggregate (the round-2 trap guard).
  - t over window excesses (ddof=1); t=None when std==0.
  - Excess = strat window return - bench window return (both close-to-close
    on the curve's own timestamps).

Usage (library):
    from tools.stats_canonical import grade
    report = grade(eq_series, bench_close_series, name="G3_center")
Usage (CLI):
    python3 tools/stats_canonical.py --curve path.pkl --bench framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv
"""
from __future__ import annotations
import argparse, json, pickle, sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2] if Path(__file__).resolve().parents[1].name == "tools" else Path(__file__).resolve().parents[1]
GRID = [pd.Timestamp("2021-04-01", tz="UTC") + pd.DateOffset(months=k) for k in range(63)]
JULY = (pd.Timestamp("2026-07-01", tz="UTC"), pd.Timestamp("2026-07-28", tz="UTC"))


def _win_ret(series: pd.Series, s, e) -> float | None:
    w = series[(series.index >= s) & (series.index < e)]
    if len(w) < 2:
        return None
    return float(w.iloc[-1] / w.iloc[0] - 1.0)  # FRACTION


def _boundary_pct(x: float) -> float:
    """single point where fractions become percent, with the trap assert."""
    p = float(x) * 100.0
    assert -100.0 < p < 1000.0, f"implausible window value {p:.1f}% — unit mix suspected"
    return round(p, 2)


def monthly_excesses(eq: pd.Series, bench_close: pd.Series, grid=None) -> np.ndarray:
    ex = []
    for s in (grid if grid is not None else GRID):
        e = s + pd.DateOffset(months=1)
        r_s, r_b = _win_ret(eq, s, e), _win_ret(bench_close, s, e)
        if r_s is None or r_b is None:
            continue
        ex.append(r_s - r_b)
    return np.array(ex)


def continuous_dd(eq: pd.Series) -> float:
    peak = eq.cummax()
    return round(float(((eq - peak) / peak).min()) * 100.0, 1)


def grade(eq: pd.Series, bench_close: pd.Series, name: str = "", pos: pd.Series | None = None, trap_asserts: bool = True, months_mask=None) -> dict:
    """months_mask: optional list/array of month-start Timestamps (subset of GRID)
    — Exam Law v2 lane-conditional mode: earning + survival measured on these months
    only (e.g., a bull specialist's in-lane months). July stays disclosed separately."""
    global GRID
    if months_mask is not None:
        keep = set(pd.Timestamp(m, tz="UTC") if m.tzinfo is None else pd.Timestamp(m) for m in months_mask)
        grid = [s for s in GRID if s in keep]
        assert len(grid) >= 8, f"mask leaves only {len(grid)} months — lane too rare for an exam"
    else:
        grid = GRID
    """eq, bench_close: tz-aware DatetimeIndex series (equity level, price)."""
    ex = monthly_excesses(eq, bench_close, grid=grid)
    assert len(ex) >= 8, f"only {len(ex)} gradeable windows — grid/curve misaligned"
    mean_f = float(ex.mean())
    std = float(ex.std(ddof=1))
    t = (mean_f / (std / np.sqrt(len(ex)))) if std > 0 else None
    half = len(ex) // 2
    jr_s, jr_b = _win_ret(eq, *JULY), _win_ret(bench_close, *JULY)
    conc = float(ex.max() / ex.sum()) if ex.sum() > 0 else None
    out = {
        "name": name,
        "mean_excess_pct_mo": _boundary_pct(mean_f),
        "t": round(t, 2) if t is not None else None,
        "worst_window_pct": _boundary_pct(ex.min()),
        "best_window_pct": _boundary_pct(ex.max()),
        "first_half_pct": _boundary_pct(ex[:half].mean()),
        "second_half_pct": _boundary_pct(ex[half:].mean()),
        "concentration": round(conc, 2) if conc is not None else None,
        "neg_windows": int((ex < 0).sum()), "n_windows": len(ex),
        "continuous_dd_pct": continuous_dd(eq),
        "july26_partial_pct": _boundary_pct(jr_s - jr_b) if (jr_s is not None and jr_b is not None) else None,
    }
    if pos is not None:
        out["time_in_pct"] = round(float((pos.abs() > 0.05).mean()) * 100.0, 0)
    # Exam Law v2: absolute worst month (ruin floor) — strat return, not excess
    strat_rets = []
    for s in grid:
        e = s + pd.DateOffset(months=1)
        r_s = _win_ret(eq, s, e)
        if r_s is not None:
            strat_rets.append(r_s)
    if strat_rets:
        out["worst_absolute_month_pct"] = _boundary_pct(min(strat_rets))
    # trap asserts (round-2 lesson): aggregates must be plausible (synthetic
    # deterministic fixtures legitimately exceed the t-cap — they pass False)
    if trap_asserts:
        assert abs(out["mean_excess_pct_mo"]) < 100, "mean |excess| >= 100%/mo — unit bug"
        if t is not None:
            assert abs(t) < 50, "|t| >= 50 — degenerate or unit bug"
    return out


def load_curve(path: str) -> tuple[pd.Series, pd.Series | None]:
    p = Path(path)
    if p.suffix == ".pkl":
        df = pickle.load(open(p, "rb"))
        df = pd.DataFrame(df)
        df.columns = [str(c).lower() for c in df.columns]
        tcol = [c for c in df.columns if "time" in c or c == "ts" or "date" in c][0]
        df.index = pd.to_datetime(df[tcol], utc=True)
        eq = df["equity"] if "equity" in df.columns else df.iloc[:, 1]
        pos = df["position"] if "position" in df.columns else (df["in_pos"].astype(float) if "in_pos" in df.columns else None)
        return eq.astype(float), (pos.astype(float) if pos is not None else None)
    df = pd.read_csv(p, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True, format="ISO8601")
    return df["equity"].astype(float), (df["position"].astype(float) if "position" in df.columns else None)


def load_bench(path: str) -> pd.Series:
    df = pd.read_csv(path, index_col=0) if path.endswith(".csv") else None
    if "close" not in [str(c).lower() for c in df.columns]:
        df = pd.read_csv(path, index_col=0, header=None, names=["ts", "open", "high", "low", "close"], usecols=[0, 4])
    df.index = pd.to_datetime(df.index, utc=True, format="ISO8601")
    return df["close"].astype(float).sort_index()


def bench_monthly(bench_close: pd.Series) -> pd.Series:
    """Bench total return per GRID month (fraction), indexed by month start."""
    out = {}
    for s in GRID:
        e = s + pd.DateOffset(months=1)
        r = _win_ret(bench_close, s, e)
        if r is not None:
            out[s] = r
    return pd.Series(out)


def sigma_m(bench_close: pd.Series) -> float:
    """Pair's bench monthly-return volatility — the allowance floor (Law v3.2)."""
    return float(bench_monthly(bench_close).std(ddof=1))


def soft_scores(ex: np.ndarray, bm: np.ndarray, theta: float, sig_m: float,
               deep: float = -35.0, s2: float = 2.0, s3: float = 3.0) -> np.ndarray:
    """Per-month soft scores s_i (Law v3.2 anchored): allowance_i = max(theta*BMU_i, sig_m);
    1:1 within allowance, s2 beyond, s3 below `deep`; single worst month charged as if `deep`."""
    ex = np.asarray(ex, dtype=float) * 100.0 if abs(np.asarray(ex).max()) < 1.0 else np.asarray(ex, dtype=float)
    bmu = np.maximum(np.asarray(bm, dtype=float), 0.0)
    bmu = bmu * 100.0 if bmu.max() < 1.0 else bmu
    allow = np.maximum(theta * bmu, 0.5 * sig_m * 100.0 if sig_m < 1.0 else 0.5 * sig_m)
    s = ex.copy()
    m = ex < -allow
    s[m] = -allow[m] + s2 * (ex[m] + allow[m])
    d = ex <= deep
    s[d] = (-allow[d] + s2 * (deep + allow[d])) + s3 * (ex[d] - deep)
    if len(s):
        i = int(np.argmin(s))
        cap = -allow[i] + s2 * (deep + allow[i])  # charge at the deep bound (sign-corrected)
        s[i] = max(s[i], cap)
    return s


def calibrate_theta(ex_anchor: np.ndarray, bm: np.ndarray, sig_m: float, target: float = 0.3) -> float:
    """Theta by anchor inversion (Law v3.2): solve so the anchor's mean soft score = target."""
    lo, hi = 0.05, 3.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        sc = soft_scores(ex_anchor, bm, mid, sig_m).mean()
        if sc < target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 3)


def _selftest():
    idx = pd.date_range("2021-04-01", "2026-07-28", freq="15min", tz="UTC")
    bench_flat = pd.Series(100.0, index=idx)
    # 1) flat strat vs flat bench: zero everything
    r = grade(pd.Series(100.0, index=idx), bench_flat, "flat")
    assert r["mean_excess_pct_mo"] == 0.0 and r["t"] is None
    # 2) strat growing continuously at ~+1%/mo: mean ~1.00 (uniform per-bar growth,
    #    independent of window-boundary conventions — real curves have no boundary jumps)
    bars = len(idx)
    eq1 = pd.Series(100.0 * np.cumprod(1.0 + 0.01 / 2880.0 * np.ones(bars)), index=idx)
    r = grade(eq1, bench_flat, "step1pct", trap_asserts=False)
    assert abs(r["mean_excess_pct_mo"] - 1.0) < 0.05, r
    # 3) UNIT-TRAP: bench as fractions-of-level must give identical result
    eq2 = eq1.copy()
    r_a = grade(eq1 / 1000.0, bench_flat / 1000.0, "scaled", trap_asserts=False)
    assert abs(r_a["mean_excess_pct_mo"] - r["mean_excess_pct_mo"]) < 1e-6  # scale invariance
    print("SELFTEST PASS (flat / step / scale-invariance)")
    # 4) real anchor: DS round-2 stored curve must grade +0.77 t 0.33
    p = REPO / "reports/bull_mining_r2/_runs/curve_cg_n144_g0.5_s0.005.pkl"
    if p.exists():
        eq, pos = load_curve(str(p))
        bench = load_bench(str(REPO / "framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv"))
        r = grade(eq, bench, "G3_center_anchor")
        assert abs(r["mean_excess_pct_mo"] - 0.77) < 0.05 and abs(r["t"] - 0.33) < 0.05, r
        print("REAL ANCHOR PASS:", r["mean_excess_pct_mo"], "t", r["t"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--curve", required=False)
    ap.add_argument("--bench", default=str(REPO / "framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest or not args.curve:
        _selftest()
    else:
        eq, pos = load_curve(args.curve)
        print(json.dumps(grade(eq, load_bench(args.bench), name=Path(args.curve).stem, pos=pos), indent=1))
