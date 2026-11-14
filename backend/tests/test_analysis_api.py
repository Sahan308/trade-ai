import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import get_settings
from app.providers.binance import BinanceProvider
from tests.fixtures import candles


def handler(request):
    t, o, h, l, c, v = candles(300, seed=3)
    rows = [[t[i], str(o[i]), str(h[i]), str(l[i]), str(c[i]), str(v[i]), t[i] + 3_599_999] for i in range(len(t))]
    return httpx.Response(200, json=rows)


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADEAI_DATABASE_URL", f"sqlite:///{tmp_path / 'a.db'}")
    get_settings.cache_clear(); db.reset_engine()
    from app.main import create_app
    p = BinanceProvider("https://s.test", "https://f.test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with TestClient(create_app(provider=p)) as c:
        yield c
    get_settings.cache_clear(); db.reset_engine()


def test_analysis_endpoint(api):
    r = api.get("/api/analysis/BTCUSDT?market=spot&interval=1H&limit=300")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["bars"] == 300 and b["source"] == "Binance Spot" and "not predictions" in b["disclaimer"]
    L = b["latest"]
    assert 0 <= L["rsi_14"] <= 100 and L["bb_lower"] < L["bb_middle"] < L["bb_upper"] and L["supertrend_direction"] in (1, -1)
    assert set(b["pivots"]) >= {"p", "r1", "s1"} and b["fibonacci"]["levels"]["0.618"]
    assert all(p["time"].startswith("20") for p in b["patterns"])


def test_patterns_endpoint_filters_by_bias(api):
    b = api.get("/api/patterns/BTCUSDT?window=300&bias=bullish").json()
    assert b["patterns"] and all(p["bias"] == "bullish" for p in b["patterns"])


def test_analysis_validation(api):
    assert api.get("/api/analysis/BTCUSDT?limit=10").status_code == 422
    assert api.get("/api/patterns/BTCUSDT?bias=maybe").status_code == 422
