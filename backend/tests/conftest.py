import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import get_settings


@pytest.fixture(autouse=True)
def _isolate_from_server_env(monkeypatch):
    """Tests must not pick up real secrets/integrations from a deployment's .env file."""
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY",
              "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "LEMONSQUEEZY_WEBHOOK_SECRET", "ADMIN_EMAILS"):
        monkeypatch.setenv(f"TRADEAI_{k}", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
