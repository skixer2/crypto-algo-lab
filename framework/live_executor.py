"""
Module 5 — Live Executor (FIXED)

Executes real trades on OKX via ccxt. API keys read from environment.
Supports spot (long-only) and perpetual futures (long + short).

Usage:
    executor = LiveExecutor(exchange="okx", allow_shorts=False)
    result = executor.execute(action="long", position_pct=0.5, symbol="ETH/USDT")
"""

import os
import logging
from typing import Dict, Optional
from dataclasses import dataclass

import ccxt

logger = logging.getLogger(__name__)

# ─── Environment variable map ────────────────────────────────────────

OKX_ENV = {
    "apiKey": "OKX_API_KEY",
    "secret": "OKX_API_SECRET",
    "password": "OKX_API_PASSPHRASE",
}

REVOLUT_ENV = {
    "apiKey": "REVOLUT_API_KEY",
    "secret": "REVOLUT_API_SECRET",
}


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str]
    symbol: str
    side: str
    amount: float
    price: Optional[float]
    status: str
    error: Optional[str] = None
    raw: Optional[Dict] = None


class LiveExecutor:
    """
    Live trade executor for OKX and Revolut.

    Args:
        exchange: "okx" or "revolut"
        leverage: leverage multiplier (futures only, default 1)
        allow_shorts: if False (spot default), reject "short" actions
        dry_run: if True, log orders without sending to exchange

    Short positions require futures trading on OKX.
    Use symbol "BTC/USDT:USDT" for perpetual futures.
    Spot symbol "BTC/USDT" supports long-only.
    """

    def __init__(
        self,
        exchange: str = "okx",
        leverage: float = 1.0,
        allow_shorts: bool = False,
        dry_run: bool = False,
    ):
        exchange_lower = exchange.lower()
        if exchange_lower == "okx":
            self.env_vars = OKX_ENV
        elif exchange_lower == "revolut":
            self.env_vars = REVOLUT_ENV
        else:
            raise ValueError(
                f"Unsupported exchange: {exchange}. Supported: okx, revolut"
            )

        self.exchange_name = exchange_lower
        self.leverage = leverage
        self.allow_shorts = allow_shorts
        self.dry_run = dry_run

        self._exchange = None
        if not dry_run:
            self._exchange = self._init_exchange()

    def _init_exchange(self):
        """Initialize ccxt with env-based credentials."""
        missing = []
        creds = {}
        for key, env_name in self.env_vars.items():
            val = os.environ.get(env_name)
            if not val:
                missing.append(env_name)
            creds[key] = val or ""

        if missing:
            raise RuntimeError(
                f"Missing env vars for {self.exchange_name}: {', '.join(missing)}"
            )

        if self.exchange_name == "okx":
            ex = ccxt.okx({
                "apiKey": creds["apiKey"],
                "secret": creds["secret"],
                "password": creds["password"],
                "enableRateLimit": True,
            })
        else:  # revolut
            ex = ccxt.revolut({
                "apiKey": creds["apiKey"],
                "secret": creds["secret"],
                "enableRateLimit": True,
            })
        return ex

    def execute(
        self,
        action: str,
        position_pct: float,
        symbol: str,
    ) -> OrderResult:
        """
        Execute a trade based on model signal.

        Args:
            action: "long", "short", or "flat"
            position_pct: fraction of available balance to allocate
            symbol: trading pair ("BTC/USDT" for spot, "BTC/USDT:USDT" for futures)

        Returns: OrderResult
        """
        # ── Gate: no shorts on spot ───────────────────────────────
        if action == "short" and not self.allow_shorts:
            return OrderResult(
                success=False, order_id=None, symbol=symbol,
                side="short", amount=0.0, price=None,
                status="rejected",
                error="Shorts require allow_shorts=True and futures symbol (e.g. BTC/USDT:USDT)",
            )

        if action == "flat":
            return self._close_position(symbol)

        # ── Dry run ───────────────────────────────────────────────
        if self.dry_run:
            price = 0.0
            try:
                ticker = self._exchange.fetch_ticker(symbol)
                price = ticker.get("last") or 0.0
            except Exception:
                pass
            side = "buy" if action == "long" else "sell"
            logger.info(f"[DRY RUN] Would {side} {symbol} @ ~{price:.2f} pct={position_pct}")
            return OrderResult(
                success=True, order_id="dry_run",
                symbol=symbol, side=side, amount=0.0,
                price=price, status="dry_run",
            )

        # ── Real execution ────────────────────────────────────────
        try:
            balance = self._get_balance(symbol)
            if balance <= 0:
                return OrderResult(
                    success=False, order_id=None, symbol=symbol,
                    side=action, amount=0.0, price=None,
                    status="rejected", error="Insufficient balance",
                )

            ticker = self._exchange.fetch_ticker(symbol)
            price = ticker.get("last") or ticker.get("close")
            if not price:
                return OrderResult(
                    success=False, order_id=None, symbol=symbol,
                    side=action, amount=0.0, price=None,
                    status="rejected", error="Could not fetch price",
                )

            trade_cost = balance * position_pct
            side = "buy" if action == "long" else "sell"

            # Set leverage for futures
            params = {}
            if self.leverage > 1 and ":" in symbol:  # futures symbol
                params["leverage"] = self.leverage
                self._exchange.set_leverage(self.leverage, symbol)

            # Standard ccxt market order
            order = self._exchange.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=trade_cost / price if side == "buy" else trade_cost / price,
                params=params,
            )

            logger.info(
                f"EXECUTED {side.upper()} {symbol} "
                f"@ ~{price:.2f} | cost={trade_cost:.2f} | "
                f"id={order.get('id', 'N/A')}"
            )

            return OrderResult(
                success=True, order_id=order.get("id"),
                symbol=symbol, side=side,
                amount=trade_cost / price if side == "buy" else 0,
                price=price, status=order.get("status", "unknown"),
                raw=order,
            )

        except Exception as e:
            logger.error(f"Execution failed: {e}")
            return OrderResult(
                success=False, order_id=None, symbol=symbol,
                side=action, amount=0.0, price=None,
                status="error", error=str(e),
            )

    def _get_balance(self, symbol: str) -> float:
        try:
            balance = self._exchange.fetch_balance()
            quote = symbol.split("/")[1].split(":")[0]  # "USDT" from "BTC/USDT" or "BTC/USDT:USDT"
            return float(balance.get(quote, {}).get("free", 0))
        except Exception as e:
            logger.error(f"Balance fetch failed: {e}")
            return 0.0

    def _close_position(self, symbol: str) -> OrderResult:
        """Close any open position on the symbol."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would close position on {symbol}")
            return OrderResult(
                success=True, order_id="dry_run", symbol=symbol,
                side="flat", amount=0.0, price=None, status="dry_run",
            )
        try:
            positions = self._exchange.fetch_positions([symbol])
            for pos in positions:
                contracts = float(pos.get("contracts", 0))
                if contracts != 0:
                    side = "sell" if contracts > 0 else "buy"
                    order = self._exchange.create_order(
                        symbol=symbol, type="market",
                        side=side, amount=abs(contracts),
                        params={"reduceOnly": True},
                    )
                    logger.info(f"CLOSED {symbol}: {side} {abs(contracts)}")
                    return OrderResult(
                        success=True, order_id=order.get("id"),
                        symbol=symbol, side=side,
                        amount=abs(contracts), price=None,
                        status="closed", raw=order,
                    )
            return OrderResult(
                success=True, order_id=None, symbol=symbol,
                side="flat", amount=0.0, price=None, status="no_position",
            )
        except Exception as e:
            logger.error(f"Close failed: {e}")
            return OrderResult(
                success=False, order_id=None, symbol=symbol,
                side="flat", amount=0.0, price=None,
                status="error", error=str(e),
            )
