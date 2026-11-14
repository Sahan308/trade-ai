"""WebSocket endpoints. Read-only market streams; clients never send anything we act on."""
import asyncio
import contextlib
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from ..config import get_settings
from ..providers.base import MarketType, ProviderError

router = APIRouter(tags=["streams"])
INTERVALS = {"1m", "5m", "15m", "1H", "4H", "1D"}
SYMBOL_RE = re.compile(r"^[A-Za-z0-9]{2,15}USDT$", re.I)


async def _admit(ws: WebSocket) -> bool:
    """Origin allowlist (CORS doesn't cover WebSockets) + shared rate limit on connection attempts."""
    settings = get_settings()
    origin = ws.headers.get("origin")
    if origin and origin not in settings.cors_origins:
        await ws.close(code=1008)
        return False
    ip = ws.client.host if ws.client else "unknown"
    ok, _ = await ws.app.state.rate_limiter.allow(ip)
    hub_counts = ws.app.state.ws_counts
    if not ok or hub_counts.get(ip, 0) >= settings.ws_max_per_ip:
        await ws.close(code=1013)  # try again later
        return False
    hub_counts[ip] = hub_counts.get(ip, 0) + 1
    return True


def _release(ws: WebSocket):
    ip = ws.client.host if ws.client else "unknown"
    c = ws.app.state.ws_counts
    c[ip] = max(0, c.get(ip, 1) - 1)
    if not c[ip]:
        c.pop(ip, None)


async def _serve(ws: WebSocket, spec, snapshot=None):
    hub = ws.app.state.hub
    await ws.accept()
    try:
        async with hub.subscribe(spec, snapshot) as q:
            async def client_gone():
                with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                    while True:
                        await ws.receive_text()   # ignore anything the client sends
            gone = asyncio.create_task(client_gone())
            try:
                while not gone.done():
                    get = asyncio.create_task(q.get())
                    done, _ = await asyncio.wait({get, gone}, return_when=asyncio.FIRST_COMPLETED)
                    if get in done:
                        await ws.send_json(get.result())
                    else:
                        get.cancel()
            finally:
                gone.cancel()
    except (WebSocketDisconnect, RuntimeError):
        pass


@router.websocket("/ws/chart/{symbol}/{interval}")
async def chart_stream(ws: WebSocket, symbol: str, interval: str, market: str = "spot"):
    if not SYMBOL_RE.match(symbol) or interval not in INTERVALS or market not in ("spot", "futures"):
        await ws.close(code=1008)
        return
    if not await _admit(ws):
        return
    try:
        provider, mkt = ws.app.state.provider, MarketType(market)
        try:
            spec = provider.kline_stream(mkt, symbol, interval)
        except ProviderError:
            await ws.close(code=1008)
            return

        async def snapshot():
            s = await run_in_threadpool(provider.candles, mkt, symbol, interval, 20)
            return s.candles

        await _serve(ws, spec, snapshot)
    finally:
        _release(ws)


@router.websocket("/ws/market/{symbol}")
async def market_stream(ws: WebSocket, symbol: str):
    """Futures mark / index (or oracle) price and funding, pushed as they update."""
    if not SYMBOL_RE.match(symbol):
        await ws.close(code=1008)
        return
    if not await _admit(ws):
        return
    try:
        try:
            spec = ws.app.state.provider.funding_stream(symbol)
        except ProviderError:
            await ws.close(code=1008)
            return
        await _serve(ws, spec)
    finally:
        _release(ws)
