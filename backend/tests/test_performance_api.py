"""Backtest CLI path (mocked exchange), storage and /api/backtests, /api/performance."""
from datetime import datetime, timezone

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app import db
from app.config import get_settings
from app.providers.binance import BinanceProvider
from app.signals.store import save
from tests.fixtures import H, candles
from tests.test_tracking_api import stored


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADEAI_DATABASE_URL", f"sqlite:///{tmp_path / 'perf.db'}")
    get_settings.cache_clear(); db.reset_engine()
    command.upgrade(Config("alembic.ini"), "head")
    yield
    db.reset_engine(); get_settings.cache_clear()


def history_handler():
    t, o, h, l, c, v = candles(900, seed=9)
    rows = [[t[i], str(o[i]), str(h[i]), str(l[i]), str(c[i]), str(v[i]), t[i] + H - 1] for i in range(len(t))]

    def handle(request):
        start = int(request.url.params.get("startTime", 0)); end = int(request.url.params.get("endTime", 10**15))
        interval = request.url.params["interval"]
        if interval == "1m":
            return httpx.Response(200, json=[])
        sel = [r for r in rows if start <= r[0] <= end][:int(request.url.params.get("limit", 1000))]
        return httpx.Response(200, json=sel)
    return handle, t


def test_backtest_cli_store_and_api(env):
    from app.backtest.__main__ import backtest, store
    handle, t = history_handler()
    p = BinanceProvider("https://s.test", "https://f.test", client=httpx.Client(transport=httpx.MockTransport(handle)))
    now = datetime.fromtimestamp((t[-1] + H) / 1000 + 5, tz=timezone.utc)
    res = backtest(p, "TESTUSDT", "spot", days=25, now=now)
    assert res["kind"] == "backtest" and res["bars"] > 500 and res["data_source"] == "Binance Spot"
    rid = store(res)
    from app.main import create_app
    with TestClient(create_app()) as c:
        runs = c.get("/api/backtests").json()["runs"]
        assert runs[0]["id"] == rid and runs[0]["symbol"] == "TESTUSDT"
        full = c.get(f"/api/backtests/{rid}").json()
        assert {"splits", "walk_forward", "trades", "assumptions", "disclaimer"} <= set(full)
        assert c.get("/api/backtests/missing").status_code == 404
        assert c.get("/api/performance?kind=backtest").json()["runs"][0]["id"] == rid


def test_prospective_performance_only_counts_finished_signals(env):
    s = next(db.get_session())
    row = stored(s)                                   # active, no outcome
    from app.main import create_app
    with TestClient(create_app()) as c:
        p = c.get("/api/performance").json()
        assert p["kind"] == "prospective" and p["closed_signals"] == 0 and p["open_or_unfilled"] == 1
        assert "No accuracy rate is claimed" in p["claim_policy"]
        row.outcome = {"net_r": -1.1, "exit": "stop"}; row.lifecycle = "stopped"; s.commit()
        p = c.get("/api/performance").json()
        assert p["closed_signals"] == 1 and p["metrics"]["total_r"] == -1.1 and p["metrics"]["warnings"]
        assert c.get("/api/performance?kind=paper").json()["available"] is False
