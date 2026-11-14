import asyncio
import contextlib
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import db
from app.config import get_settings
from app.providers.binance import BinanceProvider
from app.streams import StreamHub
from tests.test_markets import FakeBinance

T0 = 1_794_643_200_000


def kline_msg(close, t=T0, closed=False):
    return json.dumps({"e": "kline", "E": t, "s": "BTCUSDT",
                       "k": {"t": t, "T": t + 3_599_999, "o": "100", "h": str(max(100, close) + 1), "l": str(min(100, close) - 1),
                             "c": str(close), "v": "5", "x": closed}})


class FakeConnector:
    """Each connection plays one script: a list of messages; 'DROP' raises (connection lost);
    'STALL' never returns; 'TICK' produces an endless slow stream."""

    def __init__(self, *scripts):
        self.scripts = list(scripts)
        self.connections = 0
        self.urls = []

    @contextlib.asynccontextmanager
    async def __call__(self, spec):
        self.connections += 1
        self.urls.append(spec.url)
        script = self.scripts.pop(0) if self.scripts else ["STALL"]
        yield FakeWS(script)


class FakeWS:
    def __init__(self, script):
        self.script, self.sent, self.n = list(script), [], 0

    async def send(self, msg):
        self.sent.append(msg)

    async def recv(self):
        if not self.script:
            await asyncio.sleep(3600)
        item = self.script[0]
        if item == "TICK":
            await asyncio.sleep(0.05)
            self.n += 1
            return kline_msg(100 + self.n)
        self.script.pop(0)
        if item == "DROP":
            raise ConnectionError("dropped")
        if item == "STALL":
            await asyncio.sleep(3600)
        await asyncio.sleep(0.01)
        return item


@pytest.fixture()
def make_client(tmp_path, monkeypatch):
    clients = []

    def make(connector, **hub_kw):
        monkeypatch.setenv("TRADEAI_ENV", "test")
        monkeypatch.setenv("TRADEAI_DATABASE_URL", f"sqlite:///{tmp_path / 's.db'}")
        monkeypatch.setenv("TRADEAI_CORS_ORIGINS", "http://localhost:8080")
        get_settings.cache_clear(); db.reset_engine()
        from app.main import create_app
        provider = BinanceProvider("https://spot.test", "https://fut.test", client=httpx.Client(transport=httpx.MockTransport(FakeBinance())))
        hub = StreamHub(connector=connector, base_backoff=0.01, max_backoff=0.02, **hub_kw)
        c = TestClient(create_app(provider=provider, hub=hub))
        c.__enter__()
        clients.append(c)
        return c

    yield make
    for c in clients:
        c.__exit__(None, None, None)
    get_settings.cache_clear(); db.reset_engine()


def recv_until(ws, pred, limit=50):
    seen = []
    for _ in range(limit):
        m = ws.receive_json()
        seen.append(m)
        if pred(m):
            return m, seen
    raise AssertionError(f"not received; got {seen}")


def test_chart_stream_relays_validated_candles(make_client):
    conn = FakeConnector([kline_msg(101), '{"junk": true}', kline_msg(102, closed=True)])
    c = make_client(conn)
    with c.websocket_connect("/ws/chart/BTCUSDT/1H?market=spot") as ws:
        m, seen = recv_until(ws, lambda m: m["type"] == "candle" and m["closed"])
        assert m["candle"]["close"] == 102.0 and m["candle"]["open_time"].startswith("2026-")
        assert {"type": "status", "status": "live"} in seen
        assert [x["candle"]["close"] for x in seen if x["type"] == "candle"] == [101.0, 102.0]  # junk ignored
    assert conn.urls == ["wss://data-stream.binance.vision/ws/btcusdt@kline_1h"]


def test_one_upstream_shared_by_many_clients(make_client):
    conn = FakeConnector(["TICK"])
    c = make_client(conn)
    with c.websocket_connect("/ws/chart/BTCUSDT/1H") as a, c.websocket_connect("/ws/chart/BTCUSDT/1H") as b:
        recv_until(a, lambda m: m["type"] == "candle")
        recv_until(b, lambda m: m["type"] == "candle")
    assert conn.connections == 1


def test_reconnect_then_reconcile_with_snapshot(make_client):
    conn = FakeConnector([kline_msg(101), "DROP"], ["STALL"])
    c = make_client(conn)
    with c.websocket_connect("/ws/chart/BTCUSDT/1H?market=spot") as ws:
        snap, seen = recv_until(ws, lambda m: m["type"] == "snapshot")
        statuses = [m["status"] for m in seen if m["type"] == "status"]
        assert "reconnecting" in statuses and statuses.count("live") == 2
        assert len(snap["candles"]) == 6          # REST candles from the mocked provider
    assert conn.connections == 2


def test_stale_feed_is_reported(make_client):
    c = make_client(FakeConnector(["STALL"], ["STALL"]), stale_seconds=0.2)
    with c.websocket_connect("/ws/chart/BTCUSDT/1H") as ws:
        recv_until(ws, lambda m: m.get("status") == "stale")


def test_upstream_closed_after_last_client_leaves(make_client):
    c = make_client(FakeConnector(["TICK"]))
    with c.websocket_connect("/ws/chart/BTCUSDT/1H") as ws:
        recv_until(ws, lambda m: m["type"] == "candle")
    deadline = time.time() + 2
    while c.app.state.hub.channels and time.time() < deadline:
        time.sleep(0.05)
    assert not c.app.state.hub.channels


def test_futures_funding_stream(make_client):
    msg = json.dumps({"e": "markPriceUpdate", "E": T0, "s": "SOLUSDT", "p": "75.70", "i": "75.72", "r": "-0.00006", "T": T0 + 3600000})
    conn = FakeConnector([msg])
    c = make_client(conn)
    with c.websocket_connect("/ws/market/SOLUSDT") as ws:
        m, _ = recv_until(ws, lambda m: m["type"] == "funding")
        assert m["data"]["mark_price"] == 75.70 and m["data"]["index_price"] == 75.72 and m["data"]["index_label"] == "Index price"
    assert conn.urls == ["wss://fstream.binance.com/market/ws/solusdt@markPrice@1s"]


@pytest.mark.parametrize("path", ["/ws/chart/BTC/1H", "/ws/chart/BTCUSDT/7m", "/ws/chart/BTCUSDT/1H?market=options"])
def test_invalid_stream_params_rejected(make_client, path):
    c = make_client(FakeConnector())
    with pytest.raises(WebSocketDisconnect) as e:
        with c.websocket_connect(path) as ws:
            ws.receive_json()
    assert e.value.code == 1008


def test_disallowed_origin_rejected(make_client):
    c = make_client(FakeConnector())
    with pytest.raises(WebSocketDisconnect) as e:
        with c.websocket_connect("/ws/chart/BTCUSDT/1H", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_json()
    assert e.value.code == 1008


def test_per_ip_connection_cap(make_client, monkeypatch):
    monkeypatch.setenv("TRADEAI_WS_MAX_PER_IP", "1")
    c = make_client(FakeConnector(["TICK"]))
    with c.websocket_connect("/ws/chart/BTCUSDT/1H") as a:
        recv_until(a, lambda m: m["type"] == "candle")
        with pytest.raises(WebSocketDisconnect) as e:
            with c.websocket_connect("/ws/chart/BTCUSDT/1H") as b:
                b.receive_json()
        assert e.value.code == 1013
