from alembic import command
from alembic.config import Config

from app import db
from app.backup import backup, restore
from app.config import get_settings
from tests.test_accounts import live_signals


def _fresh(monkeypatch, path):
    monkeypatch.setenv("TRADEAI_DATABASE_URL", f"sqlite:///{path}")
    get_settings.cache_clear(); db.reset_engine()
    command.upgrade(Config("alembic.ini"), "head")


def test_backup_roundtrip_and_pruning(tmp_path, monkeypatch):
    _fresh(monkeypatch, tmp_path / "a.db")
    live_signals(3)
    out = tmp_path / "bk"
    files = [backup(str(out), keep=2) for _ in range(3)]
    assert len(list(out.glob("tradeai-*.jsonl.gz"))) <= 2 and files[-1].exists()
    _fresh(monkeypatch, tmp_path / "b.db")
    restore(str(files[-1]))
    s = next(db.get_session())
    from app.models import Alert, Signal
    assert s.query(Signal).count() == 3 and s.query(Alert).count() == 3
    s.close()
    db.reset_engine(); get_settings.cache_clear()
