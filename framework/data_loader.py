"""
Module 1 — Data Retriever (FIXED)

Fetches OHLCV candles from online exchanges (OKX priority) with chunking
for long periods. Caches locally and integrates previously saved data.

Input:  symbol, exchange, date range (start/end), timeframe, extra fields
Output: (file_path, num_candles)

OKX limits: ~300 candles per request. We paginate to cover any period.
"""

import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Tuple, List

import ccxt
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "data_cache"
OKX_MAX_CANDLES = 300


class DataLoader:
    """Unified data loader with OKX support, local caching, and chunked fetch."""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._exchange_cache = {}

    def _get_exchange(self, source: str):
        source_lower = source.lower()
        if source_lower not in self._exchange_cache:
            if source_lower == "okx":
                ex = ccxt.okx({"enableRateLimit": True})
            else:
                raise ValueError(
                    f"Unsupported exchange: {source}. Currently supported: OKX"
                )
            self._exchange_cache[source_lower] = ex
        return self._exchange_cache[source_lower]

    def _cache_path(
        self, symbol: str, source: str, timeframe: str,
        start: datetime, end: datetime,
    ) -> Path:
        safe_symbol = symbol.replace("/", "_")
        s_str = start.strftime("%Y%m%d")
        e_str = end.strftime("%Y%m%d")
        fname = f"{source}_{safe_symbol}_{timeframe}_{s_str}_{e_str}.csv"
        return self.cache_dir / fname

    def load_cached(self, file_path: Path) -> Optional[pd.DataFrame]:
        if not file_path.exists():
            return None
        try:
            df = pd.read_csv(file_path, parse_dates=["timestamp"], index_col="timestamp")
            if df.empty:
                return None
            logger.info(f"Loaded cached: {file_path} ({len(df)} rows)")
            return df
        except Exception as e:
            logger.warning(f"Corrupt cache {file_path}: {e}")
            return None

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        source: str = "okx",
        extra_fields: Optional[List[str]] = None,
        force_refresh: bool = False,
    ) -> Tuple[str, int]:
        """
        Fetch OHLCV candles, merging with local cache.

        Returns: (file_path, num_candles)
        """
        extra_fields = extra_fields or []
        cache_path = self._cache_path(symbol, source, timeframe, start, end)

        # ── Cache hit ─────────────────────────────────────────────
        if not force_refresh:
            cached = self.load_cached(cache_path)
            if cached is not None:
                c_start = cached.index.min().to_pydatetime()
                c_end = cached.index.max().to_pydatetime()
                if c_start <= start and c_end >= end:
                    logger.info(f"Cache fully covers [{start}, {end}]")
                    return str(cache_path), len(cached)

        # ── Fetch from exchange ───────────────────────────────────
        exchange = self._get_exchange(source)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        since_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        all_candles: List[List] = []
        current_since = since_ms

        logger.info(f"Fetching {symbol} {timeframe} from {source} [{start} → {end}]")
        while current_since < end_ms:
            try:
                batch = exchange.fetch_ohlcv(
                    symbol, timeframe, since=current_since, limit=OKX_MAX_CANDLES
                )
            except Exception as e:
                logger.error(f"Fetch error at since={current_since}: {e}")
                break

            if not batch:
                break

            all_candles.extend(batch)
            last_ts = batch[-1][0]
            if last_ts <= current_since:
                logger.warning("Stale data, breaking pagination")
                break
            current_since = last_ts + 1
            logger.debug(f"  Chunk: {len(batch)} candles, total: {len(all_candles)}")

        if not all_candles:
            raise RuntimeError(
                f"No data from {source} for {symbol} {timeframe} in [{start}, {end}]"
            )

        # ── Build DataFrame ──────────────────────────────────────
        df = pd.DataFrame(
            all_candles,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        df = df[~df.index.duplicated(keep="last")]

        for field in extra_fields:
            if field not in df.columns:
                df[field] = None

        # ── Merge with existing cache ────────────────────────────
        existing = self.load_cached(cache_path) if cache_path.exists() else None
        if existing is not None:
            combined = pd.concat([existing, df])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined.sort_index(inplace=True)
            df = combined

        df = df[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]
        df.to_csv(cache_path)
        logger.info(f"Saved {len(df)} candles → {cache_path}")

        return str(cache_path), len(df)


# ─── Convenience ─────────────────────────────────────────────────────

def load_candles(
    symbol: str,
    timeframe: str = "5m",
    start: str = "2025-01-01",
    end: str = "2025-06-01",
    source: str = "okx",
    force_refresh: bool = False,
    cache_dir: Optional[str] = None,
) -> Tuple[pd.DataFrame, str, int]:
    """
    High-level helper: (dataframe, file_path, num_candles).
    start/end as YYYY-MM-DD strings. Symbol is REQUIRED (no default).
    """
    start_dt = pd.Timestamp(start).to_pydatetime()
    end_dt = pd.Timestamp(end).to_pydatetime()
    loader = DataLoader(cache_dir=cache_dir)
    path, count = loader.fetch_candles(
        symbol=symbol, timeframe=timeframe,
        start=start_dt, end=end_dt,
        source=source, force_refresh=force_refresh,
    )
    df = pd.read_csv(path, parse_dates=["timestamp"], index_col="timestamp")
    return df, path, count
