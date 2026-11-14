"""Milestone 7: accounts, server-side 3-signal trial and level hiding."""
import uuid
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app import db
from app.auth import hash_password, issue_token, read_token, verify_password
from app.config import Settings, get_settings
from app.models import Alert, Signal
from tests.test_signals_api import a_signal


@pytest.fixture()
def c(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADEAI_DATABASE_URL", f"sqlite:///{tmp_path / 'acc.db'}")
    monkeypatch.setenv("TRADEAI_ENV", "test")
    get_settings.cache_clear(); db.reset_engine()
    command.upgrade(Config("alembic.ini"), "head")
    from app.main import create_app
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client
    db.reset_engine(); get_settings.cache_clear()


def live_signals(n, lifecycle="active"):
    s = next(db.get_session())
    base = a_signal()
    ids = []
    for i in range(n):
        sid = str(uuid.uuid4())
        s.add(Signal(id=sid, fingerprint=f"fp-{sid}", generated_at=datetime.now(timezone.utc), symbol="BTCUSDT", market="spot",
                     timeframe="1H", side=base["side"], strategy=base["strategy"], strategy_version=base["strategy_version"],
                     config_hash="x", lifecycle=lifecycle, score=base.get("score"), payload=base))
        s.add(Alert(signal_id=sid, kind="new_signal", symbol="BTCUSDT", title="New", message="Entry 1–2, stop 0.5"))
        ids.append(sid)
    s.commit(); s.close()
    return ids


def signup(c, email="a@example.com"):
    r = c.post("/api/auth/register", json={"email": email, "password": "correct horse"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_password_hash_and_token_roundtrip():
    h = hash_password("secret-pass")
    assert h.startswith("scrypt$") and "secret-pass" not in h
    assert verify_password("secret-pass", h) and not verify_password("wrong-pass", h)
    t = issue_token("u1")
    assert read_token(t) == "u1"
    assert read_token(t[:-2] + "xx") is None and read_token("garbage") is None


def test_production_requires_real_secret(monkeypatch):
    with pytest.raises(ValueError):
        Settings(env="production", cors_origins="https://x.example", auth_secret="short")
    Settings(env="production", cors_origins="https://x.example", auth_secret="k" * 40)


def test_register_login_me(c):
    h = signup(c)
    assert c.post("/api/auth/register", json={"email": "A@example.com", "password": "correct horse"}).status_code == 409
    assert c.post("/api/auth/register", json={"email": "nope", "password": "correct horse"}).status_code == 422
    assert c.post("/api/auth/register", json={"email": "b@example.com", "password": "short"}).status_code == 422
    assert c.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong pass"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "a@example.com", "password": "correct horse"}).status_code == 200
    me = c.get("/api/auth/me", headers=h).json()
    assert me["email"] == "a@example.com" and me["usage"] == {"plan": "trial", "used": 0, "limit": 3, "remaining": 3}
    assert "password_hash" not in me
    assert c.get("/api/auth/me").status_code == 401


def test_live_levels_hidden_until_unlocked_and_trial_enforced(c):
    ids = live_signals(4)
    anon = c.get("/api/signals").json()["signals"]
    assert all(s["locked"] and "stop" not in s and "entry_low" not in s and "targets" not in s for s in anon)
    assert all(s["side"] in ("LONG", "SHORT") and "score" in s for s in anon)
    assert "stop" not in c.get(f"/api/signals/{ids[0]}").json()
    assert all("Entry" not in a["message"] and a["locked"] for a in c.get("/api/alerts").json()["alerts"])
    assert c.post(f"/api/signals/{ids[0]}/unlock").status_code == 401

    h = signup(c)
    r = c.post(f"/api/signals/{ids[0]}/unlock", headers=h).json()
    assert r["signal"]["stop"] is not None and r["usage"]["remaining"] == 2
    assert c.post(f"/api/signals/{ids[0]}/unlock", headers=h).json()["usage"]["used"] == 1   # re-unlock is free
    got = c.get(f"/api/signals/{ids[0]}", headers=h).json()
    assert not got["locked"] and "stop" in got
    assert "stop" not in c.get(f"/api/signals/{ids[0]}").json()                            # still hidden for others
    for sid in ids[1:3]:
        assert c.post(f"/api/signals/{sid}/unlock", headers=h).status_code == 200
    r = c.post(f"/api/signals/{ids[3]}/unlock", headers=h)
    assert r.status_code == 402
    assert c.get("/api/usage", headers=h).json() == {"plan": "trial", "used": 3, "limit": 3, "remaining": 0}
    other = signup(c, "b@example.com")                                                       # usage is per account
    assert c.post(f"/api/signals/{ids[3]}/unlock", headers=other).status_code == 200


def test_finished_signals_are_public_and_free(c):
    [sid] = live_signals(1, lifecycle="stopped")
    d = c.get(f"/api/signals/{sid}").json()
    assert not d["locked"] and "stop" in d
    h = signup(c)
    assert c.post(f"/api/signals/{sid}/unlock", headers=h).json()["usage"]["used"] == 0


def test_cors_allows_auth_header(c):
    r = c.options("/api/auth/login", headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "POST",
                                              "Access-Control-Request-Headers": "authorization,content-type"})
    assert r.status_code == 200 and "authorization" in r.headers["access-control-allow-headers"].lower()
