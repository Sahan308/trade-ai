"""Billing via Lemon Squeezy (merchant of record). TRADE-AI never sees card details.

Checkout happens on Lemon Squeezy's hosted page, opened by the frontend with `checkout[custom][user_id]`.
Lemon Squeezy then calls this webhook; the payload is verified with HMAC-SHA256 (X-Signature header)."""
import hashlib
import hmac
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_session
from ..models import AuditLog, User

router = APIRouter(tags=["billing"])
PAID_STATUSES = {"active", "on_trial", "past_due", "cancelled"}  # cancelled = still paid until ends_at; expired ends it


def _dt(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


@router.post("/api/billing/webhook", include_in_schema=False)
async def webhook(request: Request, session: Session = Depends(get_session)):
    secret = get_settings().lemonsqueezy_webhook_secret
    if not secret:
        raise HTTPException(503, "Billing is not configured")
    raw = await request.body()
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("X-Signature", "")):
        raise HTTPException(401, "Invalid signature")
    try:
        body = json.loads(raw)
        event = body["meta"]["event_name"]
        data = body["data"]
    except (ValueError, KeyError):
        raise HTTPException(400, "Malformed payload")
    if not event.startswith("subscription_") or data.get("type") != "subscriptions":
        return {"ignored": event}
    user_id = (body["meta"].get("custom_data") or {}).get("user_id")
    user = session.get(User, user_id) if user_id else None
    if user is None:
        return {"ignored": "unknown user"}
    a = data.get("attributes", {})
    updated = _dt(a.get("updated_at"))
    if user.subscription_updated_at and updated and _dt_aware(updated) < _dt_aware(user.subscription_updated_at) and user.subscription_id == str(data.get("id")):
        return {"ignored": "stale"}
    status = a.get("status")
    user.subscription_id = str(data.get("id"))
    user.subscription_status = status
    user.subscription_renews_at = _dt(a.get("renews_at"))
    user.subscription_ends_at = _dt(a.get("ends_at"))
    user.subscription_updated_at = updated
    user.customer_portal_url = (a.get("urls") or {}).get("customer_portal")
    user.plan = "pro" if status in PAID_STATUSES else "trial"
    session.add(AuditLog(actor="lemonsqueezy", action=f"billing.{event}", target=user.id, details={"status": status}))
    session.commit()
    return {"ok": True, "plan": user.plan}


def _dt_aware(d: datetime) -> datetime:
    from datetime import timezone
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
