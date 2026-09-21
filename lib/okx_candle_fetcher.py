"""
OKX Candle Fetcher – Reliable historical candle retrieval with pagination and cache control.
Usage:
    from okx_candle_fetcher import OKXCandleFetcher
    
    fetcher = OKXCandleFetcher(cache_enabled=False)
    df = fetcher.fetch_candles(
        symbol='BTC/USDT',
        timeframe='1m',
        num_candles=20160,      # 14 days of 1-minute candles
        cache_key='btc_1m_14d'  # optional, for caching
    )
"""

import ccxt
import pandas as pd
import time
import os
import json
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OKXCandleFetcher:
    """
    Fetches OHLCV candles from OKX with robust pagination and optional caching.
    
    Features:
    - Guarantees to return exactly `num_candles` candles (or as many as available).
    - Handles OKX's 100‑candle limit per request with automatic pagination.
    - Respects rate limits (no aggressive bursting).
    - Optional persistent caching with expiry.
    - Can bypass cache or force fresh fetch.
    """
    
    def __init__(self, paper_trading=False, api_key='', secret='', password='',
                 cache_enabled=True, cache_dir=None):
        """
        Args:
            paper_trading: Use OKX sandbox (default False).
            api_key, secret, password: OKX API credentials (optional for public OHLCV).
            cache_enabled: Enable local CSV caching (default True).
            cache_dir: Directory for cache files (default: ~/.openclaw/ipcra_ws/trading_system/data/historical).
        """
        self.exchange = ccxt.okx({
            'apiKey': api_key,
            'secret': secret,
            'password': password,
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        if paper_trading:
            self.exchange.set_sandbox_mode(True)
        
        self.cache_enabled = cache_enabled
        if cache_dir is None:
            cache_dir = os.path.join(
                os.path.dirname(__file__),
                '..', '..', 'trading_system', 'data', 'historical'
            )
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def _cache_path(self, symbol, timeframe, cache_key=None):
        """Generate cache file path."""
        safe_symbol = symbol.replace('/', '_')
        if cache_key:
            filename = f"okx_{safe_symbol}_{timeframe}_{cache_key}.csv"
        else:
            filename = f"okx_{safe_symbol}_{timeframe}.csv"
        return os.path.join(self.cache_dir, filename)
    
    def _fetch_raw_chunk(self, symbol, timeframe, since=None, limit=100):
        """
        Fetch a single chunk of raw OHLCV candles from OKX.
        Returns list of [timestamp, open, high, low, close, volume] or empty list.
        """
        try:
            candles = self.exchange.fetch_ohlcv(
                symbol, timeframe, since=since, limit=limit
            )
            return candles
        except Exception as e:
            logger.error(f"Error fetching {symbol} {timeframe} since {since}: {e}")
            return []
    
    def _paginated_fetch(self, symbol, timeframe, num_candles, start_timestamp=None):
        """
        Fetch `num_candles` candles by paginating through OKX's API.
        If `start_timestamp` is None, fetches the most recent `num_candles`.
        Returns list of candles sorted ascending by timestamp.
        """
        all_candles = []
        limit_per_request = 100  # OKX max
        since = start_timestamp
        
        # If no start timestamp, we need to fetch newest first, then walk backwards.
        # OKX returns candles from oldest to newest, so we need to estimate a start.
        if since is None:
            # Fetch the most recent chunk to get the latest timestamp
            recent = self._fetch_raw_chunk(symbol, timeframe, limit=limit_per_request)
            if not recent:
                return []
            newest_timestamp = recent[-1][0]
            # Compute start timestamp to get `num_candles` candles
            tf_ms = ccxt.Exchange.parse_timeframe(timeframe) * 1000
            since = newest_timestamp - (num_candles * tf_ms)
        
        # Now fetch forward from `since`
        while len(all_candles) < num_candles:
            chunk = self._fetch_raw_chunk(symbol, timeframe, since=since, limit=limit_per_request)
            if not chunk:
                break
            all_candles.extend(chunk)
            since = chunk[-1][0] + 1  # next millisecond after last candle
            time.sleep(self.exchange.rateLimit / 1000)  # respect rate limit
        
        # Trim to exactly num_candles (most recent)
        if len(all_candles) > num_candles:
            all_candles = all_candles[-num_candles:]
        
        return all_candles
    
    def fetch_candles(self, symbol, timeframe, num_candles, cache_key=None, force_fresh=False):
        """
        Fetch candles, using cache unless `force_fresh` is True.
        
        Args:
            symbol: Trading pair, e.g., 'BTC/USDT'.
            timeframe: CCXT timeframe string, e.g., '1m', '5m', '1h', '1d'.
            num_candles: Number of candles to return.
            cache_key: Optional identifier for this specific dataset (e.g., '14d_1m').
                       If provided, cache file will include this key.
            force_fresh: Ignore cache and fetch fresh from exchange.
        
        Returns:
            pandas DataFrame with columns ['open','high','low','close','volume'],
            index = datetime (UTC).
        """
        cache_path = self._cache_path(symbol, timeframe, cache_key)
        
        # 1. Try cache (if enabled and not forced)
        if self.cache_enabled and not force_fresh and os.path.exists(cache_path):
            try:
                df = pd.read_csv(cache_path, parse_dates=['timestamp'], index_col='timestamp')
                if len(df) >= num_candles:
                    logger.info(f"Serving {len(df)} cached candles from {cache_path}")
                    return df.tail(num_candles).copy()
                else:
                    logger.info(f"Cache has only {len(df)} candles, need {num_candles}. Fetching fresh.")
            except Exception as e:
                logger.warning(f"Cache read failed: {e}. Fetching fresh.")
        
        # 2. Fetch from exchange
        logger.info(f"Fetching {num_candles} {timeframe} candles for {symbol} from OKX...")
        raw = self._paginated_fetch(symbol, timeframe, num_candles)
        if not raw:
            raise RuntimeError(f"No candles returned from OKX for {symbol} {timeframe}")
        
        df = pd.DataFrame(raw, columns=['timestamp','open','high','low','close','volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        # 3. Write to cache (if enabled)
        if self.cache_enabled:
            try:
                df.to_csv(cache_path)
                logger.info(f"Cached {len(df)} candles to {cache_path}")
            except Exception as e:
                logger.warning(f"Could not write cache: {e}")
        
        # 4. Ensure we have the requested number of candles
        if len(df) < num_candles:
            logger.warning(f"Only {len(df)} candles available, requested {num_candles}.")
        
        return df.tail(num_candles).copy()
    
    def clear_cache(self, symbol=None, timeframe=None, cache_key=None):
        """
        Delete cache file(s).
        If symbol and timeframe are None, delete all cache files in cache_dir.
        """
        if symbol is None and timeframe is None:
            files = os.listdir(self.cache_dir)
            for f in files:
                if f.startswith('okx_'):
                    os.remove(os.path.join(self.cache_dir, f))
            logger.info(f"Cleared all OKX cache files in {self.cache_dir}")
            return
        
        path = self._cache_path(symbol, timeframe, cache_key)
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Removed cache file {path}")


# Convenience function for quick usage
def fetch_okx_candles(symbol, timeframe, num_candles, cache_enabled=True, force_fresh=False, **kwargs):
    """
    One‑line helper to fetch candles.
    Example:
        df = fetch_okx_candles('BTC/USDT', '1m', 10080, cache_enabled=False)
    """
    fetcher = OKXCandleFetcher(cache_enabled=cache_enabled, **kwargs)
    return fetcher.fetch_candles(symbol, timeframe, num_candles, force_fresh=force_fresh)