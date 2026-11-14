"""Provider-neutral market data types. Exchange adapters convert their payloads into these."""
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MarketType(str, Enum):
    spot = "spot"
    futures = "futures"


# UI timeframe -> milliseconds
INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1H": 3_600_000, "4H": 14_400_000, "1D": 86_400_000}


@dataclass(frozen=True)
class Candle:
    open_time: datetime  # UTC
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class CandleSeries:
    candles: list[Candle]
    dropped: int  # malformed rows removed during validation
    gaps: int     # missing intervals inside the range
    source: str
    fetched_at: datetime


@dataclass(frozen=True)
class Ticker:
    symbol: str
    market: MarketType
    last_price: float
    change_24h_pct: float
    quote_volume_24h: float
    data_time: datetime
    source: str
    fetched_at: datetime
    price_label: str = "Last price"


@dataclass(frozen=True)
class FundingSnapshot:
    """Futures last/mark/index are different prices — never mix them up."""
    symbol: str
    mark_price: float
    index_price: float
    funding_rate: float
    next_funding_time: datetime
    data_time: datetime
    source: str
    fetched_at: datetime
    index_label: str = "Index price"


class ProviderError(Exception):
    """kind: 'unavailable' | 'rate_limited' | 'region_blocked' | 'bad_request' | 'bad_payload'"""

    def __init__(self, kind: str, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retry_after = retry_after


@dataclass(frozen=True)
class StreamSpec:
    """How to open one upstream WebSocket and turn its messages into events.

    parse(text) returns None (ignore) or an event dict:
      {"type": "candle", "candle": Candle, "closed": bool}  or  {"type": "funding", "data": FundingSnapshot}
    """
    url: str
    parse: Callable[[str], dict | None]
    subscribe: str | None = None      # message to send after connecting (if the venue needs one)
    ping: str | None = None           # application-level keepalive message, if any
    source: str = ""
    key: tuple = field(default_factory=tuple)
