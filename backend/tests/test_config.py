import pytest
from pydantic import ValidationError

from app.config import Settings


def test_origins_split_from_comma_string(monkeypatch):
    monkeypatch.setenv("TRADEAI_CORS_ORIGINS", "http://a.test, http://b.test")
    assert Settings(_env_file=None).cors_origins == ["http://a.test", "http://b.test"]


def test_wildcard_cors_rejected_in_production(monkeypatch):
    monkeypatch.setenv("TRADEAI_ENV", "production")
    monkeypatch.setenv("TRADEAI_CORS_ORIGINS", "*")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("raw", ["postgres://u:p@h/db?sslmode=require", "postgresql://u:p@h/db?sslmode=require"])
def test_hosted_postgres_urls_use_psycopg(monkeypatch, raw):
    monkeypatch.setenv("TRADEAI_DATABASE_URL", raw)
    assert Settings(_env_file=None).database_url == "postgresql+psycopg://u:p@h/db?sslmode=require"
