"""Account endpoints and the server-side free trial (Milestone 7). Billing is not implemented."""
import re
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import hash_password, issue_token, require_user, verify_password
from ..config import get_settings
from ..db import get_session
from ..models import AuditLog, PasswordReset, Signal, SignalUnlock, User
from ..access import LIVE, view

router = APIRouter(tags=["accounts"])

# Per-account sign-in throttle (in-process): 5 failed attempts per 15 minutes locks that email for the rest of the window.
_FAILS: dict[str, list[float]] = {}
_WINDOW, _MAX_FAILS = 15 * 60, 5
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


def _recent_fails(email: str) -> list[float]:
    now = time.time()
    fails = [t for t in _FAILS.get(email, []) if now - t < _WINDOW]
    _FAILS[email] = fails
    return fails
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
    sub = None
    if user.subscription_id:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        sub = {"status": user.subscription_status, "renews_at": iso(user.subscription_renews_at),
               "ends_at": iso(user.subscription_ends_at), "portal_url": user.customer_portal_url}
    return {"id": user.id, "email": user.email, "created_at": user.created_at.isoformat(), "usage": usage(session, user),
            "subscription": sub, "is_admin": user.email.lower() in get_settings().admin_emails}


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
    email = body.email.strip().lower()
    fails = _recent_fails(email)
    if len(fails) >= _MAX_FAILS:
        wait = int(_WINDOW - (time.time() - fails[0])) + 1
        raise HTTPException(429, f"Too many failed sign-in attempts. Try again in {max(1, wait // 60)} minutes.", headers={"Retry-After": str(wait)})
    user = session.scalar(select(User).where(User.email == email))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH) and user is not None
    if not ok:
        fails.append(time.time())
        raise HTTPException(401, "Email or password is incorrect")
    _FAILS.pop(email, None)
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


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/api/auth/password", summary="Change password (signed in)")
def change_password(body: PasswordChange, user: User = Depends(require_user), session: Session = Depends(get_session)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    session.add(AuditLog(actor=user.id, action="account.password_changed", target=user.id))
    session.commit()
    return {"ok": True}


class Confirm(BaseModel):
    password: str = Field(max_length=128)


@router.post("/api/auth/delete", summary="Delete the account and its unlocks")
def delete_account(body: Confirm, user: User = Depends(require_user), session: Session = Depends(get_session)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Password is incorrect")
    if user.plan != "trial" and user.subscription_status in ("active", "on_trial", "past_due"):
        raise HTTPException(409, "Cancel your subscription first (Manage subscription), then delete the account.")
    session.query(SignalUnlock).filter(SignalUnlock.user_id == user.id).delete()
    session.query(PasswordReset).filter(PasswordReset.user_id == user.id).delete()
    from ..models import PushSubscription
    session.query(PushSubscription).filter(PushSubscription.user_id == user.id).update({"user_id": None})
    session.add(AuditLog(actor=user.id, action="account.deleted", target=user.id))
    session.delete(user)
    session.commit()
    return {"ok": True}


# ---- Password reset by email ----
import hashlib as _hashlib  # noqa: E402
import secrets as _secrets  # noqa: E402
from datetime import datetime as _dt, timedelta as _td, timezone as _tz  # noqa: E402

from .. import mailer  # noqa: E402

RESET_TTL = _td(minutes=30)


@router.get("/api/auth/config", summary="Which account features are switched on")
def auth_config():
    return {"password_reset": mailer.enabled()}


class Forgot(BaseModel):
    email: str = Field(max_length=254)


@router.post("/api/auth/forgot", summary="Email a password-reset link (always answers the same)")
def forgot(body: Forgot, session: Session = Depends(get_session)):
    if not mailer.enabled():
        raise HTTPException(503, "Password reset by email isn't available yet")
    email = body.email.strip().lower()
    user = session.scalar(select(User).where(User.email == email))
    if user is not None:
        recent = session.scalar(select(func.count()).select_from(PasswordReset).where(
            PasswordReset.user_id == user.id, PasswordReset.created_at > _dt.now(_tz.utc) - _td(hours=1))) or 0
        if recent < 3:   # at most 3 emails per hour per account
            token = _secrets.token_urlsafe(32)
            session.add(PasswordReset(user_id=user.id, token_hash=_hashlib.sha256(token.encode()).hexdigest(),
                                      expires_at=_dt.now(_tz.utc) + RESET_TTL))
            session.commit()
            link = f"{get_settings().public_site_url}#/reset?token={token}"
            mailer.send(user.email, "Reset your TRADE-AI password",
                        f"Someone asked to reset the password for your TRADE-AI account.\n\n"
                        f"Open this link within 30 minutes to choose a new password:\n{link}\n\n"
                        f"If it wasn't you, ignore this email: your password stays the same.")
    # Same answer whether or not the account exists, so this can't be used to discover emails.
    return {"ok": True, "message": "If an account exists for that email, a reset link is on its way."}


class Reset(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/api/auth/reset", summary="Set a new password with a reset token")
def reset(body: Reset, session: Session = Depends(get_session)):
    th = _hashlib.sha256(body.token.encode()).hexdigest()
    pr = session.scalar(select(PasswordReset).where(PasswordReset.token_hash == th))
    exp = None if pr is None else (pr.expires_at if pr.expires_at.tzinfo else pr.expires_at.replace(tzinfo=_tz.utc))
    if pr is None or pr.used_at is not None or exp < _dt.now(_tz.utc):
        raise HTTPException(400, "This reset link is invalid or has expired. Request a new one.")
    user = session.get(User, pr.user_id)
    user.password_hash = hash_password(body.new_password)
    pr.used_at = _dt.now(_tz.utc)
    session.add(AuditLog(actor=user.id, action="account.password_reset", target=user.id))
    session.commit()
    _FAILS.pop(user.email, None)
    return {"token": issue_token(user.id), "user": me(session, user)}
