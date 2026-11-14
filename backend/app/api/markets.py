"""Market data endpoints. Every response carries source, data time and fetch time (UTC)."""
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..config import get_settings
from ..errors import error_response
from ..providers.base import MarketType, ProviderError

router = APIRouter(prefix="/api", tags=["markets"])

SymbolPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9]{2,15}[Uu][Ss][Dd][Tt]$", description="e.g. BTCUSDT")]
Interval = Literal["1m", "5m", "15m", "1H", "4H", "1D"]


def get_provider(request: Request):
    return request.app.state.provider


class MarketItem(BaseModel):
    symbol: str
    market: MarketType


class MarketsResponse(BaseModel):
    markets: list[MarketItem]
    provider: str


class CandleOut(BaseModel):
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandlesResponse(BaseModel):
    symbol: str
    market: MarketType
    interval: Interval
    candles: list[CandleOut]
    gaps: int
    dropped: int
    source: str
    fetched_at: datetime


class TickerResponse(BaseModel):
    symbol: str
    market: MarketType
    last_price: float
    change_24h_pct: float
    quote_volume_24h: float
    data_time: datetime
    source: str
    fetched_at: datetime


class FundingResponse(BaseModel):
    symbol: str
    mark_price: float
    index_price: float
    funding_rate: float
    next_funding_time: datetime
    data_time: datetime
    source: str
    fetched_at: datetime


_STATUS = {"bad_request": 400, "rate_limited": 503, "region_blocked": 503, "unavailable": 502, "bad_payload": 502}


def provider_error(request: Request, exc: ProviderError) -> JSONResponse:
    resp = error_response(request, _STATUS.get(exc.kind, 502), f"provider_{exc.kind}", exc.message)
    if exc.retry_after:
        resp.headers["Retry-After"] = str(exc.retry_after)
    return resp


@router.get("/markets", response_model=MarketsResponse, summary="Configured symbols")
def markets(provider=Depends(get_provider)):
    items = []
    for entry in get_settings().markets:
        sym, _, mkt = entry.partition(":")
        items.append(MarketItem(symbol=sym.upper(), market=MarketType(mkt or "spot")))
    return MarketsResponse(markets=items, provider=provider.id)


@router.get("/markets/{symbol}/candles", response_model=CandlesResponse, summary="Historical candles")
def candles(request: Request, symbol: SymbolPath, market: MarketType = MarketType.spot, interval: Interval = "1H",
            limit: int = Query(200, ge=1, le=1000), provider=Depends(get_provider)):
    try:
        s = provider.candles(market, symbol, interval, limit)
    except ProviderError as exc:
        return provider_error(request, exc)
    return CandlesResponse(symbol=symbol.upper(), market=market, interval=interval, gaps=s.gaps, dropped=s.dropped,
                           source=s.source, fetched_at=s.fetched_at,
                           candles=[CandleOut(**c.__dict__) for c in s.candles])


@router.get("/markets/{symbol}/ticker", response_model=TickerResponse, summary="24h ticker (last price)")
def ticker(request: Request, symbol: SymbolPath, market: MarketType = MarketType.spot, provider=Depends(get_provider)):
    try:
        return TickerResponse(**provider.ticker(market, symbol).__dict__)
    except ProviderError as exc:
        return provider_error(request, exc)


@router.get("/futures/{symbol}/funding", response_model=FundingResponse, summary="Futures mark/index price and funding")
def funding(request: Request, symbol: SymbolPath, provider=Depends(get_provider)):
    try:
        return FundingResponse(**provider.funding(symbol).__dict__)
    except ProviderError as exc:
        return provider_error(request, exc)
