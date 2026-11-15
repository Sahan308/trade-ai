"""Where signal alerts are delivered: browser push subscriptions and the email opt-in."""
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import mailer
from ..auth import optional_user, require_user
from ..config import get_settings
from ..db import get_session
from ..models import PushSubscription, User

router = APIRouter(tags=["alerts"])
# Only real browser push services; stops the endpoint being used to make the server call arbitrary URLs.
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com", "notify.windows.com", "push.services.mozilla.com")


class Keys(BaseModel):
    p256dh: str = Field(max_length=255)
    auth: str = Field(max_length=255)


class Sub(BaseModel):
    endpoint: str = Field(max_length=1024)
    keys: Keys


class Unsub(BaseModel):
    endpoint: str = Field(max_length=1024)


@router.get("/api/alerts/delivery", summary="Which alert channels are available")
def delivery(user: User | None = Depends(optional_user)):
    s = get_settings()
    return {"push_public_key": s.vapid_public_key or None, "email_available": mailer.enabled(),
            "email_alerts": bool(user and user.email_alerts)}


@router.post("/api/alerts/push", status_code=201, summary="Subscribe this browser to new-signal notifications")
def subscribe(body: Sub, session: Session = Depends(get_session), user: User | None = Depends(optional_user)):
    if not get_settings().vapid_public_key:
        raise HTTPException(503, "Browser notifications aren't available")
    u = urlparse(body.endpoint)
    if u.scheme != "https" or not any(u.hostname == h or (u.hostname or "").endswith("." + h) for h in PUSH_HOSTS):
        raise HTTPException(422, "Unsupported push service")
    row = session.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if row is None:
        row = PushSubscription(endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth)
        session.add(row)
    row.p256dh, row.auth = body.keys.p256dh, body.keys.auth
    if user:
        row.user_id = user.id
    session.commit()
    return {"ok": True}


@router.post("/api/alerts/push/remove", summary="Unsubscribe this browser")
def unsubscribe(body: Unsub, session: Session = Depends(get_session)):
    session.execute(delete(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    session.commit()
    return {"ok": True}


class EmailPref(BaseModel):
    enabled: bool


@router.post("/api/alerts/email", summary="Turn new-signal emails on or off")
def email_pref(body: EmailPref, user: User = Depends(require_user), session: Session = Depends(get_session)):
    if body.enabled and not mailer.enabled():
        raise HTTPException(503, "Email alerts aren't available yet")
    user.email_alerts = body.enabled
    session.commit()
    return {"email_alerts": user.email_alerts}
