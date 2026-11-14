"""ORM models. Tables are introduced only when a milestone needs them; schema changes go through Alembic."""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class AuditLog(Base):
    """Append-only record of important account/configuration changes (Security requirement)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)       # e.g. "system" or a user id later
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target: Mapped[str | None] = mapped_column(String(256), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Signal(Base):
    """One engine output (LONG, SHORT or NO TRADE). Immutable once written: evidence, levels and the strategy
    snapshot can never change. Only `lifecycle` may be updated later (Milestone 5 lifecycle tracking)."""

    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)  # one row per unique setup
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)   # full engine output incl. evidence + config snapshot


IMMUTABLE_SIGNAL_FIELDS = {c for c in ("id", "fingerprint", "created_at", "generated_at", "symbol", "market", "timeframe", "side",
                                      "strategy", "strategy_version", "config_hash", "score", "data_as_of", "expires_at", "payload")}

from sqlalchemy import event, inspect as _inspect  # noqa: E402


@event.listens_for(Signal, "before_update")
def _signals_are_immutable(mapper, connection, target):
    state = _inspect(target)
    changed = {a.key for a in state.attrs if a.history.has_changes()}
    blocked = changed & IMMUTABLE_SIGNAL_FIELDS
    if blocked:
        raise ValueError(f"Signals are immutable; attempted to change {sorted(blocked)}")
