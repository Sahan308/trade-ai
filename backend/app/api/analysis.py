"""Analysis endpoints: indicators, candlestick patterns and chart formations on validated candles.
Patterns and formations are context, not predictions."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from ..analysis.summary import analyze
from ..providers.base import MarketType, ProviderError
from .markets import Interval, SymbolPath, get_provider, provider_error

router = APIRouter(prefix="/api", tags=["analysis"])
DISCLAIMER = "Indicators and patterns describe past price action. They are context, not predictions or advice."


def _series(provider, market, symbol, interval, limit):
    s = provider.candles(market, symbol, interval, limit)
    cs = s.candles
    t = [int(x.open_time.timestamp() * 1000) for x in cs]
    return s, t, [x.open for x in cs], [x.high for x in cs], [x.low for x in cs], [x.close for x in cs], [x.volume for x in cs]


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


@router.get("/analysis/{symbol}", summary="Indicator readings, levels, patterns and formations")
def analysis(request: Request, symbol: SymbolPath, market: MarketType = MarketType.spot, interval: Interval = "1H",
             limit: int = Query(300, ge=60, le=1000), provider=Depends(get_provider)):
    try:
        s, t, o, h, l, c, v = _series(provider, market, symbol, interval, limit)
    except ProviderError as exc:
        return provider_error(request, exc)
    res = analyze(t, o, h, l, c, v, interval)
    for p in res["patterns"]:
        p["time"] = _iso(p["time"])
    for f in res["formations"]:
        f["times"] = [_iso(x) for x in f["times"]]
    return {"symbol": symbol.upper(), "market": market, "interval": interval, "as_of": _iso(t[-1]) if t else None,
            "source": s.source, "fetched_at": s.fetched_at, "data_gaps": s.gaps, "disclaimer": DISCLAIMER, **res}


@router.get("/patterns/{symbol}", summary="Recent candlestick patterns and chart formations")
def patterns(request: Request, symbol: SymbolPath, market: MarketType = MarketType.spot, interval: Interval = "1H",
             limit: int = Query(300, ge=20, le=1000), window: int = Query(30, ge=1, le=500),
             bias: Literal["bullish", "bearish", "neutral"] | None = None, provider=Depends(get_provider)):
    try:
        s, t, o, h, l, c, v = _series(provider, market, symbol, interval, limit)
    except ProviderError as exc:
        return provider_error(request, exc)
    res = analyze(t, o, h, l, c, v, interval, pattern_window=window)
    pats = [dict(p, time=_iso(p["time"])) for p in res["patterns"] if bias is None or p["bias"] == bias]
    forms = [dict(f, times=[_iso(x) for x in f["times"]]) for f in res["formations"]]
    return {"symbol": symbol.upper(), "market": market, "interval": interval, "source": s.source, "fetched_at": s.fetched_at,
            "disclaimer": DISCLAIMER, "patterns": pats, "formations": forms}
