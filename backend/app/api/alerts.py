"""In-app alerts (read-only). Global until user accounts exist."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Alert, Signal, SignalEvent

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", summary="Recent alerts, newest first. Use after_id to fetch only new ones.")
def alerts(after_id: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), session: Session = Depends(get_session)):
    rows = session.scalars(select(Alert).where(Alert.id > after_id).order_by(Alert.id.desc()).limit(limit)).all()
    return {"alerts": [{"id": a.id, "created_at": a.created_at.isoformat(), "signal_id": a.signal_id, "kind": a.kind,
                        "symbol": a.symbol, "title": a.title, "message": a.message} for a in rows]}


@router.get("/signals/{signal_id}/events", summary="Lifecycle events and simulated outcome for one signal")
def events(signal_id: str, session: Session = Depends(get_session)):
    row = session.get(Signal, signal_id)
    if row is None:
        raise HTTPException(404, "Signal not found")
    evs = session.scalars(select(SignalEvent).where(SignalEvent.signal_id == signal_id).order_by(SignalEvent.seq)).all()
    return {"signal_id": signal_id, "lifecycle": row.lifecycle, "outcome": row.outcome,
            "events": [{"seq": e.seq, "type": e.type, "at": e.at.isoformat(), "price": e.price, "detail": e.detail} for e in evs]}
