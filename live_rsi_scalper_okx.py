#!/usr/bin/env python3
"""
ZioClaw RSI Scalper Pro v3.1 — OKX futures, bidirectional.
Rebuilt 2026-09-14 from log-evidenced v2 spec after source loss:
  ETH/USDT:USDT | 15m | RSI14 [30/70] | SL 2% | TP 3% | 20% equity | 3x
Syncs any existing exchange position on boot (protects orphaned positions).
v3.1 (2026-09-20, JP-approved): equity = OKX totalEq (was: cash USDT only,
under-reported ~50%); sizing in CONTRACTS via contractSize (was: ETH amount
lot-clamped to ~8% of intended size).
"""
import os
import sys
import time
import logging
import signal

import ccxt
from dotenv import load_dotenv
import pandas as pd

load_dotenv('/home/node/.openclaw/ipcra_ws/.env')
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env.root'))

SYMBOL = 'ETH/USDT:USDT'
TIMEFRAME = '15m'
RSI_PERIOD = 14
RSI_OVERSOLD = 30.0
RSI_OVERBOUGHT = 70.0
STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.03
POSITION_SIZE_PCT = 0.20
LEVERAGE = 3
CANDLE_LIMIT = 300
SLEEP_SECONDS = 60
MIN_EQUITY_WARN = 50.0

LOG_DIR = '/home/node/.openclaw/ipcra_ws/1_Projects/crypto_trading_bots/logs'
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'live_rsi_scalper_okx.log')),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger('scalper')


def rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-12)
    return 100 - 100 / (1 + rs)


def build_exchange() -> ccxt.okx:
    ex = ccxt.okx({
        'apiKey': os.getenv('OKX_API_KEY'),
        'secret': os.getenv('OKX_API_SECRET'),
        'password': os.getenv('OKX_API_PASSPHRASE'),
        'enableRateLimit': True,
    })
    ex.load_markets()
    try:
        ex.set_leverage(LEVERAGE, ex.market(SYMBOL)['id'])
        log.info(f'Leverage: {LEVERAGE}x')
    except Exception as e:
        log.warning(f'set_leverage: {e}')
    return ex


def fetch_candles(ex) -> pd.DataFrame:
    o = ex.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=CANDLE_LIMIT)
    df = pd.DataFrame(o, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df['rsi'] = rsi(df['close'])
    return df


def get_position(ex) -> dict:
    """Return {'side': 'long'|'short'|'flat', 'contracts': float, 'entry': float}."""
    pos = ex.fetch_positions([SYMBOL])
    for p in pos:
        contracts = p.get('contracts') or 0
        if contracts and contracts > 0:
            return {'side': p.get('side'), 'contracts': contracts,
                    'entry': p.get('entryPrice') or 0.0}
    return {'side': 'flat', 'contracts': 0.0, 'entry': 0.0}


def get_equity(ex) -> float:
    """True account equity: OKX totalEq in USD (matches the app view)."""
    bal = ex.fetch_balance()
    data = ((bal.get('info') or {}).get('data')) or []
    total_eq = data[0].get('totalEq') if data else None
    if total_eq:
        return float(total_eq)
    usdt = (bal.get('total') or {}).get('USDT') or 0.0
    return float(usdt)


def position_size(ex, equity: float, price: float) -> float:
    """Position size in CONTRACTS (ccxt swap `amount` = contracts, not ETH)."""
    usdt_spend = equity * POSITION_SIZE_PCT
    base_amount = (usdt_spend * LEVERAGE) / price           # size in ETH
    mkt = ex.market(SYMBOL)
    contract_size = float(mkt.get('contractSize') or 0.1)
    contracts = base_amount / contract_size
    contracts = float(ex.amount_to_precision(SYMBOL, contracts))
    min_amt = float(((mkt.get('limits') or {}).get('amount') or {}).get('min') or 0.0)
    if contracts <= 0 or contracts < min_amt:
        return 0.0
    return contracts


def close_position(ex, pos: dict, reason: str):
    try:
        side = 'sell' if pos['side'] == 'long' else 'buy'
        ex.create_order(SYMBOL, 'market', side, pos['contracts'], params={'reduceOnly': True})
        log.info(f'CLOSED {pos["side"]} ({reason})')
    except Exception as e:
        log.error(f'close_position failed: {e}')


def open_position(ex, side: str, equity: float, price: float):
    amount = position_size(ex, equity, price)
    if amount <= 0:
        log.warning('Position size zero, cannot open')
        return
    try:
        ex.create_order(SYMBOL, 'market', 'buy' if side == 'long' else 'sell', amount)
        ctv = ex.market(SYMBOL).get('contractSize') or 0.1
        log.info(f'OPENED {side} {amount} contracts (~{amount * ctv:.4f} ETH) @ ~{price}')
    except Exception as e:
        log.error(f'open_position failed: {e}')


def check_exit(pos: dict, price: float) -> str | None:
    entry = pos['entry']
    if not entry:
        return None
    if pos['side'] == 'long':
        pnl = (price - entry) / entry
        if pnl <= -STOP_LOSS_PCT:
            return 'stop-loss'
        if pnl >= TAKE_PROFIT_PCT:
            return 'take-profit'
    elif pos['side'] == 'short':
        pnl = (entry - price) / entry
        if pnl <= -STOP_LOSS_PCT:
            return 'stop-loss'
        if pnl >= TAKE_PROFIT_PCT:
            return 'take-profit'
    return None


_running = True
def _stop(signum, frame):
    global _running
    _running = False
    log.info(f'Received signal {signum}, shutting down gracefully...')


def main():
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info('=' * 60)
    log.info('ZioClaw RSI Scalper Pro v3.1 — Starting')
    log.info(f'{SYMBOL} | {TIMEFRAME} | RSI{RSI_PERIOD}[{RSI_OVERSOLD:.0f}/{RSI_OVERBOUGHT:.0f}]')
    log.info(f'SL:{STOP_LOSS_PCT*100:.0f}% TP:{TAKE_PROFIT_PCT*100:.0f}% | {POSITION_SIZE_PCT*100:.0f}% equity | {LEVERAGE}x')
    log.info('=' * 60)

    ex = build_exchange()
    df = fetch_candles(ex)
    log.info(f'Initial data: {len(df)} candles, last={pd.to_datetime(df["ts"].iloc[-1], unit="ms", utc=True)}')

    pos = get_position(ex)
    if pos['side'] != 'flat':
        log.info(f'Existing {pos["side"]} position synced: {pos["contracts"]} @ {pos["entry"]}')
    equity = get_equity(ex)
    if equity < MIN_EQUITY_WARN:
        log.warning(f'Low equity (${equity:.2f} < ${MIN_EQUITY_WARN:.0f}) — trades may fail')

    prev_rsi = df['rsi'].iloc[-2]
    while _running:
        try:
            df = fetch_candles(ex)
            price = float(df['close'].iloc[-1])
            r = float(df['rsi'].iloc[-1])
            prev_rsi = float(df['rsi'].iloc[-2])
            pos = get_position(ex)
            equity = get_equity(ex)

            pnl_pct = ''
            if pos['side'] != 'flat' and pos['entry']:
                raw = (price - pos['entry']) / pos['entry']
                pnl_pct = (raw if pos['side'] == 'long' else -raw) * LEVERAGE * 100
                pnl_pct = f' | PnL={pnl_pct:+.2f}%'

            # Exit management first
            if pos['side'] != 'flat':
                reason = check_exit(pos, price)
                if reason:
                    log.info(f'{reason.upper()} triggered: PnL {pnl_pct}')
                    close_position(ex, pos, reason)
                    pos = {'side': 'flat', 'contracts': 0.0, 'entry': 0.0}

            # RSI crossovers (use completed candle vs previous)
            crossed_up = prev_rsi is not None and prev_rsi < RSI_OVERSOLD <= r
            crossed_down = prev_rsi is not None and prev_rsi > RSI_OVERBOUGHT >= r

            if pos['side'] == 'flat':
                if crossed_up:
                    log.info(f'SIGNAL: RSI crossed up {RSI_OVERSOLD:.0f} ({prev_rsi:.1f}->{r:.1f}) — LONG')
                    open_position(ex, 'long', equity, price)
                elif crossed_down:
                    log.info(f'SIGNAL: RSI crossed down {RSI_OVERBOUGHT:.0f} ({prev_rsi:.1f}->{r:.1f}) — SHORT')
                    open_position(ex, 'short', equity, price)

            pos = get_position(ex)
            log.info(f'ETH=${price:.0f} | RSI={r:.1f} | {pos["side"]} | Eq=${equity:.2f}{pnl_pct}')

            for _ in range(SLEEP_SECONDS):
                if not _running:
                    break
                time.sleep(1)
        except Exception as e:
            log.error(f'loop: {e}')
            time.sleep(30)

    log.info('Trading script stopped.')


if __name__ == '__main__':
    main()
