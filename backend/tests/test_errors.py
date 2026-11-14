from fastapi import Query


def test_unknown_route_uses_error_envelope(client):
    r = client.get("/does-not-exist")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "not_found" and err["request_id"]


def test_method_not_allowed(client):
    r = client.post("/health")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"


def test_validation_and_internal_errors(client):
    app = client.app

    @app.get("/_test/validate")
    def validate(n: int = Query(..., ge=1)):
        return {"n": n}

    @app.get("/_test/boom")
    def boom():
        raise RuntimeError("secret internals")

    r = client.get("/_test/validate?n=0")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"

    r = client.get("/_test/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "secret" not in r.text  # no internal details leak


def test_cors_allows_configured_origin_only(client):
    ok = client.get("/health", headers={"Origin": "http://localhost:8080"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:8080"
    bad = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers
