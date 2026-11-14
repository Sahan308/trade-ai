from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.config import get_settings


def test_upgrade_and_downgrade(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    monkeypatch.setenv("TRADEAI_DATABASE_URL", url)
    get_settings.cache_clear()
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    assert "audit_logs" in inspect(create_engine(url)).get_table_names()
    command.downgrade(cfg, "base")
    assert "audit_logs" not in inspect(create_engine(url)).get_table_names()
    get_settings.cache_clear()
