"""
Module 4 — Graphing (FIXED)

Creates a single image with three vertically-stacked panels:

  Panel 1: Base/quote price + total equity (right axis), aligned by
           timestamp. Vertical lines mark trades (green=buy, red=sell).
  Panel 2: Indicators used by the model (swing points, bias, MSS zones).
  Panel 3: Running drawdown for base/quote and equity.

Uses matplotlib for PNG output.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

logger = logging.getLogger(__name__)


def generate_graph(
    result,                             # SimulationResult from module 2
    output_path: str,
    title: str = "Scalping Strategy Simulation",
    price_col: str = "price",
) -> str:
    """
    Generate a 3-panel performance chart and save to output_path.

    Args:
        result: SimulationResult with equity_curve, trades, indicators_history
        output_path: where to save the PNG
        title: chart title
        price_col: column name for price in equity_curve dataframe

    Returns: path to saved image
    """
    df = result.equity_curve.copy()
    if df.empty:
        raise ValueError("Empty equity curve — nothing to plot")

    df["timestamp_dt"] = pd.to_datetime(df["timestamp"])
    timestamps = df["timestamp_dt"]

    # ── Setup figure ──────────────────────────────────────────────
    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(16, 12),
        gridspec_kw={"height_ratios": [3, 1.5, 1.5]},
        sharex=True,
    )
    fig.suptitle(title, fontsize=14, fontweight="bold")

    # ── Panel 1: Price + Equity ───────────────────────────────────
    price = df[price_col].values.astype(float)
    equity = df["equity"].values.astype(float)

    # Normalize both to start at 1.0 for comparison
    price_norm = price / price[0]
    equity_norm = equity / equity[0]

    color_price = "#2563eb"
    color_equity = "#059669"

    ax1.plot(timestamps, price_norm, color=color_price, linewidth=1.2,
             label="Price (norm)", zorder=2)
    ax1.set_ylabel("Price (norm)", color=color_price, fontsize=10)
    ax1.tick_params(axis="y", labelcolor=color_price)

    ax1b = ax1.twinx()
    ax1b.plot(timestamps, equity_norm, color=color_equity, linewidth=1.8,
              label="Equity (norm)", zorder=3)
    ax1b.set_ylabel("Equity (norm)", color=color_equity, fontsize=10)
    ax1b.tick_params(axis="y", labelcolor=color_equity)

    # Baseline
    ax1.axhline(y=1.0, color="#94a3b8", linewidth=0.8, linestyle="--", alpha=0.6)

    # Trade markers
    for trade in result.trades:
        tt = pd.Timestamp(trade.entry_time)
        color = "#16a34a" if trade.direction == "long" else "#dc2626"
        ax1.axvline(x=tt, color=color, linewidth=0.8, linestyle="--", alpha=0.5)

        # Exit markers (smaller)
        te = pd.Timestamp(trade.exit_time)
        ax1.axvline(x=te, color=color, linewidth=0.4, linestyle=":", alpha=0.3)

    # Legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax1b.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)

    # ── Panel 2: Indicators ───────────────────────────────────────
    _plot_indicators(ax2, timestamps, result, df)

    # ── Panel 3: Drawdown ─────────────────────────────────────────
    price_peak = np.maximum.accumulate(price)
    eq_peak = np.maximum.accumulate(equity)
    price_dd = (price - price_peak) / price_peak * 100
    eq_dd = (equity - eq_peak) / eq_peak * 100

    ax3.fill_between(timestamps, 0, price_dd, color="#2563eb", alpha=0.15,
                     label="Price DD")
    ax3.plot(timestamps, price_dd, color="#2563eb", linewidth=0.8, alpha=0.7)
    ax3.fill_between(timestamps, 0, eq_dd, color="#059669", alpha=0.15,
                     label="Equity DD")
    ax3.plot(timestamps, eq_dd, color="#059669", linewidth=1.2)
    ax3.axhline(y=0, color="#94a3b8", linewidth=0.8)
    ax3.set_ylabel("Drawdown %", fontsize=10)
    ax3.legend(loc="lower left", fontsize=9)
    ax3.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.1f}%"))

    # ── Formatting ────────────────────────────────────────────────
    ax3.set_xlabel("Date", fontsize=10)
    for ax in [ax1, ax2, ax3]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.grid(True, alpha=0.3, linewidth=0.5)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    logger.info(f"Graph saved → {output_path}")
    return str(output_path)


def _plot_indicators(ax, timestamps, result, df):
    """Plot model indicators on panel 2 with trade markers."""
    indicators = result.indicators_history

    if not indicators:
        ax.text(0.5, 0.5, "No indicators available", transform=ax.transAxes,
                ha="center", va="center", color="#94a3b8")
        return

    # ── Trade entry/exit vertical lines on panel 2 ────────────────
    for trade in result.trades:
        tt = pd.Timestamp(trade.entry_time)
        color = "#16a34a" if trade.direction == "long" else "#dc2626"
        ax.axvline(x=tt, color=color, linewidth=0.8, linestyle="--", alpha=0.5, zorder=1)
        te = pd.Timestamp(trade.exit_time)
        ax.axvline(x=te, color=color, linewidth=0.4, linestyle=":", alpha=0.3, zorder=1)

    n = len(timestamps)

    # Extract bias signal over time (convert to numeric)
    bias_vals = []
    for ind in indicators:
        b = ind.get("bias", "neutral")
        if b == "bullish":
            bias_vals.append(0.5)
        elif b == "bearish":
            bias_vals.append(-0.5)
        else:
            bias_vals.append(0.0)

    bias_vals = np.array(bias_vals)
    if len(bias_vals) < n:
        bias_vals = np.pad(bias_vals, (0, n - len(bias_vals)), constant_values=0.0)
    bias_vals = bias_vals[:n]

    # Plot bias as filled area
    ax.fill_between(timestamps, 0, bias_vals, where=(bias_vals > 0),
                    color="#16a34a", alpha=0.3, label="Bullish bias")
    ax.fill_between(timestamps, 0, bias_vals, where=(bias_vals < 0),
                    color="#dc2626", alpha=0.3, label="Bearish bias")

    # Plot MSS signals
    mss_ts = []
    mss_vals = []
    for i, ind in enumerate(indicators):
        if ind.get("m5_mss") and i < n:
            mss_ts.append(timestamps.iloc[i])
            mss_vals.append(0.8 if ind.get("m5_trend") == "bullish" else -0.8)

    if mss_ts:
        ax.scatter(mss_ts, mss_vals, marker="^",
                   c=["#16a34a" if v > 0 else "#dc2626" for v in mss_vals],
                   s=40, zorder=5, label="MSS")

    # Plot unique swing points from the last indicator (has full accumulated lists)
    last_ind = indicators[-1] if indicators else {}
    for swing_ts, swing_price in last_ind.get("m5_swing_highs", []):
        sp_ts = pd.Timestamp(swing_ts)
        if sp_ts >= timestamps.iloc[0] and sp_ts <= timestamps.iloc[-1]:
            ax.scatter(sp_ts, 1.0, marker="v", color="#dc2626", s=15, alpha=0.4)
    for swing_ts, swing_price in last_ind.get("m5_swing_lows", []):
        sp_ts = pd.Timestamp(swing_ts)
        if sp_ts >= timestamps.iloc[0] and sp_ts <= timestamps.iloc[-1]:
            ax.scatter(sp_ts, -1.0, marker="^", color="#16a34a", s=15, alpha=0.4)

    ax.set_ylabel("Bias / Signals", fontsize=10)
    ax.set_ylim(-1.2, 1.2)
    ax.axhline(y=0, color="#94a3b8", linewidth=0.8)
    ax.legend(loc="upper left", fontsize=8)
