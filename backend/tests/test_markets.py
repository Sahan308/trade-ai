import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import get_settings
from app.providers.base import MarketType, ProviderError
from app.providers.binance import BinanceProvider, normalize_symbol
from app.services.candles import validate_klines

H = 3_600_000
T0 = 1_794_643_200_000  # aligned to the hour


def kline(t, o=100.0, h=101.0, l=99.0, c=100.5, v=10.0):
    return [t, str(o), str(h), str(l), str(c), str(v), t + H - 1, "0", 1, "0", "0", "0"]


class FakeBinance:
    """Mock transport mimicking the public endpoints we use."""

    def __init__(self):
        self.calls = []
        self.status = None  # force a status code for every call
        self.headers = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.status:
            return httpx.Response(self.status, headers=self.headers, json={"code": -1, "msg": "x"})
        p = request.url.path
        if p.endswith("/klines"):
            rows = [kline(T0 + i * H) for i in range(5)]
            rows.append(kline(T0 + 4 * H, c=100.9))       # duplicate of last → later wins
            rows.append(kline(T0 + 7 * H))                # 2 missing candles before this one
            rows.insert(0, ["bad", "x"])                  # malformed
            rows.append(kline(T0 + 8 * H, h=90))          # high below open/close → invalid
            return httpx.Response(200, json=rows, headers={"X-MBX-USED-WEIGHT-1M": "12"})
        if p.endswith("/ticker/24hr"):
            return httpx.Response(200, json={"symbol": request.url.params["symbol"], "lastPrice": "67000.5",
                                             "priceChangePercent": "-1.25", "quoteVolume": "123456789", "closeTime": T0})
        if p.endswith("/premiumIndex"):
            return httpx.Response(200, json={"symbol": "SOLUSDT", "markPrice": "75.70", "indexPrice": "75.72",
                                             "lastFundingRate": "-0.00006", "nextFundingTime": T0 + 8 * H, "time": T0})
        return httpx.Response(404, json={})


@pytest.fixture()
def fake():
    return FakeBinance()


@pytest.fixture()
def provider(fake):
    return BinanceProvider("https://spot.test", "https://fut.test", client=httpx.Client(transport=httpx.MockTransport(fake)))


@pytest.fixture()
def api(tmp_path, monkeypatch, provider):
    monkeypatch.setenv("TRADEAI_ENV", "test")
    monkeypatch.setenv("TRADEAI_DATABASE_URL", f"sqlite:///{tmp_path / 't.db'}")
    monkeypatch.setenv("TRADEAI_RATE_LIMIT_PER_MINUTE", "1000")
    get_settings.cache_clear(); db.reset_engine()
    from app.main import create_app
    with TestClient(create_app(provider=provider), raise_server_exceptions=False) as c:
        yield c
    get_settings.cache_clear(); db.reset_engine()


# ---------- validation ----------
def test_validate_klines_dedupes_drops_and_counts_gaps():
    rows = [kline(T0), kline(T0 + H), kline(T0 + H, c=100.9), kline(T0 + 4 * H), ["x"], kline(T0 + 5 * H, l=200)]
    candles, dropped, gaps = validate_klines(rows, "1H")
    assert [c.open_time.timestamp() * 1000 for c in candles] == [T0, T0 + H, T0 + 4 * H]
    assert candles[1].close == 100.9
    assert dropped == 2 and gaps == 2
    assert candles[0].open_time.tzinfo is not None  # UTC-aware


@pytest.mark.parametrize("bad", ["BTC", "btc-usd", "DROP TABLE", "BTCUSDT; x", ""])
def test_normalize_symbol_rejects_bad(bad):
    with pytest.raises(ProviderError):
        normalize_symbol(bad)


def test_normalize_symbol_accepts_slash_form():
    assert normalize_symbol("btc/usdt") == "BTCUSDT"


# ---------- endpoints ----------
def test_candles_endpoint(api, fake):
    r = api.get("/api/markets/BTCUSDT/candles?market=spot&interval=1H&limit=50")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["source"] == "Binance Spot" and b["gaps"] == 2 and b["dropped"] == 2
    assert len(b["candles"]) == 6 and b["candles"][4]["close"] == 100.9
    req = fake.calls[-1]
    assert req.url.host == "spot.test" and req.url.path == "/api/v3/klines"
    assert dict(req.url.params) == {"symbol": "BTCUSDT", "interval": "1h", "limit": "50"}


def test_futures_candles_use_futures_host(api, fake):
    assert api.get("/api/markets/SOLUSDT/candles?market=futures&interval=4H").status_code == 200
    assert fake.calls[-1].url.host == "fut.test" and fake.calls[-1].url.path == "/fapi/v1/klines"


def test_ticker_endpoint(api):
    b = api.get("/api/markets/ETHUSDT/ticker?market=spot").json()
    assert b["last_price"] == 67000.5 and b["change_24h_pct"] == -1.25 and b["source"] == "Binance Spot"
    assert b["data_time"].startswith("2026-")


def test_funding_keeps_mark_and_index_distinct(api):
    b = api.get("/api/futures/SOLUSDT/funding").json()
    assert b["mark_price"] == 75.70 and b["index_price"] == 75.72 and b["funding_rate"] == -0.00006
    assert b["source"] == "Binance USDT-M Futures"


def test_markets_list(api):
    b = api.get("/api/markets").json()
    assert {"symbol": "SOLUSDT", "market": "futures"} in b["markets"] and b["provider"] == "binance"


@pytest.mark.parametrize("url", [
    "/api/markets/BTC/candles",                          # bad symbol
    "/api/markets/BTCUSDT/candles?interval=7m",          # bad interval
    "/api/markets/BTCUSDT/candles?limit=5000",           # limit too high
    "/api/markets/BTCUSDT/candles?market=options",       # bad market
])
def test_input_validation(api, url):
    r = api.get(url)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_cache_avoids_repeat_calls(api, fake):
    api.get("/api/markets/BTCUSDT/ticker"); api.get("/api/markets/BTCUSDT/ticker")
    assert len(fake.calls) == 1


# ---------- provider failures ----------
def test_rate_limited_by_provider_backs_off(api, fake):
    fake.status, fake.headers = 429, {"Retry-After": "30"}
    r = api.get("/api/markets/BTCUSDT/ticker")
    assert r.status_code == 503 and r.json()["error"]["code"] == "provider_rate_limited"
    assert r.headers["Retry-After"] == "30"
    n = len(fake.calls)
    fake.status = None
    r = api.get("/api/markets/ETHUSDT/ticker")      # still inside back-off window → no upstream call
    assert r.status_code == 503 and len(fake.calls) == n


def test_region_block(api, fake):
    fake.status = 451
    assert api.get("/api/markets/BTCUSDT/ticker").json()["error"]["code"] == "provider_region_blocked"


def test_provider_down(tmp_path, monkeypatch):
    def down(request):
        raise httpx.ConnectError("no route")
    p = BinanceProvider("https://s.test", "https://f.test", client=httpx.Client(transport=httpx.MockTransport(down)))
    with pytest.raises(ProviderError) as e:
        p.ticker(MarketType.spot, "BTCUSDT")
    assert e.value.kind == "unavailable"


def test_weight_budget_guard(provider, fake):
    provider._weight[MarketType.spot] = 6000
    provider._weight_minute[MarketType.spot] = int(time.time() // 60)
    with pytest.raises(ProviderError) as e:
        provider.ticker(MarketType.spot, "BTCUSDT")
    assert e.value.kind == "rate_limited" and not fake.calls


# ---------- inbound rate limit ----------
def test_inbound_rate_limit(tmp_path, monkeypatch, provider):
    monkeypatch.setenv("TRADEAI_DATABASE_URL", f"sqlite:///{tmp_path / 'r.db'}")
    monkeypatch.setenv("TRADEAI_RATE_LIMIT_PER_MINUTE", "3")
    monkeypatch.setenv("TRADEAI_CORS_ORIGINS", "http://localhost:8080")
    get_settings.cache_clear(); db.reset_engine()
    from app.main import create_app
    with TestClient(create_app(provider=provider)) as c:
        codes = [c.get("/api/markets").status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
        r = c.get("/api/markets", headers={"Origin": "http://localhost:8080"})
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
        assert r.headers.get("access-control-allow-origin") == "http://localhost:8080"  # browser can read the 429
        assert c.get("/health").status_code == 200   # health isn't rate limited
    get_settings.cache_clear(); db.reset_engine()
