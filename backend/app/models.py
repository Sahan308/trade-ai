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
    outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # simulated result once the lifecycle ends


IMMUTABLE_SIGNAL_FIELDS = {c for c in ("id", "fingerprint", "created_at", "generated_at", "symbol", "market", "timeframe", "side",
                                      "strategy", "strategy_version", "config_hash", "score", "data_as_of", "expires_at", "payload")}

from sqlalchemy import ForeignKey, UniqueConstraint, event, inspect as _inspect  # noqa: E402


class SignalEvent(Base):
    """Append-only lifecycle events (triggered, tp1_hit, stopped, …)."""
    __tablename__ = "signal_events"
    __table_args__ = (UniqueConstraint("signal_id", "seq"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[float | None] = mapped_column(JSON, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Alert(Base):
    """In-app alerts (new signals and lifecycle changes). Global until accounts exist (Milestone 7)."""
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    signal_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("signals.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)


@event.listens_for(Signal, "before_update")
def _signals_are_immutable(mapper, connection, target):
    state = _inspect(target)
    changed = {a.key for a in state.attrs if a.history.has_changes()}
    blocked = changed & IMMUTABLE_SIGNAL_FIELDS
    if blocked:
        raise ValueError(f"Signals are immutable; attempted to change {sorted(blocked)}")


class BacktestRun(Base):
    """Stored backtest. Backtests are never mixed with paper or prospective (live) results."""
    __tablename__ = "backtest_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="backtest")
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    data_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)


class User(Base):
    """An account. Passwords are stored only as scrypt hashes. `plan` is "trial" until billing exists."""
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(16), nullable=False, default="trial")
    subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subscription_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subscription_renews_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customer_portal_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SignalUnlock(Base):
    """A user revealing one signal's full trade levels. Trial usage = number of unlocks (server-side)."""
    __tablename__ = "signal_unlocks"
    __table_args__ = (UniqueConstraint("user_id", "signal_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PageView(Base):
    """Daily aggregate page views per path. No cookies, IPs or user agents are stored."""
    __tablename__ = "page_views"
    __table_args__ = (UniqueConstraint("day", "path"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(64), nullable=False)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visitors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DailyVisitor(Base):
    """One row per (day, path, salted hash). The salt rotates daily and is never stored, so hashes can't be
    linked across days or reversed to an IP. Rows older than 2 days are deleted."""
    __tablename__ = "daily_visitors"
    __table_args__ = (UniqueConstraint("day", "path", "visitor"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(64), nullable=False)
    visitor: Mapped[str] = mapped_column(String(32), nullable=False)
