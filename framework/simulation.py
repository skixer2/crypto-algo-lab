"""
Module 7 — Simulation Engine (FIXED)

Owns ALL financial state: cash, crypto quantity, position, SL/TP.
The model (module 3) is a pure signal generator — no financial state.

Equity never resets — one continuous run from start to end.
Supports long and short positions (shorts gated by allow_shorts flag).

Accepts an arbitrary set of timeframes via data_files dict.

⚠️  All trading decisions use ONLY candle close prices.
    Never uses high/low — intra-candle wicks retrace and are unreliable.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: str
    entry_price: float
    exit_price: float
    pnl_pct: float       # relative to MTM equity at exit
    pnl_abs: float
    exit_reason: str      # "stop_loss", "take_profit", "signal", "force_close"


@dataclass
class SimulationResult:
    equity_curve: pd.DataFrame
    trades: List[Trade]
    final_equity: float
    initial_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    total_trades: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float
    indicators_history: List[Dict]


class SimulationEngine:
    """
    Fixed simulation engine. Portable across any model.

    On each candle:
      1. If in a position: check SL/TP against candle high/low
      2. Else: call model.predict() → action, size_pct, indicators
      3. If action ≠ "flat": enter position with SL/TP from indicators
      4. Record MTM equity

    Timeframe-agnostic: accepts data_files = {"5m": "btc_5m.csv", "1h": "btc_1h.csv", ...}.
    """

    def __init__(
        self,
        model,
        initial_capital: float = 10000.0,
        fee: float = 0.0008,
        exchange: str = "simulation",
        create_graphs: bool = False,
        allow_shorts: bool = False,
    ):
        self.model = model
        self.initial_capital = initial_capital
        self.fee = fee
        self.exchange = exchange
        self.create_graphs = create_graphs
        self.allow_shorts = allow_shorts

        # ── Financial state (single source of truth) ──────────────
        self.cash: float = initial_capital
        self.crypto_qty: float = 0.0
        self.position: Optional[str] = None   # "long" | "short" | None
        self.entry_price: float = 0.0
        self.stop_loss: float = 0.0
        self.take_profit: float = 0.0
        self._entry_ts: Optional[pd.Timestamp] = None

        # ── Records ───────────────────────────────────────────────
        self.equity_history: List[Dict] = []
        self.trades: List[Trade] = []
        self.indicators_hist: List[Dict] = []

    # ── Main entry point ─────────────────────────────────────────────

    def run(
        self,
        data_files: Dict[str, str],
        execution_tf: str,
        data_start: Optional[str] = None,
        data_end: Optional[str] = None,
    ) -> SimulationResult:
        """
        Execute simulation over an arbitrary set of timeframes.

        Args:
            data_files: {"5m": "/path/to/btc_5m.csv", "1h": "/path/to/btc_1h.csv", ...}
                        Must include execution_tf as one key.
            execution_tf: which timeframe's candles drive the tick loop
            data_start, data_end: optional date filters (ISO strings)

        ⚠️ All SL/TP checks use CLOSE price only — never high/low.
        """
        if execution_tf not in data_files:
            raise ValueError(
                f"execution_tf '{execution_tf}' not found in data_files keys: "
                f"{list(data_files.keys())}"
            )

        # ── Load all dataframes ──────────────────────────────────
        dfs: Dict[str, pd.DataFrame] = {}
        timestamps: Dict[str, List[pd.Timestamp]] = {}
        for tf, path in data_files.items():
            df = pd.read_csv(path, parse_dates=["timestamp"], index_col="timestamp")
            df.sort_index(inplace=True)
            if data_start:
                df = df[df.index >= pd.Timestamp(data_start)]
            if data_end:
                df = df[df.index <= pd.Timestamp(data_end)]
            dfs[tf] = df
            timestamps[tf] = list(df.index)

        # ── Execution timeframe drives the loop ──────────────────
        exec_df = dfs[execution_tf]
        bias_tfs = [tf for tf in data_files if tf != execution_tf]

        # Track how far we've fed into each bias TF
        bias_idxs: Dict[str, int] = {tf: 0 for tf in bias_tfs}

        n_bias = len(bias_tfs)
        logger.info(
            f"Sim: {len(exec_df)} candles ({execution_tf}) | "
            f"bias TFs={bias_tfs} ({n_bias}) | "
            f"capital={self.initial_capital} | shorts={'on' if self.allow_shorts else 'off'}"
        )

        # ── Main tick loop ───────────────────────────────────────
        for ts, row in exec_df.iterrows():
            price = float(row["close"])

            # Feed bias TF candles up to current execution timestamp
            for tf in bias_tfs:
                ts_list = timestamps[tf]
                bdf = dfs[tf]
                idx = bias_idxs[tf]
                while idx < len(ts_list) and ts_list[idx] <= ts:
                    self.model.update(bdf.loc[ts_list[idx]], tf)
                    idx += 1
                bias_idxs[tf] = idx

            # Feed execution TF candle
            self.model.update(row, execution_tf)

            # ── Step 1: Check exit conditions if in position ──────
            if self.position is not None:
                # Optional model-managed exit hook (backward compatible:
                # models without manage_position behave exactly as before).
                if hasattr(self.model, "manage_position"):
                    reason = self.model.manage_position(self.position, price, ts)
                    if reason:
                        self._do_exit(price, ts, f"model_exit:{reason}")
                if self.position == "long":
                    if price <= self.stop_loss:
                        self._do_exit(price, ts, "stop_loss")
                    elif price >= self.take_profit:
                        self._do_exit(price, ts, "take_profit")
                elif self.position == "short":
                    if price >= self.stop_loss:
                        self._do_exit(price, ts, "stop_loss")
                    elif price <= self.take_profit:
                        self._do_exit(price, ts, "take_profit")

            # ── Step 2: Check for new entry signal ────────────────
            if self.position is None:
                action, size_pct, indicators = self.model.predict(
                    allow_shorts=self.allow_shorts
                )
                if action != "flat":
                    sl = indicators.get("stop_loss", 0.0)
                    tp = indicators.get("take_profit", 0.0)
                    if sl > 0 and tp > 0:
                        self._do_enter(action, price, size_pct, ts, sl, tp)

            # ── Step 3: Record ────────────────────────────────────
            eq = self._eq(price)
            self.equity_history.append({
                "timestamp": ts,
                "equity": eq,
                "position": self.position,
                "price": price,
                "cash": self.cash,
                "crypto_qty": self.crypto_qty,
            })
            self.indicators_hist.append(self.model.get_indicators())

        # Force-close at end
        if self.position and len(exec_df) > 0:
            close_price = float(exec_df.iloc[-1]["close"])
            self._do_exit(close_price, exec_df.index[-1], "force_close")

        return self._build_result()

    # ── Trade execution ──────────────────────────────────────────────

    def _do_enter(self, direction: str, price: float, size_pct: float,
                  ts: pd.Timestamp, sl: float, tp: float) -> None:
        """Enter a position. All params validated before calling."""
        if self.position is not None:
            return
        eq = self._eq(price)
        trade_val = eq * size_pct
        fee_cost = trade_val * self.fee

        self.position = direction
        self.entry_price = price
        self.stop_loss = sl
        self.take_profit = tp
        self._entry_ts = ts

        if direction == "long":
            self.crypto_qty = (trade_val - fee_cost) / price
            self.cash -= trade_val
        else:  # short
            self.crypto_qty = -(trade_val - fee_cost) / price  # negative = owed
            self.cash += trade_val - fee_cost

        logger.info(
            f"ENTER {direction.upper()} @ {price:.2f} "
            f"SL={sl:.2f} TP={tp:.2f} size={size_pct:.0%}"
        )

    def _do_exit(self, price: float, ts: pd.Timestamp, reason: str) -> None:
        """Exit current position at given fill price."""
        if self.position is None:
            return

        eq_before = self._eq(price)
        trade_val = abs(self.crypto_qty) * price
        fee_cost = trade_val * self.fee

        if self.position == "long":
            pnl = self.crypto_qty * (price - self.entry_price) - fee_cost
            self.cash += self.crypto_qty * price - fee_cost
        else:  # short
            pnl = abs(self.crypto_qty) * (self.entry_price - price) - fee_cost
            self.cash -= abs(self.crypto_qty) * price + fee_cost

        pnl_pct = pnl / eq_before if eq_before > 0 else 0.0

        self.trades.append(Trade(
            entry_time=self._entry_ts,
            exit_time=ts,
            direction=self.position,
            entry_price=self.entry_price,
            exit_price=price,
            pnl_pct=pnl_pct,
            pnl_abs=pnl,
            exit_reason=reason,
        ))

        logger.info(
            f"EXIT {self.position.upper()} @ {price:.2f} "
            f"PnL={pnl_pct:+.4%} [{reason}]"
        )

        self.position = None
        self.entry_price = 0.0
        self.stop_loss = 0.0
        self.take_profit = 0.0
        self.crypto_qty = 0.0



    # ── Helpers ──────────────────────────────────────────────────────

    def _eq(self, price: float) -> float:
        return self.cash + self.crypto_qty * price

    def _build_result(self) -> SimulationResult:
        df = pd.DataFrame(self.equity_history)
        init = self.initial_capital
        final = df["equity"].iloc[-1] if len(df) > 0 else init
        ret = (final - init) / init

        peak = df["equity"].expanding().max() if len(df) > 0 else pd.Series([init])
        dd = (df["equity"] - peak) / peak
        max_dd = float(dd.min()) if len(dd) > 0 else 0.0

        r = df["equity"].pct_change().dropna() if len(df) > 1 else pd.Series()
        sharpe = float(r.mean() / r.std() * np.sqrt(35040)) if len(r) > 0 and r.std() > 0 else 0.0

        wins = [t for t in self.trades if t.pnl_pct > 0]
        losses = [t for t in self.trades if t.pnl_pct <= 0]
        wr = len(wins) / len(self.trades) if self.trades else 0.0
        gross_p = sum(t.pnl_abs for t in wins)
        gross_l = abs(sum(t.pnl_abs for t in losses))

        return SimulationResult(
            equity_curve=df, trades=self.trades,
            final_equity=final, initial_equity=init,
            total_return_pct=ret, max_drawdown_pct=max_dd,
            sharpe_ratio=sharpe, total_trades=len(self.trades),
            win_rate=wr,
            avg_win_pct=float(np.mean([t.pnl_pct for t in wins])) if wins else 0.0,
            avg_loss_pct=float(np.mean([t.pnl_pct for t in losses])) if losses else 0.0,
            profit_factor=gross_p / gross_l if gross_l > 0 else float("inf"),
            indicators_history=self.indicators_hist,
        )


def run_simulation(
    model,
    data_files: Dict[str, str],
    execution_tf: str,
    initial_capital: float = 10000.0,
    fee: float = 0.0008,
    data_start: Optional[str] = None,
    data_end: Optional[str] = None,
    allow_shorts: bool = False,
) -> SimulationResult:
    return SimulationEngine(
        model=model, initial_capital=initial_capital, fee=fee,
        allow_shorts=allow_shorts,
    ).run(data_files, execution_tf, data_start, data_end)
