"""In-app alerts (read-only). Levels in alerts for locked live signals are hidden (Milestone 7)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access import LOCKED_MESSAGE, is_locked, unlocked_ids
from ..auth import optional_user
from ..db import get_session
from ..models import Alert, Signal, SignalEvent, User

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", summary="Recent alerts, newest first. Use after_id to fetch only new ones.")
def alerts(after_id: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), session: Session = Depends(get_session),
           user: User | None = Depends(optional_user)):
    rows = session.scalars(select(Alert).where(Alert.id > after_id).order_by(Alert.id.desc()).limit(limit)).all()
    ul = unlocked_ids(session, user)
    sigs = {s.id: s for s in session.scalars(select(Signal).where(Signal.id.in_({a.signal_id for a in rows if a.signal_id})))}
    hidden = {sid for sid, s in sigs.items() if is_locked(s, ul)}
    return {"alerts": [{"id": a.id, "created_at": a.created_at.isoformat(), "signal_id": a.signal_id, "kind": a.kind,
                        "symbol": a.symbol, "title": a.title, "message": LOCKED_MESSAGE if a.signal_id in hidden else a.message,
                        "locked": a.signal_id in hidden} for a in rows]}


@router.get("/signals/{signal_id}/events", summary="Lifecycle events and simulated outcome for one signal")
def events(signal_id: str, session: Session = Depends(get_session), user: User | None = Depends(optional_user)):
    row = session.get(Signal, signal_id)
    if row is None:
        raise HTTPException(404, "Signal not found")
    if is_locked(row, unlocked_ids(session, user)):
        return {"signal_id": signal_id, "lifecycle": row.lifecycle, "outcome": None, "events": [], "locked": True}
    evs = session.scalars(select(SignalEvent).where(SignalEvent.signal_id == signal_id).order_by(SignalEvent.seq)).all()
    return {"signal_id": signal_id, "lifecycle": row.lifecycle, "outcome": row.outcome,
            "events": [{"seq": e.seq, "type": e.type, "at": e.at.isoformat(), "price": e.price, "detail": e.detail} for e in evs],
            "locked": False}
