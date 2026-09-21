#!/usr/bin/env python3
"""
Train / Validation / Test — STRICT temporal split
FOR: crypto/scraping_rules (Market Structure Scalping Strategy)

NO data sharing between train, validation, and test:
  • TRAIN:   oldest data — Optuna optimization finds best ModelParams
  • VAL:     middle data — verify params generalize beyond training
  • TEST:    most recent data — final evaluation (untouched by optimization)

Uses the project's own modules:
  - data_loader.py (Module 1) → fetch 5m, 1h, 2h candles from OKX
  - model.py (Module 3) → ScalpingModel signal generator
  - simulation.py (Module 7) → SimulationEngine for backtesting
  - graphing.py (Module 4) → 3-panel performance charts
  - optimizer.py (Module 6) → Optuna parameter search

Usage:
    cd crypto/scraping_rules/code
    python train_val_test.py --train-days 40 --val-days 7 --test-days 14
"""

import sys, os, json, logging, argparse, time, copy
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import ccxt

# Ensure the code directory is importable
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from data_loader import DataLoader, DEFAULT_CACHE_DIR
from model import ScalpingModel, ModelParams, Action
from simulation import SimulationEngine, SimulationResult, Trade
from optimizer import suggest_params, DEFAULT_PARAM_SPACE
from graphing import generate_graph

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(message)s]")
logger = logging.getLogger("train_val_test")

OUT_DIR = Path(__file__).parent / "output" / "train_val_test"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── Constants ───────────────────────────────────────────────────────
GAP_CANDLES_5M = 288   # 1 day in 5m candles (24h × 12)
GAP_HOURS = 24         # 1 day gap for 1h/2h data

# Default timeframe setup (matches model's default: execution=5m, bias=1h+2h)
EXECUTION_TF = "5m"
BIAS_TFS = ["1h", "2h"]
ALL_TFS = [EXECUTION_TF] + BIAS_TFS

# Fee (OKX taker)
FEE = 0.0008
INITIAL_CAPITAL = 10000.0


# ─══ RSI (Wilder-style) ═════════════════════════════════════════════

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI via ta if available, else manual EMA."""
    try:
        from ta.momentum import RSIIndicator
        return RSIIndicator(series, window=period, fillna=False).rsi()
    except ImportError:
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - 100 / (1 + rs)


# ─══ Fast OKX Data Fetch ══════════════════════════════════════════════

def fetch_all_timeframes(
    symbol: str, start: datetime, end: datetime,
    source: str = "okx", force_refresh: bool = False,
) -> Dict[str, str]:
    """Fetch 5m, 1h, 2h candles and return {tf: csv_path} dict."""
    loader = DataLoader()
    data_files: Dict[str, str] = {}

    tf_minutes = {"5m": 5, "1h": 60, "2h": 120}
    okx_limits = {"5m": 300, "1h": 300, "2h": 300}

    for tf in ALL_TFS:
        logger.info(f"Fetching {tf} candles for {symbol}...")
        t0 = time.time()

        # Use direct ccxt for better progress logging
        cache_path = DEFAULT_CACHE_DIR / f"okx_{symbol.replace('/', '_')}_{tf}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.csv"

        if not force_refresh and cache_path.exists():
            df = pd.read_csv(cache_path, parse_dates=['timestamp'], index_col='timestamp')
            df.sort_index(inplace=True)
            c_start = df.index.min().to_pydatetime().replace(tzinfo=timezone.utc)
            c_end = df.index.max().to_pydatetime().replace(tzinfo=timezone.utc)
            if c_start <= start.replace(tzinfo=timezone.utc) and c_end >= end.replace(tzinfo=timezone.utc):
                logger.info(f"  Cache hit: {len(df)} candles ({time.time()-t0:.1f}s)")
                data_files[tf] = str(cache_path)
                continue

        ex = ccxt.okx({"enableRateLimit": True})
        ex.load_markets()

        since_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        all_candles = []
        n_req = 0
        limit = okx_limits.get(tf, 300)

        logger.info(f"  Fetching {tf} from {start} to {end}...")
        while since_ms < end_ms:
            try:
                chunk = ex.fetch_ohlcv(symbol, tf, since=since_ms, limit=limit)
            except Exception as e:
                logger.error(f"  Request {n_req} failed: {e}")
                time.sleep(1)
                continue
            if not chunk:
                break
            all_candles.extend(chunk)
            since_ms = chunk[-1][0] + 1
            n_req += 1
            if n_req % 50 == 0:
                logger.info(f"    {n_req} requests, {len(all_candles)} candles")

            # Stop if we've passed the end
            if chunk[-1][0] > end_ms:
                break

        logger.info(f"  {tf}: {len(all_candles)} candles, {n_req} reqs ({time.time()-t0:.0f}s)")

        if len(all_candles) < 10:
            logger.error(f"  Not enough {tf} data!")
            continue

        df = pd.DataFrame(all_candles, columns=['timestamp','open','high','low','close','volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        # end is tz-aware, index is tz-naive — strip for comparison
        end_naive = end.replace(tzinfo=None)
        df = df[df.index <= end_naive]
        df.to_csv(cache_path)
        data_files[tf] = str(cache_path)

    return data_files


# ─══ Temporal Split ═══════════════════════════════════════════════════

def compute_splits(
    data_files: Dict[str, str],
    val_days: float, test_days: float,
) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str], datetime, datetime, datetime]:
    """Split data_files into train/val/test periods.

    Splits are based on the execution TF's date range, then applied to all TFs.
    Returns (train_files, val_files, test_files, train_end, val_end, test_start).
    """
    exec_path = data_files[EXECUTION_TF]
    exec_df = pd.read_csv(exec_path, parse_dates=['timestamp'], index_col='timestamp')
    exec_df.sort_index(inplace=True)

    total_end = exec_df.index.max().to_pydatetime()
    total_start = exec_df.index.min().to_pydatetime()

    val_delta = timedelta(days=val_days)
    test_delta = timedelta(days=test_days)
    gap_delta = timedelta(days=1)

    test_start = total_end - test_delta
    val_end_dt = test_start - gap_delta
    val_start_dt = val_end_dt - val_delta
    train_end_dt = val_start_dt - gap_delta

    logger.info(f"Total data: {total_start} → {total_end}")
    logger.info(f"Train: {total_start} → {train_end_dt}")
    logger.info(f"Val:   {val_start_dt} → {val_end_dt}")
    logger.info(f"Test:  {test_start} → {total_end}")

    def filter_df(path: str, start: datetime, end: datetime) -> str:
        df = pd.read_csv(path, parse_dates=['timestamp'], index_col='timestamp')
        df.sort_index(inplace=True)
        filtered = df[(df.index >= start) & (df.index <= end)]
        out_path = OUT_DIR / f"_{path.split('/')[-1].replace('.csv', '')}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.csv"
        filtered.to_csv(out_path)
        return str(out_path)

    train_files = {tf: filter_df(data_files[tf], total_start, train_end_dt) for tf in ALL_TFS}
    val_files = {tf: filter_df(data_files[tf], val_start_dt, val_end_dt) for tf in ALL_TFS}
    test_files = {tf: filter_df(data_files[tf], test_start, total_end) for tf in ALL_TFS}

    return train_files, val_files, test_files, train_end_dt, val_end_dt, test_start


# ─══ Simulation Helper ════════════════════════════════════════════════

def run_simulation(
    data_files: Dict[str, str],
    params: ModelParams,
    label: str = "",
    allow_shorts: bool = True,
    create_graphs: bool = False,
    graph_title: str = "",
) -> SimulationResult:
    """Run a simulation with given params and return the result."""
    model = ScalpingModel(params=params, execution_tf=EXECUTION_TF, bias_tfs=BIAS_TFS)
    engine = SimulationEngine(
        model=model,
        initial_capital=INITIAL_CAPITAL,
        fee=FEE,
        allow_shorts=allow_shorts,
        create_graphs=create_graphs,
    )
    result = engine.run(data_files=data_files, execution_tf=EXECUTION_TF)
    logger.info(f"  {label}: return={result.total_return_pct:+.2f}% | "
                f"sharpe={result.sharpe_ratio:.3f} | trades={result.total_trades} | "
                f"win={result.win_rate:.0f}% | maxDD={result.max_drawdown_pct:.2f}%")
    return result


# ─══ Optuna Optimization on TRAIN ═════════════════════════════════════

def objective_factory(train_files: Dict[str, str], allow_shorts: bool = True):
    """Create Optuna objective function with progressive penalties."""
    def objective(trial):
        params_dict = suggest_params(trial, DEFAULT_PARAM_SPACE)
        params = ModelParams(**params_dict)

        # Suppress noisy trade logging during optimization
        import logging as _logging
        _logging.getLogger('model').setLevel(_logging.WARNING)
        _logging.getLogger('simulation').setLevel(_logging.WARNING)

        model = ScalpingModel(params=params, execution_tf=EXECUTION_TF, bias_tfs=BIAS_TFS)
        engine = SimulationEngine(
            model=model, initial_capital=INITIAL_CAPITAL, fee=FEE,
            allow_shorts=allow_shorts,
        )
        result = engine.run(data_files=train_files, execution_tf=EXECUTION_TF)

        _logging.getLogger('model').setLevel(_logging.INFO)
        _logging.getLogger('simulation').setLevel(_logging.INFO)

        # Multi-objective: maximize Sharpe, penalize negative returns
        sharpe = max(result.sharpe_ratio, -5.0)
        ret = result.total_return_pct
        trades = result.total_trades

        # Base score
        score = sharpe

        # Progressive penalties
        if trades < 5:
            score -= 2.0 * (5 - trades)  # penalize too few trades
        if ret < -15:
            score -= 2.0 * abs(ret + 15) / 10  # heavy loss penalty
        if result.max_drawdown_pct > 30:
            score -= (result.max_drawdown_pct - 30) / 5

        trial.set_user_attr("return_pct", ret)
        trial.set_user_attr("sharpe", sharpe)
        trial.set_user_attr("trades", trades)
        trial.set_user_attr("win_rate", result.win_rate)
        trial.set_user_attr("max_dd", result.max_drawdown_pct)

        return score

    return objective


def run_optimization(train_files: Dict[str, str], n_trials: int = 100,
                     allow_shorts: bool = True) -> Tuple[ModelParams, Dict]:
    """Run Optuna on TRAIN data, return best params + study info."""
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        logger.info("Optuna not installed — using default params")
        return ModelParams(), {"n_trials": 0, "best_value": 0, "best_params": {}, "elapsed_seconds": 0}

    logger.info(f"Optuna optimization: {n_trials} trials on TRAIN data...")
    t0 = time.time()

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=10, n_warmup_steps=5),
    )

    obj = objective_factory(train_files, allow_shorts=allow_shorts)
    study.optimize(obj, n_trials=n_trials, show_progress_bar=True)

    elapsed = time.time() - t0
    best = study.best_params
    logger.info(f"Optimization complete: {elapsed:.0f}s, {n_trials} trials")
    logger.info(f"Best params: {json.dumps(best, indent=2, default=str)}")
    logger.info(f"Best score: {study.best_value:.3f}")

    study_info = {
        "n_trials": n_trials,
        "best_value": study.best_value,
        "best_params": best,
        "elapsed_seconds": elapsed,
    }

    return ModelParams(**best), study_info


# ─══ Plotly Graph (crypto-trading-graphs skill standard) ════════════

def generate_plotly_graph(
    result: SimulationResult,
    data_files: Dict[str, str],
    output_path: str,
    title: str = "Market Structure Scalping",
):
    """
    3-panel Plotly HTML following crypto-trading-graphs skill EXACTLY:
      Panel 1: BTC price + Equity, SAME axis, normalized to 100 at anchor
      Panel 2: RSI(14) indicator
      Panel 3: Volume with MA(20)
      Shapes-based trade markers (green=entry, red=exit)
      CDN Plotly, ISO timestamps, type='date'
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    df = result.equity_curve.copy()
    if df.empty:
        raise ValueError("Empty equity curve")

    df["timestamp_dt"] = pd.to_datetime(df["timestamp"])

    # Load BTC data for the test period
    btc = pd.read_csv(data_files[EXECUTION_TF],
                      parse_dates=['timestamp'], index_col='timestamp')
    btc.sort_index(inplace=True)
    btc = btc[btc.index >= df["timestamp_dt"].min()]

    # ── Anchor: first timestamp ───────────────────────────────────
    anchor_ts = df["timestamp_dt"].iloc[0]

    # Align BTC to equity timestamps
    btc_aligned = btc.reindex(df["timestamp_dt"], method='ffill')

    # Normalize both to 100 at anchor
    price_at_anchor = float(btc.loc[btc.index >= anchor_ts, 'close'].iloc[0])
    eq_at_anchor = float(df["equity"].iloc[0])

    btc_norm = btc_aligned['close'] / price_at_anchor * 100.0
    eq_norm = df["equity"] / eq_at_anchor * 100.0

    # Unified Y range
    all_vals = pd.concat([btc_norm.dropna(), eq_norm.dropna()])
    ymin, ymax = all_vals.min(), all_vals.max()
    pad = (ymax - ymin) * 0.05
    y_lo, y_hi = ymin - pad, ymax + pad

    # RSI(14)
    btc_plot = btc.loc[df["timestamp_dt"].min():df["timestamp_dt"].max()].copy()
    btc_plot['rsi_14'] = rsi(btc_plot['close'], 14)
    btc_plot['vol_ma20'] = btc_plot['volume'].rolling(20, min_periods=1).mean()

    # ISO timestamps (Plotly bug avoidance)
    btc_x = [str(t) for t in btc_plot.index]
    eq_x = [str(t) for t in df["timestamp_dt"]]
    anc_s = str(anchor_ts)

    # Trade times
    entries = [str(t.entry_time) for t in result.trades]
    exits = [str(t.exit_time) for t in result.trades]
    directions = [t.direction for t in result.trades]

    # Volume colors
    vol_colors = ['rgba(180,180,180,0.35)' if v >= m else 'rgba(255,100,100,0.25)'
                  for v, m in zip(btc_plot['volume'], btc_plot['vol_ma20'])]

    # ── Build figure ──────────────────────────────────────────────
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.10,
        row_heights=[0.40, 0.30, 0.30],
        subplot_titles=("BTC & Equity — Normalized to 100", "RSI(14)", "Volume + MA(20)"),
    )

    # Panel 1: Price + Equity
    fig.add_trace(go.Scatter(x=btc_x, y=btc_norm, mode='lines',
        name='BTC/USDT', line=dict(color='#1f77b4', width=1.2), opacity=0.85), row=1, col=1)
    fig.add_trace(go.Scatter(x=eq_x, y=eq_norm, mode='lines',
        name='Equity', line=dict(color='#2ca02c', width=2.2)), row=1, col=1)
    fig.add_hline(y=100, line=dict(color='gray', width=0.8, dash='dot'),
                  opacity=0.3, row=1, col=1)

    # Panel 2: RSI
    fig.add_trace(go.Scatter(x=btc_x, y=btc_plot['rsi_14'], mode='lines',
        name='RSI(14)', line=dict(color='#9467bd', width=1.2)), row=2, col=1)
    fig.add_hline(y=70, line=dict(color='red', width=0.8, dash='dot'),
                  opacity=0.4, row=2, col=1)
    fig.add_hline(y=30, line=dict(color='green', width=0.8, dash='dot'),
                  opacity=0.4, row=2, col=1)
    fig.add_hline(y=50, line=dict(color='gray', width=0.5), opacity=0.2, row=2, col=1)

    # Panel 3: Volume
    fig.add_trace(go.Bar(x=btc_x, y=btc_plot['volume'],
        name='Volume', marker_color=vol_colors, opacity=0.7), row=3, col=1)
    fig.add_trace(go.Scatter(x=btc_x, y=btc_plot['vol_ma20'], mode='lines',
        name='Vol MA(20)', line=dict(color='#ff7f0e', width=1.2)), row=3, col=1)
    fig.add_trace(go.Scatter(x=btc_x, y=btc_plot['vol_ma20'] * 0.5, mode='lines',
        name='Low-vol (50% MA)', line=dict(color='red', width=1, dash='dot'),
        opacity=0.6), row=3, col=1)

    # ═══ Trade markers — shapes-based (O(n), NOT O(n²) add_vline loop) ═══
    shapes = []
    for i, (entry_s, exit_s, direction) in enumerate(zip(entries, exits, directions)):
        entry_color = 'green' if direction == 'long' else 'blue'
        exit_color = 'red' if direction == 'long' else 'orange'
        for x_s, color in [(entry_s, entry_color), (exit_s, exit_color)]:
            for r in [1, 2, 3]:
                shapes.append(dict(
                    type='line', x0=x_s, x1=x_s, y0=0, y1=1,
                    xref=f'x{r}', yref='paper',
                    line=dict(color=color, width=0.8),
                    opacity=0.35,
                ))

    fig.update_layout(shapes=shapes)

    # ── Layout ────────────────────────────────────────────────────
    fig.update_layout(
        title=dict(text=f'<b>{title}</b>', x=0.5, font=dict(size=13)),
        hovermode='x unified',
        legend=dict(x=0.01, y=0.99, bgcolor='rgba(255,255,255,0.88)',
                    bordercolor='#ccc', borderwidth=1, font=dict(size=10)),
        height=1100, plot_bgcolor='white', margin=dict(l=80, r=80, t=100, b=60),
    )
    fig.update_yaxes(title='Normalized (%)', range=[y_lo, y_hi], ticksuffix='%',
        showgrid=True, gridcolor='rgba(0,0,0,0.07)', row=1, col=1)
    fig.update_yaxes(title='RSI', range=[0, 100],
        showgrid=True, gridcolor='rgba(0,0,0,0.07)', row=2, col=1)
    fig.update_yaxes(title='Volume',
        showgrid=True, gridcolor='rgba(0,0,0,0.07)', row=3, col=1)
    for r in [1, 2, 3]:
        fig.update_xaxes(type='date', showgrid=True,
                         gridcolor='rgba(0,0,0,0.07)', row=r, col=1)
    fig.update_xaxes(title_text='Time (UTC)', row=3, col=1)

    fig.write_html(str(output_path), include_plotlyjs='cdn')
    sz = os.path.getsize(output_path)
    logger.info(f"Plotly graph saved: {output_path} ({sz/1024:.0f} KB)")
    return output_path


# ─══ Main ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Train/Val/Test — Market Structure Scalping Strategy")
    parser.add_argument("--train-days", type=float, default=None,
                        help="Training days (default: auto — all old data)")
    parser.add_argument("--val-days", type=float, default=7,
                        help="Validation days (default: 7)")
    parser.add_argument("--test-days", type=float, default=14,
                        help="Test days (default: 14)")
    parser.add_argument("--trials", type=int, default=50,
                        help="Optuna trials (default: 50)")
    parser.add_argument("--symbol", type=str, default="BTC/USDT")
    parser.add_argument("--force-fresh", action="store_true",
                        help="Ignore cache, refetch data")
    parser.add_argument("--no-shorts", action="store_true",
                        help="Disable short selling")
    parser.add_argument("--no-graphs", action="store_true",
                        help="Skip graph generation")
    args = parser.parse_args()
    # Default: shorts enabled for simulation
    ALLOW_SHORTS = not args.no_shorts

    print("\n" + "=" * 72)
    print("  TRAIN / VAL / TEST — Market Structure Scalping")
    print("  scraping_rules strategy | Multi-TF: 5m, 1h, 2h")
    print("=" * 72)
    print(f"  Symbol: {args.symbol}")
    print(f"  Val days: {args.val_days} | Test days: {args.test_days}")
    print(f"  Optuna trials: {args.trials}")
    print(f"  Fee: {FEE*100:.2f}% | Capital: ${INITIAL_CAPITAL:,.0f}")
    print(f"  Shorts: {'ON' if ALLOW_SHORTS else 'OFF'}")
    print("=" * 72)

    # ─── 1. Determine date range ─────────────────────────────────────
    # Fetch a small sample to find the latest available data
    loader = DataLoader()
    now = datetime.now(timezone.utc)
    end_dt = now.replace(minute=0, second=0, microsecond=0)
    # Total data needed: max 90 days
    total_days = (args.train_days or 60) + args.val_days + args.test_days + 3
    start_dt = end_dt - timedelta(days=total_days)

    # ─── 2. Fetch Data ──────────────────────────────────────────────
    print(f"\n─── Fetching {total_days}d of 5m/1h/2h data ───")
    print(f"  Range: {start_dt} → {end_dt}")
    t0 = time.time()
    data_files = fetch_all_timeframes(args.symbol, start_dt, end_dt,
                                      force_refresh=args.force_fresh)
    print(f"  Total fetch: {time.time()-t0:.0f}s")

    if EXECUTION_TF not in data_files:
        print(f"ERROR: Could not fetch {EXECUTION_TF} data")
        sys.exit(1)

    # ─── 3. Temporal Split ──────────────────────────────────────────
    print(f"\n─── Temporal Split ───")
    train_files, val_files, test_files, train_end, val_end, test_start = \
        compute_splits(data_files, args.val_days, args.test_days)

    print(f"\n  ⚠ Leakage check:")
    for tf in ALL_TFS:
        if tf in train_files and tf in val_files and tf in test_files:
            print(f"    {tf}: train→{train_end} | gap | val→{val_end} | gap | test from {test_start}")

    # ─── 4. Optimize on TRAIN ────────────────────────────────────────
    print(f"\n─── Step 1: Optimize on TRAIN data ───")
    best_params, study_info = run_optimization(train_files, n_trials=args.trials,
                                                allow_shorts=ALLOW_SHORTS)

    # ─── 5. Validate on VAL ─────────────────────────────────────────
    print(f"\n─── Step 2: Validate on VAL data ───")
    val_result = run_simulation(val_files, best_params, label="VAL", allow_shorts=ALLOW_SHORTS)

    # ─── 6. Test on TEST ────────────────────────────────────────────
    print(f"\n─── Step 3: Test on TEST data (UNSEEN) ───")
    test_result = run_simulation(test_files, best_params, label="TEST",
                                 allow_shorts=ALLOW_SHORTS,
                                 create_graphs=not args.no_graphs,
                                 graph_title="Market Structure Scalping — TEST Period")

    # ─── 7. BTC Buy & Hold comparison ────────────────────────────────
    test_exec_df = pd.read_csv(test_files[EXECUTION_TF],
                               parse_dates=['timestamp'], index_col='timestamp')
    test_exec_df.sort_index(inplace=True)
    btc_start = test_exec_df['close'].iloc[0]
    btc_end = test_exec_df['close'].iloc[-1]
    btc_return = (btc_end - btc_start) / btc_start * 100

    # ─── 8. Report ──────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  RESULTS — Market Structure Scalping")
    print("=" * 72)
    print(f"  Optimization: {study_info['n_trials']} trials, "
          f"best_score={study_info['best_value']:.3f}")
    print(f"  Best params:")
    for k, v in study_info['best_params'].items():
        print(f"    {k}: {v}")
    print()
    print(f"  ┌──────────────────────────┬──────────────┬──────────────┐")
    print(f"  │ Metric                   │ VAL          │ TEST (FINAL) │")
    print(f"  ├──────────────────────────┼──────────────┼──────────────┤")
    print(f"  │ Return                   │ {val_result.total_return_pct:+.4f}%    │ {test_result.total_return_pct:+.4f}%    │")
    print(f"  │ BTC Buy & Hold           │ —            │ {btc_return:+.4f}%    │")
    print(f"  │ Sharpe Ratio             │ {val_result.sharpe_ratio:.3f}         │ {test_result.sharpe_ratio:.3f}         │")
    print(f"  │ Max Drawdown             │ {val_result.max_drawdown_pct:.4f}%    │ {test_result.max_drawdown_pct:.4f}%    │")
    print(f"  │ Total Trades             │ {val_result.total_trades:<4d}         │ {test_result.total_trades:<4d}         │")
    print(f"  │ Win Rate                 │ {val_result.win_rate:.0f}%           │ {test_result.win_rate:.0f}%           │")
    print(f"  │ Avg Win / Avg Loss       │ {val_result.avg_win_pct:+.2f}% / {val_result.avg_loss_pct:+.2f}% │ {test_result.avg_win_pct:+.2f}% / {test_result.avg_loss_pct:+.2f}% │")
    print(f"  │ Profit Factor            │ {val_result.profit_factor:.3f}         │ {test_result.profit_factor:.3f}         │")
    print(f"  └──────────────────────────┴──────────────┴──────────────┘")

    # ─── 9. Graphs ──────────────────────────────────────────────────
    if not args.no_graphs:
        print(f"\n─── Generating Graphs ───")
        try:
            # Test period Plotly graph (following crypto-trading-graphs skill)
            test_path = str(OUT_DIR / "test_period_chart.html")
            generate_plotly_graph(test_result, test_files, test_path,
                title=f"Market Structure Scalping — TEST Period\n"
                      f"{test_start.strftime('%Y-%m-%d')} → {end_dt.strftime('%Y-%m-%d')} | "
                      f"Return: {test_result.total_return_pct:+.4f}% | "
                      f"BTC: {btc_return:+.2f}% | "
                      f"Shorts: {'ON' if ALLOW_SHORTS else 'OFF'}")
            print(f"  Test graph (Plotly): {test_path}")
        except Exception as e:
            logger.error(f"Plotly graph failed, falling back to PNG: {e}")
            test_path = str(OUT_DIR / "test_period_chart.png")
            generate_graph(test_result, test_path,
                          title="Market Structure Scalping — TEST Period")
            print(f"  Test graph (PNG): {test_path}")

    # ─── 10. Save Results ───────────────────────────────────────────
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "symbol": args.symbol,
            "execution_tf": EXECUTION_TF,
            "bias_tfs": BIAS_TFS,
            "initial_capital": INITIAL_CAPITAL,
            "fee": FEE,
            "val_days": args.val_days,
            "test_days": args.test_days,
            "optuna_trials": args.trials,
            "allow_shorts": ALLOW_SHORTS,
        },
        "train_end": str(train_end),
        "val_end": str(val_end),
        "test_start": str(test_start),
        "optimization": study_info,
        "val_metrics": {
            "return_pct": val_result.total_return_pct,
            "sharpe": val_result.sharpe_ratio,
            "max_dd_pct": val_result.max_drawdown_pct,
            "total_trades": val_result.total_trades,
            "win_rate": val_result.win_rate,
            "avg_win_pct": val_result.avg_win_pct,
            "avg_loss_pct": val_result.avg_loss_pct,
            "profit_factor": val_result.profit_factor,
        },
        "test_metrics": {
            "return_pct": test_result.total_return_pct,
            "sharpe": test_result.sharpe_ratio,
            "max_dd_pct": test_result.max_drawdown_pct,
            "total_trades": test_result.total_trades,
            "win_rate": test_result.win_rate,
            "avg_win_pct": test_result.avg_win_pct,
            "avg_loss_pct": test_result.avg_loss_pct,
            "profit_factor": test_result.profit_factor,
            "btc_return_pct": btc_return,
        },
        "test_trades": [
            {
                "entry": str(t.entry_time),
                "exit": str(t.exit_time),
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl_pct": t.pnl_pct,
                "exit_reason": t.exit_reason,
            }
            for t in test_result.trades
        ],
    }

    results_path = OUT_DIR / "train_val_test_results.json"
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  ✓ Results saved → {results_path}")
    print(f"  ✓ Output directory → {OUT_DIR}")
    print("\n" + "=" * 72)
    print("  DONE")
    print("=" * 72)


if __name__ == "__main__":
    main()
