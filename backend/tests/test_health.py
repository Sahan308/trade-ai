from app import db


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["components"]["database"]["status"] == "ok"
    assert body["environment"] == "test"
    assert body["time_utc"].endswith("Z") or "+00:00" in body["time_utc"]
    assert r.headers["X-Request-ID"]


def test_health_reports_database_down(client, monkeypatch):
    monkeypatch.setattr("app.api.health.check_database", lambda: (False, "OperationalError"))
    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["components"]["database"] == {"status": "error", "error": "OperationalError"}


def test_check_database_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("no db")
    monkeypatch.setattr(db, "get_engine", boom)
    assert db.check_database() == (False, "RuntimeError")
