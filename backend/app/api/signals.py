"""Signal endpoints (read-only). Signals are produced by the scanner (`python -m app.scan`)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Signal
from ..signals.store import to_api

router = APIRouter(prefix="/api/signals", tags=["signals"])
NOTE = ("Analysis only — TRADE-AI never places trades. The score is a heuristic, not a win probability. "
        "No accuracy rate is claimed: outcomes are not yet tracked (Milestone 5).")


@router.get("", summary="Recent LONG/SHORT signals")
def recent(symbol: str | None = Query(None, pattern=r"^[A-Za-z0-9]{2,15}USDT$"), side: Literal["LONG", "SHORT"] | None = None,
           limit: int = Query(20, ge=1, le=100), session: Session = Depends(get_session)):
    q = select(Signal).where(Signal.side.in_(["LONG", "SHORT"]))
    if symbol:
        q = q.where(Signal.symbol == symbol.upper())
    if side:
        q = q.where(Signal.side == side)
    rows = session.scalars(q.order_by(Signal.created_at.desc()).limit(limit)).all()
    return {"signals": [to_api(r) for r in rows], "note": NOTE}


@router.get("/history", summary="All evaluations, including NO TRADE, newest first")
def history(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
            side: Literal["LONG", "SHORT", "NO TRADE"] | None = None, session: Session = Depends(get_session)):
    q = select(Signal)
    cq = select(func.count()).select_from(Signal)
    if side:
        q, cq = q.where(Signal.side == side), cq.where(Signal.side == side)
    total = session.scalar(cq)
    rows = session.scalars(q.order_by(Signal.created_at.desc()).offset(offset).limit(limit)).all()
    return {"total": total, "offset": offset, "limit": limit, "items": [to_api(r) for r in rows], "note": NOTE}


@router.get("/{signal_id}", summary="One signal with its full evidence and strategy snapshot")
def one(signal_id: str, session: Session = Depends(get_session)):
    row = session.get(Signal, signal_id)
    if row is None:
        raise HTTPException(404, "Signal not found")
    return {**to_api(row), "note": NOTE}
