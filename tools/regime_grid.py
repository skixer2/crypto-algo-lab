#!/usr/bin/env python3
"""Precompute a GRID of regime series for detector-search in the blender (v2.1).

JP 2026-10-13: detector quality is the critical path ("if the regime isn't
reliably detected, all the work on Alphas is worthless"). Grid over:
  donchian x confirm x vol_enter/exit x grind slope/confirm
Each combo -> lane array over the sealed span, stored once (npz + manifest).
Blender v2.1 adds one categorical dim: which regime series to route by.

Output: data/precompute/regime_grid.npz (arrays stacked) + regime_grid.json
(manifest: params per index). Causal by construction — same formulas as
router v2.2, only parameterized.
"""
from __future__ import annotations

import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

EXEC = "framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv"

GRID = list(itertools.product(
    [96, 144, 192, 288],          # donchian bars
    [48, 96],                     # confirm bars (bearish)
    [(0.70, 0.80), (0.75, 0.85), (0.80, 0.90)],  # vol enter/exit (Schmitt)
    [(96, 48), (192, 96)],        # grind slope, grind confirm
))


def regime_array(bench, donch, confirm, ve, vx, gs, gc):
    h, l, c = bench["high"], bench["low"], bench["close"]
    hh = h.rolling(donch, min_periods=donch // 2).max()
    ll = l.rolling(donch, min_periods=donch // 2).min()
    mid = (hh + ll) / 2.0
    prev = c.shift(1)
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    vrf = tr.rolling(14, min_periods=5).mean()
    vrs = tr.rolling(96, min_periods=24).mean().replace(0, 1e-9)
    vr = (vrf / vrs).fillna(1.0).to_numpy()
    below = (c < mid).astype(float)
    sustained = below.rolling(confirm, min_periods=confirm).mean() >= 0.9
    slope = c - c.rolling(gs, min_periods=gs // 2).mean()
    slope_neg = (slope < 0).astype(float).rolling(gc, min_periods=gc).mean() >= 0.8

    comp = np.zeros(len(vr), dtype=bool)
    state = False
    for k in range(len(vr)):
        if not state and vr[k] < ve:
            state = True
        elif state and vr[k] > vx:
            state = False
        comp[k] = state

    cn, mn, sn = c.to_numpy(), mid.to_numpy(), sustained.to_numpy()
    reg = np.where(sn & (cn < mn), 0,                    # confirmed_bearish
          np.where((cn < mn) & slope_neg.to_numpy(), 1,  # grind_down
          np.where(comp, 2, 3)))                         # vol_compressed / expansion
    return reg.astype(np.int8)


def main():
    bench = pd.read_csv(EXEC, parse_dates=["timestamp"], index_col="timestamp").sort_index()
    arrs, meta = [], []
    for i, (d, cf, (ve, vx), (gs, gc)) in enumerate(GRID):
        arr = regime_array(bench, d, cf, ve, vx, gs, gc)
        arrs.append(arr)
        meta.append({"i": i, "donchian": d, "confirm": cf, "vol_enter": ve, "vol_exit": vx,
                     "grind_slope": gs, "grind_confirm": gc,
                     "shares": {k: round(float((arr == v).mean()), 3)
                                for k, v in [("bear", 0), ("grind", 1), ("chop", 2), ("expansion", 3)]}})
        print(f"[{i:02d}] donch {d} conf {cf} vol {ve}/{vx} grind {gs}/{gc} -> "
              f"bear {meta[-1]['shares']['bear']:.2f} grind {meta[-1]['shares']['grind']:.2f} "
              f"chop {meta[-1]['shares']['chop']:.2f} exp {meta[-1]['shares']['expansion']:.2f}", flush=True)
    np.savez_compressed("data/precompute/regime_grid.npz", lanes=np.stack(arrs),
                        index=bench.index.astype("int64").to_numpy())
    json.dump(meta, open("data/precompute/regime_grid.json", "w"), indent=1)
    print(f"GRID DONE: {len(arrs)} series saved")


if __name__ == "__main__":
    main()
