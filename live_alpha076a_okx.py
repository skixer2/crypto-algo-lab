#!/usr/bin/env python3
"""
LIVE alpha_076a runner — OKX ETH-USDT-SWAP, 1x, long-only (Machine A).

Deployment class: LIVE DATA COLLECTION (operator override 2026-10-25, ledger
d40ad8b) — NOT an approved deployable. Goal: fills-vs-model, funding paid,
decision-vs-fill timing, real DD.

Formula-faithful by construction:
  - signal: models/alpha_formulas/alpha_076a.calculate_math_signal (imported)
  - funding gate: binance settled rates, 30d rolling pctl-rank (tuner spec)
  - decide @ closed 15m bar -> market fill at next bar open
  - size: full equity notional @ 1x (JP 2026-10-08 venue rule)
Kill criteria (pre-registered): equity -30% vs switch baseline, or JP's word.
"""
import json
import os
import sys
import time
import logging
import signal as sigmod
from datetime import datetime, timezone

import ccxt
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models.alpha_formulas import alpha_076a as A76  # noqa: E402

load_dotenv('/home/node/.openclaw/ipcra_ws/.env')
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env.root'))

SYMBOL = 'ETH/USDT:USDT'
BAR = '15m'
STATE_DIR = 'data/live_076a'
JOURNAL = os.path.join(STATE_DIR, 'journal.jsonl')
HALT = os.path.join(STATE_DIR, 'HALT')
BASELINE_FILE = os.path.join(STATE_DIR, 'baseline.json')
KILL_DD = 0.30            # pre-registered: -30% equity vs baseline -> flatten + halt
FUND_WIN, FUND_MP = 96 * 30, 96 * 7   # 30d window / 7d min_periods (engine spec)
WARMUP_BARS = 3000        # covers channel(192)+ATR(96)+rank window(2880)

os.makedirs(STATE_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(os.path.join(STATE_DIR, 'runner.log')),
              logging.StreamHandler()])
log = logging.getLogger('live076a')


def now_utc():
    return datetime.now(timezone.utc)


def jlog(evt: dict):
    evt['ts'] = now_utc().isoformat()
    with open(JOURNAL, 'a') as f:
        f.write(json.dumps(evt) + '\n')


def pct_rank_series(rate_15m: pd.Series) -> pd.Series:
    """Engine gate: 30d rolling pctl-rank, window-before-current, count-le."""
    def _pct_rank(w: np.ndarray) -> float:
        return float((w[:-1] <= w[-1]).mean())
    return rate_15m.rolling(FUND_WIN, min_periods=FUND_MP).apply(_pct_rank, raw=True)


def fetch_binance_funding() -> pd.Series:
    """Binance settled funding rates, stamped at settle time, floored 8h."""
    out = []
    for _ in range(4):  # ~4 pages of 1000 = 100+ days of 8h settles
        u = 'https://fapi.binance.com/fapi/v1/fundingRate?symbol=ETHUSDT&limit=1000'
        if out:
            u += f'&startTime={int(out[0][0].timestamp() * 1000)}'
        r = requests.get(u, timeout=20)
        r.raise_for_status()
        page = [(pd.Timestamp(x['fundingTime'], unit='ms', tz='UTC').floor('8h'),
                 float(x['fundingRate'])) for x in r.json()]
        if not page:
            break
        if out and page[-1][0] >= out[0][0]:
            break
        out = page + out
    s = pd.Series({t: v for t, v in out}).sort_index()
    return s[~s.index.duplicated(keep='last')]


def build_frame(ohlcv, funding: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df = df.set_index('timestamp')
    # settle publication margin: a settle at T is usable by decisions at bars
    # whose CLOSE is > T (shift the rate one extra 15m bar after ffill)
    rate = funding.reindex(df.index, method='ffill').shift(1)
    df['fund_pct'] = pct_rank_series(rate)
    return df


class Runner:
    def __init__(self):
        self.ex = ccxt.okx({
            'apiKey': os.environ['OKX_API_KEY'],
            'secret': os.environ['OKX_API_SECRET'],
            'password': os.environ['OKX_API_PASSPHRASE']})
        self.ex.load_markets()
        self.market = self.ex.market(SYMBOL)
        self.bars_path = os.path.join(STATE_DIR, 'bars.csv')
        self.fund_path = os.path.join(STATE_DIR, 'funding.csv')
        self.target = 0.0
        self.position_contracts = 0.0
        self.baseline = None
        self.running = True

    # ---------- data ----------
    def load_or_fetch_bars(self):
        t0 = int((now_utc().timestamp() - WARMUP_BARS * 900 - 3600) * 1000)
        ohlcv = []
        while t0 < now_utc().timestamp() * 1000:
            batch = self.ex.fetch_ohlcv(SYMBOL, BAR, since=t0, limit=300)
            if not batch:
                break
            ohlcv += batch
            t0 = batch[-1][0] + 900_000
            if len(batch) < 300:
                break
            time.sleep(0.15)
        return ohlcv

    def load_or_fetch_funding(self):
        try:
            return fetch_binance_funding()
        except Exception as e:
            log.warning(f"binance funding fetch failed ({e}); trying cached")
            if os.path.exists(self.fund_path):
                c = pd.read_csv(self.fund_path, index_col=0, parse_dates=True)
                return c.iloc[:, 0]
            raise

    # ---------- account ----------
    def equity(self):
        bal = self.ex.fetch_balance()
        return float(bal['info']['data'][0]['totalEq'])

    def current_contracts(self):
        for p in self.ex.fetch_positions([SYMBOL]):
            if abs(float(p.get('contracts') or 0)) > 0:
                self.position_contracts = float(p['contracts'])
                return float(p['contracts'])
        self.position_contracts = 0.0
        return 0.0

    def contracts_for(self, notional, price):
        cs = float(self.market['contractSize'] or 1)
        return int((notional / price) / cs)

    def trade_to(self, target_contracts, why):
        cur = self.current_contracts()
        delta = target_contracts - cur
        if abs(delta) < 1:
            return
        side = 'buy' if delta > 0 else 'sell'
        o = self.ex.create_order(SYMBOL, 'market', side, abs(delta), params={'tdMode': 'cross'})
        px = self.ex.fetch_order(o['id'], SYMBOL).get('average') or o.get('average')
        jlog({'evt': 'fill', 'why': why, 'side': side, 'contracts': abs(delta),
              'px': px, 'target': target_contracts})
        log.info(f"TRADE {side} {abs(delta)} contracts @~{px} ({why})")

    # ---------- core ----------
    def decide(self, df):
        sig = A76.calculate_math_signal(df)
        return float(sig.iloc[-1])   # +1 long / -1 flat (long-only formula)

    def sync_once(self):
        df = build_frame(self.load_or_fetch_bars(), self.load_or_fetch_funding())
        df.to_csv(self.bars_path)
        t = self.decide(df)
        eq = self.equity()
        px = df['close'].iloc[-1]
        if self.baseline is None:
            self.baseline = eq
            json.dump({'baseline_eq': eq, 'ts': now_utc().isoformat()},
                      open(BASELINE_FILE, 'w'))
        # kill check
        if eq < self.baseline * (1 - KILL_DD):
            self.trade_to(0, 'KILL_DD')
            open(HALT, 'w').write(f'kill dd {now_utc().isoformat()} eq {eq}')
            jlog({'evt': 'KILL', 'eq': eq, 'baseline': self.baseline})
            self.running = False
            return
        # position sync
        want = self.contracts_for(eq, px) if t > 0 else 0
        cur = self.current_contracts()
        if want != cur:
            self.trade_to(want, f'target {t:+.0f}')
        self.target = t
        jlog({'evt': 'bar', 'bar': str(df.index[-1]), 'close': px,
              'sig': t, 'pos': self.current_contracts(), 'eq': eq,
              'fund_pct': round(float(df['fund_pct'].iloc[-1]), 4)
              if pd.notna(df['fund_pct'].iloc[-1]) else None,
              'baseline': round(self.baseline, 2)})
        log.info(f"bar {df.index[-1]} close {px:.1f} sig {t:+.0f} pos "
                 f"{self.position_contracts} eq {eq:.2f}")

    def run(self):
        log.info("live076a starting (Machine A, 1x, live data collection)")
        last_bar = None
        while self.running and not os.path.exists(HALT):
            try:
                ohlcv = self.ex.fetch_ohlcv(SYMBOL, BAR, limit=3)
                last_closed = pd.Timestamp(ohlcv[-2][0], unit='ms', tz='UTC')
                if last_closed != last_bar and now_utc() >= last_closed + pd.Timedelta(minutes=15, seconds=5):
                    last_bar = last_closed
                    self.sync_once()
                time.sleep(30)
            except KeyboardInterrupt:
                break
            except Exception as e:
                log.error(f"cycle error: {type(e).__name__} {e}")
                time.sleep(60)
        log.info("live076a stopped")


if __name__ == '__main__':
    if '--validate' in sys.argv:
        # offline equivalence: runner frame+signal vs stored engine curve
        cache = 'framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv'
        c = pd.read_csv(cache)
        c.columns = [x.lower() for x in c.columns]
        c['timestamp'] = pd.to_datetime(c['timestamp'], utc=True)
        c = c.set_index('timestamp')
        from tuner.alpha_orchestrator import build_fund_pct
        fp = build_fund_pct(c.reset_index()[['timestamp', 'open', 'high', 'low', 'close']].set_index('timestamp'), 'binance', 'ETH/USDT')
        c['fund_pct'] = fp
        sig = A76.calculate_math_signal(c)
        pos_engine = pd.read_csv('data/precompute/alpha_076a.csv.gz')
        pos_engine['timestamp'] = pd.to_datetime(pos_engine['timestamp'], utc=True)
        m = pos_engine.set_index('timestamp')['position'].reindex(c.index).ffill()
        mine = (sig > 0).astype(float)
        overlap = m.dropna().index
        diff = (mine.loc[overlap] != m.loc[overlap]).sum()
        print(f"bars compared: {len(overlap)} | mismatches: {diff} "
              f"| match: {(1 - diff / len(overlap)) * 100:.3f}%")
        sys.exit(0 if diff == 0 else 1)
    r = Runner()
    r.run()
