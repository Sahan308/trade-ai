"""Shared upstream WebSocket hub.

One upstream connection per (venue, stream) no matter how many browsers watch it. Each channel:
  * reconnects with exponential backoff,
  * treats the feed as stale after `stale_seconds` without a message,
  * after every RE-connect sends subscribers a REST "snapshot" of recent candles (reconciliation),
  * shuts the upstream down when the last subscriber leaves.
Events sent to clients:
  {"type":"status","status":"connecting|live|reconnecting|stale"}
  {"type":"candle","candle":{...},"closed":bool}
  {"type":"snapshot","candles":[...]}
  {"type":"funding","data":{...}}
"""
import asyncio
import contextlib
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict
from datetime import datetime

from .providers.base import StreamSpec

log = logging.getLogger("tradeai.streams")

# connector(spec) -> async context manager yielding an object with: async recv() -> str, async send(str)
Connector = Callable[[StreamSpec], "contextlib.AbstractAsyncContextManager"]


def _jsonable(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return _jsonable(asdict(obj))
    return obj


@contextlib.asynccontextmanager
async def websockets_connector(spec: StreamSpec):
    import websockets  # installed with uvicorn[standard]

    async with websockets.connect(spec.url, open_timeout=10, ping_interval=20, max_size=2**20) as ws:
        yield ws


class Channel:
    def __init__(self, hub: "StreamHub", spec: StreamSpec, snapshot: Callable[[], Awaitable[list]] | None):
        self.hub, self.spec, self.snapshot = hub, spec, snapshot
        self.subscribers: set[asyncio.Queue] = set()
        self.task: asyncio.Task | None = None
        self.status = "connecting"
        self.connects = 0

    def broadcast(self, event: dict):
        data = _jsonable(event)
        for q in list(self.subscribers):
            if q.full():                 # slow client: drop its oldest message rather than block everyone
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            q.put_nowait(data)

    def set_status(self, status: str):
        self.status = status
        self.broadcast({"type": "status", "status": status})

    async def run(self):
        attempt = 0
        while self.subscribers:
            try:
                async with self.hub.connector(self.spec) as ws:
                    if self.spec.subscribe:
                        await ws.send(self.spec.subscribe)
                    self.connects += 1
                    attempt = 0
                    self.set_status("live")
                    if self.connects > 1 and self.snapshot:      # reconcile after a reconnect
                        with contextlib.suppress(Exception):
                            self.broadcast({"type": "snapshot", "candles": await self.snapshot()})
                    await self._pump(ws)
                if self.subscribers:
                    self.set_status("reconnecting")
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                self.set_status("stale")
            except Exception as exc:  # noqa: BLE001 — any upstream failure → back off and retry
                log.info("upstream %s failed: %s", self.spec.url, exc.__class__.__name__)
                if self.subscribers:
                    self.set_status("reconnecting")
            if not self.subscribers:
                break
            delay = min(self.hub.max_backoff, self.hub.base_backoff * 2 ** attempt) * (1 + random.random() * 0.2)
            attempt += 1
            await asyncio.sleep(delay)

    async def _pump(self, ws):
        ping_task = None
        if self.spec.ping:
            async def pinger():
                while True:
                    await asyncio.sleep(self.hub.ping_seconds)
                    await ws.send(self.spec.ping)
            ping_task = asyncio.create_task(pinger())
        try:
            while self.subscribers:
                text = await asyncio.wait_for(ws.recv(), timeout=self.hub.stale_seconds)
                if text is None:
                    return
                event = self.spec.parse(text)
                if event:
                    self.broadcast(event)
        finally:
            if ping_task:
                ping_task.cancel()


class StreamHub:
    def __init__(self, connector: Connector = websockets_connector, stale_seconds: float = 30,
                 base_backoff: float = 1.0, max_backoff: float = 30.0, ping_seconds: float = 30, queue_size: int = 200):
        self.connector = connector
        self.stale_seconds, self.base_backoff, self.max_backoff = stale_seconds, base_backoff, max_backoff
        self.ping_seconds, self.queue_size = ping_seconds, queue_size
        self.channels: dict[tuple, Channel] = {}

    @contextlib.asynccontextmanager
    async def subscribe(self, spec: StreamSpec, snapshot=None) -> AsyncIterator[asyncio.Queue]:
        key = spec.key or (spec.url, spec.subscribe)
        ch = self.channels.get(key)
        if ch is None:
            ch = self.channels[key] = Channel(self, spec, snapshot)
        q: asyncio.Queue = asyncio.Queue(maxsize=self.queue_size)
        ch.subscribers.add(q)
        q.put_nowait({"type": "status", "status": ch.status})
        if ch.task is None or ch.task.done():
            ch.task = asyncio.create_task(ch.run())
        try:
            yield q
        finally:
            ch.subscribers.discard(q)
            if not ch.subscribers:
                self.channels.pop(key, None)
                if ch.task and not ch.task.done():
                    ch.task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await ch.task

    async def close(self):
        for ch in list(self.channels.values()):
            ch.subscribers.clear()
            if ch.task:
                ch.task.cancel()
        self.channels.clear()
