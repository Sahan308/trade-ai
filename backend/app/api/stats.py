"""Privacy-friendly usage stats: aggregate page views + daily unique visitors.

A visitor is counted via sha256(daily_salt + ip + user_agent), truncated. The salt is derived from the server
secret and the date, never stored or exposed, so hashes are unlinkable across days. No cookies are used."""
import hashlib
import hmac
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import require_user
from ..config import get_settings
from ..db import get_session
from ..models import DailyVisitor, PageView, Signal, SignalUnlock, User

router = APIRouter(tags=["stats"])
PATH_RE = re.compile(r"^/[a-z0-9/_-]{0,63}$")


class Hit(BaseModel):
    path: str = Field(max_length=64)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@router.post("/api/stats/hit", status_code=204, include_in_schema=False)
def hit(body: Hit, request: Request, session: Session = Depends(get_session)):
    path = body.path.lower()
    if not PATH_RE.match(path) or request.headers.get("DNT") == "1" or request.headers.get("Sec-GPC") == "1":
        return None  # ignore junk paths and honour Do-Not-Track / Global Privacy Control
    day = _today()
    salt = hmac.new(get_settings().auth_secret.encode(), f"stats:{day}".encode(), hashlib.sha256).digest()
    ip = request.client.host if request.client else ""
    visitor = hashlib.sha256(salt + f"{ip}|{request.headers.get('user-agent', '')}".encode()).hexdigest()[:32]
    pv = session.scalar(select(PageView).where(PageView.day == day, PageView.path == path))
    if pv is None:
        pv = PageView(day=day, path=path, views=0, visitors=0)
        session.add(pv)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            pv = session.scalar(select(PageView).where(PageView.day == day, PageView.path == path))
    pv.views += 1
    session.add(DailyVisitor(day=day, path=path, visitor=visitor))
    try:
        session.flush()
        pv.visitors += 1
    except IntegrityError:
        session.rollback()
        pv = session.scalar(select(PageView).where(PageView.day == day, PageView.path == path))
        pv.views += 1
    old = (date.fromisoformat(day) - timedelta(days=2)).isoformat()
    session.execute(delete(DailyVisitor).where(DailyVisitor.day < old))
    session.commit()
    return None


@router.get("/api/stats/summary", summary="Usage summary (admins only)")
def summary(days: int = 30, user: User = Depends(require_user), session: Session = Depends(get_session)):
    if user.email.lower() not in get_settings().admin_emails:
        raise HTTPException(403, "Admins only")
    days = max(1, min(days, 365))
    since = (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat()
    rows = session.execute(select(PageView.day, func.sum(PageView.views), func.sum(PageView.visitors))
                           .where(PageView.day >= since).group_by(PageView.day).order_by(PageView.day)).all()
    pages = session.execute(select(PageView.path, func.sum(PageView.views), func.sum(PageView.visitors))
                            .where(PageView.day >= since).group_by(PageView.path)
                            .order_by(func.sum(PageView.views).desc()).limit(20)).all()
    cnt = lambda q: session.scalar(q) or 0  # noqa: E731
    return {
        "days": days,
        "daily": [{"day": d, "views": int(v), "visitors": int(u)} for d, v, u in rows],
        "pages": [{"path": p, "views": int(v), "visitors": int(u)} for p, v, u in pages],
        "totals": {
            "accounts": cnt(select(func.count()).select_from(User)),
            "paid": cnt(select(func.count()).select_from(User).where(User.plan != "trial")),
            "unlocks": cnt(select(func.count()).select_from(SignalUnlock)),
            "signals": cnt(select(func.count()).select_from(Signal)),
        },
        "note": "Visitors are counted once per page per day (no cookies; IPs are never stored).",
    }
