"""Persistence for engine outputs. Insert-only; a unique fingerprint stops the same setup being stored twice."""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Signal


def _dt(s):
    return datetime.fromisoformat(s) if s else None


def save(session: Session, result: dict) -> tuple[Signal, bool]:
    """Return (row, created). If the fingerprint already exists, the existing row is returned unchanged."""
    existing = session.scalar(select(Signal).where(Signal.fingerprint == result["fingerprint"]))
    if existing:
        return existing, False
    row = Signal(id=str(uuid.uuid4()), fingerprint=result["fingerprint"], generated_at=_dt(result["generated_at"]),
                 symbol=result["symbol"], market=result["market"], timeframe=result["timeframe"], side=result["side"],
                 strategy=result["strategy"], strategy_version=result["strategy_version"], config_hash=result["config_hash"],
                 lifecycle=result["lifecycle"], score=result.get("score"), data_as_of=_dt(result.get("data_as_of")),
                 expires_at=_dt(result.get("expires_at")), payload=result)
    session.add(row)
    try:
        session.commit()
    except IntegrityError:            # concurrent writer stored it first
        session.rollback()
        return session.scalar(select(Signal).where(Signal.fingerprint == result["fingerprint"])), False
    return row, True


def to_api(row: Signal) -> dict:
    p = dict(row.payload)
    p.update(id=row.id, lifecycle=row.lifecycle, created_at=row.created_at.isoformat() if row.created_at else None)
    return p
