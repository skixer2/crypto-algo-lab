#!/usr/bin/env python3
"""
Revolut X Crypto Exchange API client (ccxt-like interface).
"""
import os
import sys
import subprocess
import base64
import time
import json
from typing import Optional, Dict, List, Any
from decimal import Decimal

# Bootstrap missing packages
def ensure_package(package, pip_name=None):
    try:
        __import__(package)
    except ImportError:
        pip_name = pip_name or package
        print(f"Installing missing package {pip_name}...", file=sys.stderr)
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', pip_name])
        # Reload module
        globals()[package] = __import__(package)

# Ensure required packages
required = [
    ('requests', 'requests'),
    ('cryptography', 'cryptography'),
    ('nacl.signing', 'pynacl'),
    ('dotenv', 'python-dotenv'),
]
for module, pip_name in required:
    try:
        ensure_package(module, pip_name)
    except Exception as e:
        print(f"Failed to install {module}: {e}", file=sys.stderr)
        sys.exit(1)

import requests
import requests.exceptions
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import nacl.signing
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/home/node/.openclaw/workspace/.env')

class RevolutClient:
    """Client for Revolut X Crypto Exchange REST API."""
    
    def __init__(self, api_key=None, private_key_pem=None):
        """
        Initialize Revolut X client.
        
        Args:
            api_key: Your 64-character API key (optional, reads from REVOLUT_API_KEY)
            private_key_pem: Your private key in PEM format (optional, reads from REVOLUT_PRIVATE_ED25519)
        """
        self.api_key = api_key or os.getenv('REVOLUT_API_KEY')
        self.private_key_pem = private_key_pem or os.getenv('REVOLUT_PRIVATE_ED25519')
        
        if not self.api_key:
            raise ValueError("REVOLUT_API_KEY not set in environment")
        if not self.private_key_pem:
            raise ValueError("REVOLUT_PRIVATE_ED25519 not set in environment")
        
        # Base URL (server root)
        self.base_url = 'https://revx.revolut.com'
        self.api_prefix = '/api/1.0'
        
        # Prepare signing key
        self._signing_key = self._load_signing_key()
        
        # Session for connection reuse
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'OpenClaw/1.0',
            'Accept': 'application/json',
        })
        
        # Rate limit tracking
        self.last_request = 0
        
        # Time offset correction (ms) — computed once on init from a reliable time source
        self._time_offset_ms = self._compute_time_offset()
    
    def _compute_time_offset(self):
        """Compute local clock offset from reliable time sources (ms).
        Returns a positive offset if local clock is ahead (will be subtracted).
        Uses HTTP Date headers (Google/Cloudflare CDN edges are NTP-synced) as primary,
        with JSON time APIs as fallback. Cross-validates multiple sources to discard outliers."""
        import urllib.request as _ur
        import ssl as _ssl
        from datetime import datetime as _dt, timezone as _tz
        import email.utils as _email_utils
        ctx = _ssl.create_default_context()
        
        local_ms = int(time.time() * 1000)
        offsets = []
        
        # --- Tier 1: HTTP Date headers from major CDN edges (most reliable) ---
        http_sources = [
            'https://www.google.com',
            'https://www.microsoft.com',
            'https://www.apple.com',
        ]
        for url in http_sources:
            try:
                req = _ur.Request(url, method='HEAD')
                resp = _ur.urlopen(req, timeout=5, context=ctx)
                date_header = resp.getheader('Date')
                if date_header:
                    # Parse RFC 2822 date: "Mon, 29 Jun 2026 07:47:02 GMT"
                    parsed = _email_utils.parsedate_to_datetime(date_header)
                    server_ms = int(parsed.replace(tzinfo=_tz.utc).timestamp() * 1000)
                    offset = int(time.time() * 1000) - server_ms
                    offsets.append(offset)
            except Exception as e:
                print(f"[RevolutClient] HTTP time source {url}: {e}")
                continue
        
        # --- Tier 2: JSON time APIs (fallback) ---
        json_sources = [
            ('https://worldtimeapi.org/api/timezone/Etc/UTC', 'worldtimeapi'),
        ]
        for url, fmt in json_sources:
            try:
                req = _ur.Request(url)
                resp = _ur.urlopen(req, timeout=5, context=ctx)
                data = json.loads(resp.read())
                
                if fmt == 'timeapi_component':
                    dt = _dt(
                        data['year'], data['month'], data['day'],
                        data['hour'], data['minute'], data['seconds'],
                        data.get('milliSeconds', 0) * 1000
                    )
                    server_ms = int(dt.replace(tzinfo=_tz.utc).timestamp() * 1000)
                elif fmt == 'worldtimeapi':
                    if 'unixtime' in data:
                        server_ms = int(float(data['unixtime']) * 1000)
                    else:
                        continue
                else:
                    continue
                
                offset = int(time.time() * 1000) - server_ms
                offsets.append(offset)
            except Exception as e:
                print(f"[RevolutClient] JSON time source {url}: {e}")
                continue
        
        if not offsets:
            print(f"[RevolutClient] All time sources failed. Using local clock.")
            return 0
        
        # Cross-validate: discard outliers more than 5s from median
        if len(offsets) >= 2:
            sorted_offsets = sorted(offsets)
            median = sorted_offsets[len(sorted_offsets) // 2]
            filtered = [o for o in offsets if abs(o - median) < 5000]
            if filtered:
                offsets = filtered
        
        # Use minimum absolute offset when sources disagree wildly (median unreliable with 2)
        if len(offsets) >= 2:
            best_offset = min(offsets, key=abs)
        elif len(offsets) == 1:
            best_offset = offsets[0]
        else:
            return 0
        
        if abs(best_offset) > 500:
            print(f"[RevolutClient] Clock drift: {best_offset}ms (local {'ahead' if best_offset > 0 else 'behind'}), "
                  f"{len(offsets)} sources. Applying correction.")
            return best_offset
        print(f"[RevolutClient] Clock sync OK (offset: {best_offset}ms, {len(offsets)} sources)")
        return 0
    
    def _load_signing_key(self):
        """Load Ed25519 private key from base64-encoded DER."""
        der = base64.b64decode(self.private_key_pem)
        pk = serialization.load_der_private_key(der, None, default_backend())
        raw_private = pk.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        return nacl.signing.SigningKey(raw_private)
    
    def _sign_request(self, timestamp: str, method: str, path: str, query: str = '', body: str = ''):
        """Sign a request following Revolut X spec."""
        message = f"{timestamp}{method}{path}{query}{body}".encode()
        signed = self._signing_key.sign(message)
        return base64.b64encode(signed.signature).decode()
    
    def _request(self, method: str, path: str, params=None, data=None):
        """Make an authenticated request to the API with retries."""
        # Ensure path starts with /api
        if not path.startswith('/api'):
            path = self.api_prefix + path
        
        # Build full URL
        url = self.base_url + path
        
        # Prepare query string
        query = ''
        if params:
            from urllib.parse import urlencode
            query = urlencode(params, safe=':')
            url += '?' + query
        
        # Prepare body
        body = ''
        if data:
            body = json.dumps(data, separators=(',', ':'))
        
        # Timestamp in milliseconds (corrected for clock drift)
        timestamp = str(int(time.time() * 1000) - self._time_offset_ms)
        
        # Sign (use the exact path we're sending, including /api/1.0)
        signature = self._sign_request(timestamp, method.upper(), path, query, body)
        
        # Headers
        headers = {
            'X-Revx-API-Key': self.api_key,
            'X-Revx-Timestamp': timestamp,
            'X-Revx-Signature': signature,
        }
        
        # Retry configuration
        max_retries = 4
        retry_delay = 2  # seconds
        last_exception = None
        timestamp_adjustment = 0  # additional ms to subtract on 409 retries
        
        for attempt in range(max_retries):
            try:
                # Recompute timestamp on each retry (with accumulated adjustment)
                if attempt > 0 or timestamp_adjustment != 0:
                    new_ts = str(int(time.time() * 1000) - self._time_offset_ms - timestamp_adjustment)
                    signature = self._sign_request(new_ts, method.upper(), path, query, body)
                    headers['X-Revx-Timestamp'] = new_ts
                    headers['X-Revx-Signature'] = signature
                
                resp = self.session.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    data=body if method.upper() != 'GET' else None,
                    params=None,  # already in URL
                    timeout=30
                )
                
                # Rate limit
                self.last_request = time.time()
                
                # Handle response
                if resp.status_code == 429:
                    # Rate limit exceeded
                    wait = int(resp.headers.get('Retry-After', retry_delay * (2 ** attempt)))
                    print(f"Rate limited, waiting {wait} seconds...")
                    time.sleep(wait)
                    continue
                elif resp.status_code == 409:
                    # Timestamp issue — adjust and retry
                    try:
                        err = resp.json()
                        msg = err.get('message', '')
                    except:
                        msg = ''
                    if 'timestamp' in msg.lower() and attempt < max_retries - 1:
                        # Subtract 2s more on each retry (Revolut tolerance is ~30s)
                        timestamp_adjustment += 2000 + (attempt * 1000)
                        print(f"[RevolutClient] Timestamp rejected, retrying with -{timestamp_adjustment}ms adjustment...")
                        time.sleep(0.5)
                        continue
                    raise Exception(f"API error 409: {msg}")
                elif resp.status_code >= 500:
                    # Server error, retry after delay
                    print(f"Server error {resp.status_code}, retrying...")
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
                elif resp.status_code != 200:
                    # Client error, no retry
                    try:
                        error_data = resp.json()
                        raise Exception(f"API error {resp.status_code}: {error_data.get('message', 'Unknown error')}")
                    except:
                        raise Exception(f"API error {resp.status_code}: {resp.text[:200]}")
                
                return resp.json()
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                print(f"Request failed (attempt {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                continue
        
        # If all retries exhausted
        raise Exception(f"Request failed after {max_retries} attempts: {last_exception}")
    
    # Public API methods (ccxt-like)
    
    def fetch_balance(self, params=None):
        """
        Fetch account balances.
        
        Returns:
            ccxt-like balance dict with 'total', 'free', 'used' keys.
        """
        data = self._request('GET', '/balances', params=params)
        
        # Transform to ccxt format
        total = {}
        free = {}
        used = {}
        
        for item in data:
            currency = item['currency']
            available = Decimal(item['available'])
            reserved = Decimal(item['reserved'])
            total_bal = Decimal(item['total'])
            
            total[currency] = total_bal
            free[currency] = available
            used[currency] = reserved
        
        return {
            'total': total,
            'free': free,
            'used': used,
            'info': data,
            'timestamp': int(time.time() * 1000),
            'datetime': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ', time.gmtime())
        }
    
    def fetch_open_orders(self, symbol=None, since=None, limit=None, params=None):
        """
        Fetch open (active) orders.
        
        Args:
            symbol: Optional trading pair (e.g., 'BTC-USD')
            since: Not used in Revolut X
            limit: Max number of orders (default 100)
            params: Extra parameters
            
        Returns:
            List of order dicts in ccxt format.
        """
        params = params or {}
        if limit:
            params['limit'] = limit
        
        data = self._request('GET', '/orders/active', params=params)
        
        orders = []
        if isinstance(data, str):
            # API returned an error string, log and return empty list
            print(f"fetch_open_orders: API returned string: {data}")
            return orders
        
        # Extract list of orders from response dict
        if isinstance(data, dict) and 'data' in data:
            items = data['data']
        else:
            items = data
        
        for item in items:
            # Transform to ccxt format
            if isinstance(item, str):
                print(f"fetch_open_orders: item is string: {item}")
                continue
            order = {
                'id': item.get('venue_order_id', ''),
                'clientOrderId': item.get('client_order_id', ''),
                'symbol': item.get('symbol', '').replace('-', '/'),
                'type': 'limit',  # only limit supported for now
                'side': item.get('side', '').lower(),
                'amount': Decimal(item.get('base_size', '0')),
                'price': Decimal(item.get('price', '0')),
                'filled': Decimal(item.get('filled_size', '0')),
                'remaining': Decimal(item.get('remaining_size', '0')),
                'status': 'open',
                'timestamp': item.get('created_at_ms', 0),
                'datetime': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ', time.gmtime(item.get('created_at_ms', 0) / 1000)) if item.get('created_at_ms') else None,
                'info': item,
            }
            
            # Filter by symbol if provided
            if symbol and order['symbol'] != symbol.replace('/', '-'):
                continue
            
            orders.append(order)
        
        return orders
    
    def fetch_tickers(self, symbols=None, params=None):
        data = self._request('GET', '/tickers', params=params)
        items = data.get('data', data) if isinstance(data, dict) else data
        
        tickers = {}
        for item in items:
            if not isinstance(item, dict): continue
            symbol = item.get('symbol', '').replace('-', '/')
            if symbols and symbol not in symbols:
                continue
            
            tickers[symbol] = {
                'symbol': symbol,
                'last': float(item.get('last_price', '0')),
                'bid': float(item.get('bid', '0')),
                'ask': float(item.get('ask', '0')),
                'info': item,
            }
        
        return tickers
    
    def fetch_order_book(self, symbol, limit=None, params=None):
        """
        Fetch order book for a symbol.
        
        Args:
            symbol: Trading pair (e.g., 'BTC-USD')
            limit: Depth (default 20)
            params: Extra parameters
            
        Returns:
            Order book dict with 'bids' and 'asks'.
        """
        params = params or {}
        if limit:
            params['depth'] = limit
        
        data = self._request('GET', f'/order-book/{symbol.replace("/", "-")}', params=params)
        
        # Extract bids and asks from data['data']
        book_data = data.get('data', {})
        bids_raw = book_data.get('bids', [])
        asks_raw = book_data.get('asks', [])
        bids = [[Decimal(item['p']), Decimal(item['q'])] for item in bids_raw]
        asks = [[Decimal(item['p']), Decimal(item['q'])] for item in asks_raw]
        
        # Timestamp from metadata
        timestamp = data.get('metadata', {}).get('timestamp', 0)
        
        return {
            'bids': bids,
            'asks': asks,
            'symbol': symbol,
            'timestamp': timestamp,
            'datetime': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ', time.gmtime(timestamp / 1000)) if timestamp else None,
            'nonce': timestamp,
            'info': data,
        }
    def fetch_order_book_imbalance(self, symbol, limit=10):
        """
        Compute order-book imbalance for a symbol.
        
        OBI = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        
        Returns a float between -1 (all asks) and +1 (all bids).
        """
        book = self.fetch_order_book(symbol, limit=limit)
        bid_volume = sum(price * amount for price, amount in book['bids'])
        ask_volume = sum(price * amount for price, amount in book['asks'])
        total = bid_volume + ask_volume
        if total == 0:
            return 0.0
        return float((bid_volume - ask_volume) / total)
    def create_order(self, symbol, type, side, amount, price=None, params=None):
        """
        Place a new order.
        
        Args:
            symbol: Trading pair (e.g., 'BTC-USD')
            type: 'limit' (only limit supported)
            side: 'buy' or 'sell'
            amount: Base currency amount
            price: Limit price (required for limit orders)
            params: Extra parameters
            
        Returns:
            Order dict.
        """
        if type != 'limit':
            raise ValueError('Only limit orders are supported')
        if not price:
            raise ValueError('Price is required for limit orders')
        
        # Prepare order payload
        taker_allowed = params.get('taker_allowed', True) if params else True
        order_data = {
            'symbol': symbol.replace('/', '-'),
            'side': side.upper(),
            'order_configuration': {
                'limit': {
                    'base_size': str(amount),
                    'price': str(price),
                    'taker_allowed': taker_allowed,
                }
            }
        }
        
        # Add optional client_order_id if provided
        if params and 'client_order_id' in params:
            order_data['client_order_id'] = params['client_order_id']
        
        data = self._request('POST', '/orders', data=order_data)
        
        # Return order info
        return {
            'id': data.get('venue_order_id', ''),
            'clientOrderId': data.get('client_order_id', ''),
            'symbol': symbol,
            'type': type,
            'side': side,
            'amount': Decimal(amount),
            'price': Decimal(price),
            'filled': Decimal('0'),
            'remaining': Decimal(amount),
            'status': 'open',
            'timestamp': data.get('created_at_ms', 0),
            'datetime': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ', time.gmtime(data.get('created_at_ms', 0) / 1000)) if data.get('created_at_ms') else None,
            'info': data,
        }
    
    def cancel_order(self, order_id, symbol=None, params=None):
        """
        Cancel an order by ID.
        
        Args:
            order_id: Venue order ID
            symbol: Optional symbol (not used)
            params: Extra parameters
            
        Returns:
            Cancellation result.
        """
        data = self._request('DELETE', f'/orders/{order_id}', params=params)
        return {
            'id': order_id,
            'info': data,
            'status': 'canceled',
        }
    
    def fetch_currencies(self, params=None):
        """Fetch available currencies."""
        data = self._request('GET', '/configuration/currencies', params=params)
        return data
    
    def fetch_markets(self, params=None):
        """Fetch available trading pairs."""
        data = self._request('GET', '/configuration/pairs', params=params)
        
        markets = []
        for item in data:
            markets.append({
                'id': item.get('symbol', ''),
                'symbol': item.get('symbol', '').replace('-', '/'),
                'base': item.get('base_currency', ''),
                'quote': item.get('quote_currency', ''),
                'active': True,
                'precision': {
                    'amount': item.get('base_increment', '0.000001'),
                    'price': item.get('quote_increment', '0.01'),
                },
                'limits': {
                    'amount': {
                        'min': Decimal(item.get('base_min_size', '0')),
                        'max': Decimal(item.get('base_max_size', '1000000')),
                    },
                    'price': {
                        'min': Decimal(item.get('quote_min_price', '0')),
                        'max': Decimal(item.get('quote_max_price', '1000000')),
                    },
                    'cost': {
                        'min': Decimal(item.get('quote_min_size', '0')),
                        'max': Decimal(item.get('quote_max_size', '1000000')),
                    },
                },
                'info': item,
            })
        
        return markets


    def fetch_candles(self, symbol, interval, since=None, until=None, limit=1000):
        """
        Fetch historical OHLCV candles from Revolut X.
        
        Args:
            symbol: Trading pair (e.g., 'BTC-USD')
            interval: Candle interval in minutes (must be one of the allowed values: 1,5,15,30,60,240,1440,2880,5760,10080,20160,40320)
            since: Start timestamp in milliseconds (optional)
            until: End timestamp in milliseconds (optional)
            limit: Maximum number of candles to return (max 1000 per request)
        
        Returns:
            List of candles in ccxt format: [timestamp, open, high, low, close, volume]
        """
        # Convert symbol format
        rev_symbol = symbol.replace('/', '-')
        
        # Prepare query parameters
        params = {'interval': interval}
        if since is not None:
            params['since'] = since
        if until is not None:
            params['until'] = until
        
        # Revolut API max 1000 candles per request
        max_per_request = 1000
        limit = min(limit, max_per_request)
        
        data = self._request('GET', f'/candles/{rev_symbol}', params=params)
        candles = data.get('data', [])
        
        result = []
        for c in candles:
            result.append([
                c['start'],                     # timestamp (ms)
                float(c['open']),               # open
                float(c['high']),               # high
                float(c['low']),                # low
                float(c['close']),              # close
                float(c['volume']),             # volume
            ])
        return result

# Helper function to get a Revolut client instance
def get_revolut_client():
    """Factory function to create a RevolutClient instance."""
    return RevolutClient()


if __name__ == '__main__':
    # Quick test
    client = RevolutClient()
    print("Testing Revolut X connection...")
    
    # Test balance
    try:
        balance = client.fetch_balance()
        print(f"✅ Balance fetched: {len(balance['total'])} currencies")
        for currency, amount in balance['total'].items():
            if amount > 0:
                print(f"  {currency}: {amount}")
    except Exception as e:
        print(f"❌ Balance error: {e}")
    
    # Test tickers
    try:
        tickers = client.fetch_tickers()
        print(f"\n✅ Tickers fetched: {len(tickers)} symbols")
        for symbol in list(tickers.keys())[:3]:
            print(f"  {symbol}: {tickers[symbol]['last']}")
    except Exception as e:
        print(f"❌ Tickers error: {e}")
    
    # Test markets
    try:
        markets = client.fetch_markets()
        print(f"\n✅ Markets fetched: {len(markets)} pairs")
        for market in markets[:5]:
            print(f"  {market['symbol']}: {market['base']}/{market['quote']}")
    except Exception as e:
        print(f"❌ Markets error: {e}")