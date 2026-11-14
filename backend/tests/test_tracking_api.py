"""Tracker + alerts + risk endpoints, against SQLite built from the migrations."""
from datetime import datetime, timezone

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app import db
from app.config import get_settings
from app.models import Alert, Signal, SignalEvent
from app.providers.binance import BinanceProvider
from app.signals.store import save
from app.signals.tracker import alert_for_new_signal, apply
from tests.test_lifecycle import H, T0, at_end, bars, sig


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADEAI_DATABASE_URL", f"sqlite:///{tmp_path / 'trk.db'}")
    get_settings.cache_clear(); db.reset_engine()
    command.upgrade(Config("alembic.ini"), "head")
    yield
    db.reset_engine(); get_settings.cache_clear()


def stored(session):
    payload = {**sig(), "symbol": "TESTUSDT", "market": "spot", "strategy": "smc_trend_pullback", "strategy_version": "1.0.0",
               "config_hash": "x", "lifecycle": "active", "generated_at": datetime.fromtimestamp(T0 / 1000, tz=timezone.utc).isoformat(),
               "score": 70, "fingerprint": "TESTUSDT|spot|1H|LONG|test"}
    row, _ = save(session, payload)
    return row


def test_tracker_appends_events_idempotently_and_raises_alerts(env):
    s = next(db.get_session())
    row = stored(s)
    alert_for_new_signal(s, row); s.commit()
    part = bars([(101, 101.2, 99.8, 100.5), (100.5, 102.5, 100.2, 102.2)])
    assert [e["type"] for e in apply(s, row, part, at_end(part))] == ["triggered", "tp1_hit"]
    assert row.lifecycle == "target_reached"
    assert apply(s, row, part, at_end(part)) == []                     # re-running adds nothing
    full = bars([(101, 101.2, 99.8, 100.5), (100.5, 102.5, 100.2, 102.2), (102, 102.1, 97.5, 97.8)])
    assert [e["type"] for e in apply(s, row, full, at_end(full))] == ["stopped"]
    assert row.lifecycle == "stopped" and row.outcome["simulated"] is True
    assert [e.seq for e in s.query(SignalEvent).order_by(SignalEvent.seq)] == [1, 2, 3]
    kinds = [a.kind for a in s.query(Alert).order_by(Alert.id)]
    assert kinds == ["new_signal", "triggered", "tp1_hit", "stopped"]
    assert "no order has been placed" in s.query(Alert).first().message


def test_events_and_alerts_api(env):
    s = next(db.get_session())
    row = stored(s)
    alert_for_new_signal(s, row); s.commit()
    b = bars([(101, 101.2, 99.8, 100.5), (100.5, 102.5, 97.5, 101)])
    apply(s, row, b, at_end(b))
    from app.main import create_app
    with TestClient(create_app()) as c:
        ev = c.get(f"/api/signals/{row.id}/events").json()
        assert [e["type"] for e in ev["events"]] == ["triggered", "stopped"] and ev["events"][1]["detail"]["ambiguous_same_candle"]
        assert ev["lifecycle"] == "stopped" and ev["outcome"]["gross_r"] == -1
        al = c.get("/api/alerts").json()["alerts"]
        assert [a["kind"] for a in al] == ["stopped", "triggered", "new_signal"]
        assert c.get(f"/api/alerts?after_id={al[1]['id']}").json()["alerts"][0]["kind"] == "stopped"
        assert c.get("/api/signals/nope/events").status_code == 404
        d = c.get(f"/api/signals/{row.id}").json()
        assert d["lifecycle"] == "stopped" and d["outcome"]["exit"] == "stop"


SPOT_INFO = {"symbols": [{"symbol": "BTCUSDT", "filters": [
    {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"}, {"filterType": "LOT_SIZE", "stepSize": "0.00001000", "minQty": "0.00001000"},
    {"filterType": "NOTIONAL", "minNotional": "5.00000000"}]}]}
FUT_INFO = {"symbols": [{"symbol": "SOLUSDT", "maintMarginPercent": "2.5000", "filters": [
    {"filterType": "PRICE_FILTER", "tickSize": "0.0100"}, {"filterType": "LOT_SIZE", "stepSize": "0.01", "minQty": "0.01"},
    {"filterType": "MIN_NOTIONAL", "notional": "5"}]}]}


def spec_handler(request):
    p = request.url.path
    if p == "/api/v3/exchangeInfo":
        return httpx.Response(200, json=SPOT_INFO)
    if p == "/fapi/v1/exchangeInfo":
        return httpx.Response(200, json=FUT_INFO)
    if p == "/fapi/v1/premiumIndex":
        return httpx.Response(200, json={"symbol": "SOLUSDT", "markPrice": "75", "indexPrice": "75", "lastFundingRate": "0.0001",
                                         "nextFundingTime": T0 + 8 * H, "time": T0})
    return httpx.Response(404, json={})


def test_specs_and_size_endpoints(env):
    from app.main import create_app
    p = BinanceProvider("https://s.test", "https://f.test", client=httpx.Client(transport=httpx.MockTransport(spec_handler)))
    with TestClient(create_app(provider=p)) as c:
        sp = c.get("/api/markets/BTCUSDT/specs?market=spot").json()
        assert sp == {"symbol": "BTCUSDT", "market": "spot", "tick_size": 0.01, "step_size": 0.00001, "min_qty": 0.00001,
                      "min_notional": 5.0, "mmr": None, "source": "Binance Spot"}
        fut = c.get("/api/markets/SOLUSDT/specs?market=futures").json()
        assert fut["mmr"] == 0.025 and fut["min_notional"] == 5.0
        r = c.get("/api/risk/size?balance=1000&risk_pct=1&entry=75&stop=77&side=SHORT&market=futures&leverage=5&symbol=SOLUSDT&hold_hours=24").json()
        assert r["valid"] and r["specs"]["step_size"] == 0.01 and round(r["qty"], 2) == r["qty"]
        assert r["liquidation_price"] == pytest.approx(75 * (1 + 0.2 - 0.025)) and r["funding_cost"] < 0
        bad = c.get("/api/risk/size?balance=1000&risk_pct=1&entry=75&stop=77&side=LONG").json()
        assert not bad["valid"]
        assert c.get("/api/risk/size?balance=-1&risk_pct=1&entry=1&stop=0.9").status_code == 422
        assert c.get("/api/markets/ETHUSDT/specs?market=futures").json()["error"]["code"] == "provider_bad_request"
