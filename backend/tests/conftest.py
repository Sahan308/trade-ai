import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import get_settings


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADEAI_ENV", "test")
    monkeypatch.setenv("TRADEAI_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("TRADEAI_CORS_ORIGINS", "http://localhost:8080")
    get_settings.cache_clear()
    db.reset_engine()
    from app.main import create_app

    with TestClient(create_app(), raise_server_exceptions=False) as c:
        yield c
    db.reset_engine()
    get_settings.cache_clear()
