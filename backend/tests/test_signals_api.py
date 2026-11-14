"""Persistence (insert-only, de-duplicated, immutable), scanner and /api/signals."""
from datetime import datetime, timezone

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app import db
from app.config import get_settings
from app.models import Signal
from app.providers.binance import BinanceProvider
from app.signals.store import save
from tests.fixtures import H, candles
from tests.test_engine import run, series


@pytest.fixture()
def env(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'sig.db'}"
    monkeypatch.setenv("TRADEAI_DATABASE_URL", url)
    monkeypatch.setenv("TRADEAI_MARKETS", "TESTUSDT:spot")
    get_settings.cache_clear(); db.reset_engine()
    command.upgrade(Config("alembic.ini"), "head")       # schema from migrations, not create_all
    yield
    db.reset_engine(); get_settings.cache_clear()


def a_signal():
    for seed in range(1, 120):
        for mirror in (False, True):
            r = run(series(seed, mirror=mirror))
            if r["side"] != "NO TRADE":
                return r
    raise AssertionError("fixtures produced no signal")


def test_save_dedupes_by_fingerprint(env):
    s = next(db.get_session())
    r = a_signal()
    row1, c1 = save(s, r)
    row2, c2 = save(s, r)
    assert c1 and not c2 and row1.id == row2.id
    assert s.query(Signal).count() == 1


def test_signals_are_immutable_except_lifecycle(env):
    s = next(db.get_session())
    row, _ = save(s, a_signal())
    row.lifecycle = "triggered"
    s.commit()                                           # allowed (Milestone 5 lifecycle)
    row.payload = {**row.payload, "stop": 0}
    with pytest.raises(ValueError, match="immutable"):
        s.commit()
    s.rollback()
    row.score = 1
    with pytest.raises(ValueError, match="immutable"):
        s.commit()


def test_api_lists_details_and_history(env):
    s = next(db.get_session())
    sig, _ = save(s, a_signal())
    nt = run(series(3, n=120))
    save(s, nt)
    from app.main import create_app
    with TestClient(create_app()) as c:
        recent = c.get("/api/signals").json()
        assert [x["id"] for x in recent["signals"]] == [sig.id] and "not a win probability" in recent["note"]
        d = c.get(f"/api/signals/{sig.id}").json()
        assert d["supporting"] and d["config"]["version"] == "1.0.0" and d["invalidation"]
        h = c.get("/api/signals/history").json()
        assert h["total"] == 2 and {x["side"] for x in h["items"]} == {sig.side, "NO TRADE"}
        assert c.get("/api/signals/history?side=NO TRADE").json()["total"] == 1
        assert c.get("/api/signals/nope").status_code == 404
        assert c.get("/api/signals?symbol=bad!").status_code == 422


def test_scanner_stores_once(env):
    t, o, h, l, c, v = candles(300, seed=3)

    def handler(request):
        rows = [[t[i], str(o[i]), str(h[i]), str(l[i]), str(c[i]), str(v[i]), t[i] + H - 1] for i in range(len(t))]
        return httpx.Response(200, json=rows)

    from app import scan
    p = BinanceProvider("https://s.test", "https://f.test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    now = datetime.fromtimestamp((t[-1] + H) / 1000 + 5, tz=timezone.utc)
    res = scan.evaluate_symbol(p, "TESTUSDT", "spot", now=now)
    assert res["side"] in ("LONG", "SHORT", "NO TRADE") and res["data_source"] == "Binance Spot"
    # scan_once uses wall-clock time → fixture data is stale → a NO TRADE evaluation is stored, exactly once
    first = scan.scan_once(p)
    second = scan.scan_once(p)
    assert first[0]["created"] and not second[0]["created"]
    assert first[0]["side"] == "NO TRADE"
