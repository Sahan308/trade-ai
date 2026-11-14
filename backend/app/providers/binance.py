"""Binance public market-data adapter (Spot + USDT-M Futures). Read-only, no API key.

Rate limits: Binance reports used request weight in X-MBX-USED-WEIGHT-1M. We stop calling well
before the documented per-minute limit, and honour Retry-After on 429/418.
"""
import re
import threading
import time
from datetime import datetime, timezone

import httpx

from ..services.candles import validate_klines
from .base import CandleSeries, FundingSnapshot, MarketType, ProviderError, Ticker

SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,15}USDT$")
BINANCE_INTERVALS = {"1m": "1m", "5m": "5m", "15m": "15m", "1H": "1h", "4H": "4h", "1D": "1d"}
SOURCES = {MarketType.spot: "Binance Spot", MarketType.futures: "Binance USDT-M Futures"}
# Documented per-minute IP weight limits; we use a safety margin below them.
WEIGHT_LIMITS = {MarketType.spot: 6000, MarketType.futures: 2400}
WEIGHT_SAFETY = 0.8


def _utc(ms: int | float) -> datetime:
    return datetime.fromtimestamp(float(ms) / 1000, tz=timezone.utc)


def normalize_symbol(symbol: str) -> str:
    s = re.sub(r"[^A-Z0-9]", "", symbol.upper())
    if not SYMBOL_RE.match(s):
        raise ProviderError("bad_request", f"Invalid symbol: {symbol}")
    return s


class BinanceProvider:
    id = "binance"

    def __init__(self, spot_base: str, futures_base: str, client: httpx.Client | None = None,
                 timeout: float = 8.0, cache_ttl: dict[str, float] | None = None):
        self.bases = {MarketType.spot: spot_base.rstrip("/"), MarketType.futures: futures_base.rstrip("/")}
        self.client = client or httpx.Client(timeout=timeout, headers={"User-Agent": "TRADE-AI/0.2 (read-only)"})
        self.cache_ttl = cache_ttl or {"candles": 10.0, "ticker": 5.0, "funding": 5.0}
        self._cache: dict[tuple, tuple[float, object]] = {}
        self._lock = threading.Lock()
        self._weight = {m: 0 for m in MarketType}
        self._weight_minute = {m: 0 for m in MarketType}
        self._blocked_until = {m: 0.0 for m in MarketType}

    def close(self) -> None:
        self.client.close()

    # ---------------- HTTP ----------------
    def _get(self, market: MarketType, path: str, params: dict) -> object:
        now = time.time()
        minute = int(now // 60)
        with self._lock:
            if now < self._blocked_until[market]:
                raise ProviderError("rate_limited", "Provider rate limit — backing off", int(self._blocked_until[market] - now) + 1)
            if self._weight_minute[market] == minute and self._weight[market] >= WEIGHT_LIMITS[market] * WEIGHT_SAFETY:
                raise ProviderError("rate_limited", "Request budget for this minute used up", 60 - int(now % 60))
        try:
            res = self.client.get(self.bases[market] + path, params=params)
        except httpx.TimeoutException:
            raise ProviderError("unavailable", "Provider timed out")
        except httpx.HTTPError:
            raise ProviderError("unavailable", "Provider unreachable")

        used = res.headers.get("X-MBX-USED-WEIGHT-1M")
        with self._lock:
            if used and used.isdigit():
                self._weight[market], self._weight_minute[market] = int(used), minute
            if res.status_code in (429, 418):
                retry = int(res.headers.get("Retry-After", "60") or 60)
                self._blocked_until[market] = time.time() + retry
        if res.status_code in (429, 418):
            raise ProviderError("rate_limited", "Rate limited by provider", retry)
        if res.status_code in (403, 451):
            raise ProviderError("region_blocked", "Provider not available from this server's region")
        if res.status_code == 400:
            raise ProviderError("bad_request", "Provider rejected the request (unknown symbol or bad parameters)")
        if res.status_code >= 400:
            raise ProviderError("unavailable", f"Provider error (HTTP {res.status_code})")
        try:
            return res.json()
        except ValueError:
            raise ProviderError("bad_payload", "Provider returned invalid JSON")

    def _cached(self, key: tuple, ttl: float, fn):
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        value = fn()
        self._cache[key] = (now, value)
        return value

    # ---------------- API ----------------
    def candles(self, market: MarketType, symbol: str, interval: str, limit: int) -> CandleSeries:
        sym = normalize_symbol(symbol)
        if interval not in BINANCE_INTERVALS:
            raise ProviderError("bad_request", f"Unsupported interval: {interval}")
        limit = max(1, min(1000, int(limit)))
        path = "/api/v3/klines" if market == MarketType.spot else "/fapi/v1/klines"

        def load():
            rows = self._get(market, path, {"symbol": sym, "interval": BINANCE_INTERVALS[interval], "limit": limit})
            if not isinstance(rows, list):
                raise ProviderError("bad_payload", "Unexpected candle payload")
            candles, dropped, gaps = validate_klines(rows, interval)
            return CandleSeries(candles, dropped, gaps, SOURCES[market], datetime.now(timezone.utc))

        return self._cached(("candles", market, sym, interval, limit), self.cache_ttl["candles"], load)

    def ticker(self, market: MarketType, symbol: str) -> Ticker:
        sym = normalize_symbol(symbol)
        path = "/api/v3/ticker/24hr" if market == MarketType.spot else "/fapi/v1/ticker/24hr"

        def load():
            r = self._get(market, path, {"symbol": sym})
            try:
                return Ticker(sym, market, float(r["lastPrice"]), float(r["priceChangePercent"]), float(r["quoteVolume"]),
                              _utc(r["closeTime"]), SOURCES[market], datetime.now(timezone.utc))
            except (KeyError, TypeError, ValueError):
                raise ProviderError("bad_payload", "Unexpected ticker payload")

        return self._cached(("ticker", market, sym), self.cache_ttl["ticker"], load)

    def funding(self, symbol: str) -> FundingSnapshot:
        sym = normalize_symbol(symbol)

        def load():
            r = self._get(MarketType.futures, "/fapi/v1/premiumIndex", {"symbol": sym})
            try:
                return FundingSnapshot(sym, float(r["markPrice"]), float(r["indexPrice"]), float(r["lastFundingRate"]),
                                       _utc(r["nextFundingTime"]), _utc(r["time"]), SOURCES[MarketType.futures],
                                       datetime.now(timezone.utc))
            except (KeyError, TypeError, ValueError):
                raise ProviderError("bad_payload", "Unexpected funding payload")

        return self._cached(("funding", sym), self.cache_ttl["funding"], load)
