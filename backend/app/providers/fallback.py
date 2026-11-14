"""Primary provider with a Futures-only fallback for region blocks / outages.

Spot always uses the primary. For Futures, if the primary fails with 'region_blocked' or
'unavailable', we switch to the fallback and re-check the primary every `recheck_seconds`.
Responses carry the real source name, so the UI always shows where data came from."""
import logging
import time

from .base import MarketType, ProviderError

log = logging.getLogger("tradeai.providers")
SWITCH_KINDS = {"region_blocked", "unavailable"}


class FallbackProvider:
    def __init__(self, primary, futures_fallback, recheck_seconds: float = 600):
        self.primary, self.fallback = primary, futures_fallback
        self.id = primary.id
        self.recheck_seconds = recheck_seconds
        self._fallback_since: float | None = None

    @property
    def using_fallback(self) -> bool:
        return self._fallback_since is not None

    def close(self):
        for p in (self.primary, self.fallback):
            getattr(p, "close", lambda: None)()

    def _futures(self, method: str, *args):
        if self._fallback_since and time.monotonic() - self._fallback_since < self.recheck_seconds:
            return getattr(self.fallback, method)(*args)
        try:
            out = getattr(self.primary, method)(*args)
            if self._fallback_since:
                log.info("Primary futures provider reachable again; leaving fallback")
            self._fallback_since = None
            return out
        except ProviderError as exc:
            if exc.kind not in SWITCH_KINDS or self.fallback is None:
                raise
            log.warning("Primary futures provider failed (%s); switching to fallback", exc.kind)
            self._fallback_since = time.monotonic()
            return getattr(self.fallback, method)(*args)

    def candles(self, market, symbol, interval, limit):
        if market == MarketType.futures:
            return self._futures("candles", market, symbol, interval, limit)
        return self.primary.candles(market, symbol, interval, limit)

    def ticker(self, market, symbol):
        if market == MarketType.futures:
            return self._futures("ticker", market, symbol)
        return self.primary.ticker(market, symbol)

    def specs(self, market, symbol):
        if market == MarketType.futures:
            return self._futures("specs", market, symbol)
        return self.primary.specs(market, symbol)

    def funding(self, symbol):
        return self._futures("funding", symbol)

    # Streams follow whichever provider is currently serving Futures REST.
    def kline_stream(self, market, symbol, interval):
        src = self.fallback if (market == MarketType.futures and self.using_fallback) else self.primary
        return src.kline_stream(market, symbol, interval)

    def funding_stream(self, symbol):
        return (self.fallback if self.using_fallback else self.primary).funding_stream(symbol)
