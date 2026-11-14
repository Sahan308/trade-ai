"""Account endpoints and the server-side free trial (Milestone 7). Billing is not implemented."""
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import hash_password, issue_token, require_user, verify_password
from ..config import get_settings
from ..db import get_session
from ..models import AuditLog, Signal, SignalUnlock, User
from ..access import LIVE, view

router = APIRouter(tags=["accounts"])
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)


def usage(session: Session, user: User) -> dict:
    used = session.scalar(select(func.count()).select_from(SignalUnlock).where(SignalUnlock.user_id == user.id)) or 0
    limit = get_settings().trial_signals
    unlimited = user.plan != "trial"
    return {"plan": user.plan, "used": used, "limit": None if unlimited else limit,
            "remaining": None if unlimited else max(0, limit - used)}


def me(session: Session, user: User) -> dict:
    return {"id": user.id, "email": user.email, "created_at": user.created_at.isoformat(), "usage": usage(session, user)}


@router.post("/api/auth/register", status_code=201, summary="Create an account (starts the free trial)")
def register(body: Credentials, session: Session = Depends(get_session)):
    email = body.email.strip().lower()
    if not EMAIL.match(email):
        raise HTTPException(422, "Enter a valid email address")
    user = User(id=str(uuid.uuid4()), email=email, password_hash=hash_password(body.password), plan="trial")
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "An account with this email already exists")
    session.add(AuditLog(actor=user.id, action="account.created", target=user.id))
    session.commit()
    return {"token": issue_token(user.id), "user": me(session, user)}


@router.post("/api/auth/login", summary="Sign in")
def login(body: Credentials, session: Session = Depends(get_session)):
    user = session.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect")
    return {"token": issue_token(user.id), "user": me(session, user)}


@router.get("/api/auth/me", summary="Current account and trial usage")
def whoami(user: User = Depends(require_user), session: Session = Depends(get_session)):
    return me(session, user)


@router.get("/api/usage", summary="Trial usage for the signed-in account")
def get_usage(user: User = Depends(require_user), session: Session = Depends(get_session)):
    return usage(session, user)


@router.post("/api/signals/{signal_id}/unlock", summary="Reveal a signal's trade levels (uses one trial signal)")
def unlock(signal_id: str, user: User = Depends(require_user), session: Session = Depends(get_session)):
    row = session.get(Signal, signal_id)
    if row is None:
        raise HTTPException(404, "Signal not found")
    if row.side not in ("LONG", "SHORT"):
        raise HTTPException(400, "NO TRADE results have no levels to unlock")
    exists = session.scalar(select(SignalUnlock).where(SignalUnlock.user_id == user.id, SignalUnlock.signal_id == signal_id))
    if exists is None and row.lifecycle in LIVE and user.plan == "trial":
        u = usage(session, user)
        if u["remaining"] is not None and u["remaining"] <= 0:
            raise HTTPException(402, "Your free trial signals are used up. A subscription is needed to unlock more.")
        session.add(SignalUnlock(user_id=user.id, signal_id=signal_id))
        try:
            session.commit()
        except IntegrityError:  # concurrent double-click
            session.rollback()
    return {"signal": view(row, None), "usage": usage(session, user)}
