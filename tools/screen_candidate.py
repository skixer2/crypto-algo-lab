#!/usr/bin/env python3
"""Canonical candidate screen — the ONLY numbers a proposing agent may quote.

Usage: MPLCONFIGDIR=/tmp/ml python3 tools/screen_candidate.py <formula.py>

Grades one alpha formula through the engine convention (decide@close,
fill@next-bar, netted fees 0.0008 on |dpos|, long-only clip, buy-hold bench)
via tools/stats_canonical. Floors: mean>0, worst_abs>=-40, both halves>=0,
2024+ subwindow mean>0. Prints PASS/FAIL per floor. No tuning, no variants.
"""
import sys, os, warnings, importlib
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from tuner.alpha_orchestrator import build_fund_pct
from tools.stats_canonical import grade, load_bench

CACHE = 'framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv'


def main():
    fpath = sys.argv[1]
    name = os.path.basename(fpath)[:-3]
    mod = importlib.import_module(f'models.alpha_formulas.{name}')

    c = pd.read_csv(CACHE)
    c.columns = [x.lower() for x in c.columns]
    c['timestamp'] = pd.to_datetime(c['timestamp'], utc=True)
    c = c.set_index('timestamp')
    c['fund_pct'] = build_fund_pct(
        c.reset_index()[['timestamp', 'open', 'high', 'low', 'close']].set_index('timestamp'),
        'binance', 'ETH/USDT')
    bench = load_bench(CACHE)
    ret = c['close'].pct_change().fillna(0)

    sig = mod.calculate_math_signal(c.copy())
    pos = sig.shift(1).fillna(0.0).clip(0, 1)
    eq = (1 + pos * ret - pos.diff().abs() * 0.0008).cumprod()
    eq_s = pd.Series(eq.values, index=c.index)
    r = grade(eq_s, bench, name=name, trap_asserts=False)

    mid = len(eq_s) // 2
    halves = (eq_s.iloc[:mid].pct_change().sum() * 100, eq_s.iloc[mid:].pct_change().sum() * 100)

    recent = c.index >= '2024-01-01'
    er = eq_s[recent]; er = er / er.iloc[0]
    mret = er.groupby(er.index.to_period('M')).last() / er.groupby(er.index.to_period('M')).first() - 1
    br = bench[recent]; br = br / br.iloc[0]
    bret = br.groupby(br.index.to_period('M')).last() / br.groupby(br.index.to_period('M')).first() - 1
    exc_recent = (mret - bret).mean() * 100

    print(f"SCREEN {name} (stats_canonical, engine convention)")
    print(f"  mean_excess {r['mean_excess_pct_mo']:+.2f}%/mo | t {r['t']:+.2f} | "
          f"DD {r['continuous_dd_pct']:.1f}% | worst_abs_month {r['worst_absolute_month_pct']:+.1f}%")
    print(f"  halves {halves[0]:+.1f}/{halves[1]:+.1f} | 2024+ mean excess {exc_recent:+.2f}%/mo")
    checks = [
        ('mean>0', r['mean_excess_pct_mo'] > 0),
        ('worst>=-40', r['worst_absolute_month_pct'] >= -40),
        ('halves>=0', halves[0] >= 0 and halves[1] >= 0),
        ('2024+>0', exc_recent > 0),
    ]
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    print("VERDICT:", "PASS" if all(ok for _, ok in checks) else "FAIL")


if __name__ == '__main__':
    main()
