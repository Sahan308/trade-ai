"""Hyperliquid public market data — used ONLY as the Futures fallback when Binance Futures is
region-blocked or unreachable. USDC-settled perpetuals quoted in USD; labelled as such.
Hyperliquid has no index price: we report its oracle price and label it "Oracle price"."""
import json
import math
import re
import time
from datetime import datetime, timezone

import httpx

from ..services.candles import validate_klines
from .base import INTERVAL_MS, Candle, CandleSeries, FundingSnapshot, MarketType, ProviderError, StreamSpec, Ticker

SOURCE = "Hyperliquid perpetuals (fallback)"
INTERVALS = {"1m": "1m", "5m": "5m", "15m": "15m", "1H": "1h", "4H": "4h", "1D": "1d"}


def to_coin(symbol: str) -> str:
    c = re.sub(r"[^A-Z0-9]", "", symbol.upper())
    c = re.sub(r"(USDT|USDC)$", "", c)
    if not re.match(r"^[A-Z0-9]{2,12}$", c):
        raise ProviderError("bad_request", f"Invalid symbol: {symbol}")
    return c


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _next_hour(ts: datetime) -> datetime:
    return datetime.fromtimestamp(math.ceil(ts.timestamp() / 3600) * 3600, tz=timezone.utc)


class HyperliquidProvider:
    id = "hyperliquid"

    def __init__(self, base: str = "https://api.hyperliquid.xyz", client: httpx.Client | None = None, timeout: float = 8.0):
        self.base = base.rstrip("/")
        self.client = client or httpx.Client(timeout=timeout, headers={"User-Agent": "TRADE-AI/0.3 (read-only)"})
        self._ctx_cache: tuple[float, dict] | None = None

    def close(self) -> None:
        self.client.close()

    def _info(self, body: dict):
        try:
            res = self.client.post(self.base + "/info", json=body)
        except httpx.HTTPError:
            raise ProviderError("unavailable", "Fallback provider unreachable")
        if res.status_code == 429:
            raise ProviderError("rate_limited", "Rate limited by fallback provider", 60)
        if res.status_code >= 400:
            raise ProviderError("unavailable", f"Fallback provider error (HTTP {res.status_code})")
        try:
            return res.json()
        except ValueError:
            raise ProviderError("bad_payload", "Fallback provider returned invalid JSON")

    def _ctx(self, coin: str) -> dict:
        if not self._ctx_cache or time.monotonic() - self._ctx_cache[0] > 3:
            meta, ctxs = self._info({"type": "metaAndAssetCtxs"})
            self._ctx_cache = (time.monotonic(), {u["name"]: c for u, c in zip(meta["universe"], ctxs)})
        ctx = self._ctx_cache[1].get(coin)
        if ctx is None:
            raise ProviderError("bad_request", f"{coin} is not listed on the fallback provider")
        return ctx

    @staticmethod
    def _require_futures(market: MarketType):
        if market != MarketType.futures:
            raise ProviderError("bad_request", "Fallback provider only covers Futures")

    def candles(self, market: MarketType, symbol: str, interval: str, limit: int) -> CandleSeries:
        self._require_futures(market)
        if interval not in INTERVALS:
            raise ProviderError("bad_request", f"Unsupported interval: {interval}")
        limit = max(1, min(1000, int(limit)))
        end = int(time.time() * 1000)
        rows = self._info({"type": "candleSnapshot", "req": {"coin": to_coin(symbol), "interval": INTERVALS[interval],
                                                             "startTime": end - INTERVAL_MS[interval] * limit, "endTime": end}})
        if not isinstance(rows, list):
            raise ProviderError("bad_payload", "Unexpected candle payload")
        kl = [[r.get("t"), r.get("o"), r.get("h"), r.get("l"), r.get("c"), r.get("v")] for r in rows if isinstance(r, dict)]
        candles, dropped, gaps = validate_klines(kl, interval)
        return CandleSeries(candles, dropped, gaps, SOURCE, _now())

    def history(self, market: MarketType, symbol: str, interval: str, start_ms: int, end_ms: int) -> CandleSeries:
        self._require_futures(market)
        rows, cursor = [], int(start_ms)
        for _ in range(100):
            page = self._info({"type": "candleSnapshot", "req": {"coin": to_coin(symbol), "interval": INTERVALS[interval],
                                                                 "startTime": cursor, "endTime": int(end_ms) - 1}})
            if not isinstance(page, list) or not page:
                break
            rows.extend([[r.get("t"), r.get("o"), r.get("h"), r.get("l"), r.get("c"), r.get("v")] for r in page if isinstance(r, dict)])
            nxt = int(page[-1]["t"]) + 1
            if nxt >= end_ms or len(page) < 500:
                break
            cursor = nxt
        candles, dropped, gaps = validate_klines(rows, interval)
        return CandleSeries(candles, dropped, gaps, SOURCE, _now())

    def ticker(self, market: MarketType, symbol: str) -> Ticker:
        self._require_futures(market)
        coin = to_coin(symbol)
        try:
            ctx = self._ctx(coin)
            mid, prev = float(ctx.get("midPx") or ctx["markPx"]), float(ctx["prevDayPx"])
            return Ticker(coin + "USDT", market, mid, (mid - prev) / prev * 100, float(ctx["dayNtlVlm"]), _now(), SOURCE, _now(), "Mid price")
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            raise ProviderError("bad_payload", "Unexpected ticker payload")

    def funding(self, symbol: str) -> FundingSnapshot:
        coin = to_coin(symbol)
        try:
            ctx = self._ctx(coin)
            now = _now()
            return FundingSnapshot(coin, float(ctx["markPx"]), float(ctx["oraclePx"]), float(ctx["funding"]),
                                   _next_hour(now), now, SOURCE, now, "Oracle price")
        except (KeyError, TypeError, ValueError):
            raise ProviderError("bad_payload", "Unexpected funding payload")

    def specs(self, market: MarketType, symbol: str) -> dict:
        self._require_futures(market)
        coin = to_coin(symbol)
        meta = self._info({"type": "meta"})
        u = next((x for x in meta.get("universe", []) if x.get("name") == coin), None)
        if u is None:
            raise ProviderError("bad_request", f"{coin} is not listed on the fallback provider")
        return {"symbol": coin, "market": "futures", "tick_size": None, "step_size": 10 ** -int(u.get("szDecimals", 0)),
                "min_qty": None, "min_notional": 10.0, "mmr": None, "source": SOURCE,
                "max_leverage": u.get("maxLeverage")}

    # ---- streams ----
    def kline_stream(self, market: MarketType, symbol: str, interval: str) -> StreamSpec:
        self._require_futures(market)
        coin = to_coin(symbol)

        def parse(text):
            try:
                m = json.loads(text)
                if m.get("channel") != "candle":
                    return None
                k = m["data"]
                o, h, l, c, v = (float(k[x]) for x in ("o", "h", "l", "c", "v"))
                if h < l:
                    return None
                return {"type": "candle", "candle": Candle(datetime.fromtimestamp(k["t"] / 1000, tz=timezone.utc), o, h, l, c, v), "closed": False}
            except (KeyError, TypeError, ValueError):
                return None

        sub = json.dumps({"method": "subscribe", "subscription": {"type": "candle", "coin": coin, "interval": INTERVALS[interval]}})
        return StreamSpec("wss://api.hyperliquid.xyz/ws", parse, sub, '{"method":"ping"}', SOURCE, ("hyperliquid", "kline", coin, interval))

    def funding_stream(self, symbol: str) -> StreamSpec:
        coin = to_coin(symbol)

        def parse(text):
            try:
                m = json.loads(text)
                if m.get("channel") != "activeAssetCtx":
                    return None
                ctx, now = m["data"]["ctx"], _now()
                return {"type": "funding", "data": FundingSnapshot(coin, float(ctx["markPx"]), float(ctx["oraclePx"]), float(ctx["funding"]),
                                                                  _next_hour(now), now, SOURCE, now, "Oracle price")}
            except (KeyError, TypeError, ValueError):
                return None

        sub = json.dumps({"method": "subscribe", "subscription": {"type": "activeAssetCtx", "coin": coin}})
        return StreamSpec("wss://api.hyperliquid.xyz/ws", parse, sub, '{"method":"ping"}', SOURCE, ("hyperliquid", "ctx", coin))
