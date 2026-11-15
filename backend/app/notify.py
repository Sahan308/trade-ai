"""Telegram channel alerts for new LONG/SHORT signals.

Only a teaser is posted (pair, side, timeframe, setup score): trade levels stay inside the app, where they are
gated by the trial/subscription. Failures are logged and never break a scan."""
import logging

import httpx

from .config import get_settings
from .models import Signal

log = logging.getLogger("tradeai.notify")


def format_signal(row: Signal) -> str:
    s = get_settings()
    pair = row.symbol.replace("USDT", "/USDT")
    arrow = "🟢 LONG" if row.side == "LONG" else "🔴 SHORT"
    score = f"{row.score}/100" if row.score is not None else "n/a"
    return (f"<b>{arrow} · {pair}</b> ({row.market.capitalize()}, {row.timeframe})\n"
            f"Setup score: {score} (a checklist rating, not a win probability)\n\n"
            f"Entry, stop and targets are in the app:\n{s.public_site_url}#/signals\n\n"
            f"<i>Experimental strategy, analysis only, not financial advice. TRADE-AI never places trades.</i>")


def send_telegram(text: str, client: httpx.Client | None = None) -> bool:
    s = get_settings()
    if not s.telegram_bot_token or not s.telegram_chat_id:
        return False
    try:
        c = client or httpx.Client(timeout=10)
        r = c.post(f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage",
                   json={"chat_id": s.telegram_chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
        if r.status_code != 200:
            log.warning("Telegram send failed: HTTP %s %s", r.status_code, r.text[:200])
            return False
        return True
    except httpx.HTTPError as exc:
        log.warning("Telegram send failed: %s", exc.__class__.__name__)
        return False


def plain_text(row: Signal) -> tuple[str, str]:
    pair = row.symbol.replace("USDT", "/USDT")
    title = f"{'LONG' if row.side == 'LONG' else 'SHORT'} · {pair} ({row.timeframe})"
    body = f"Setup score {row.score}/100 (not a win probability). Open TRADE-AI for levels. Analysis only, not advice."
    return title, body


def send_push_all(row: Signal, session=None, webpush=None) -> int:
    """Send a Web Push notification to every subscribed browser. Expired subscriptions are deleted."""
    import json

    from sqlalchemy import select

    from .db import get_session
    from .models import PushSubscription
    s = get_settings()
    if not (s.vapid_private_key and s.vapid_public_key):
        return 0
    if webpush is None:
        from pywebpush import WebPushException, webpush as _wp  # noqa: F401
        webpush = _wp
    own = session is None
    session = session or next(get_session())
    title, body = plain_text(row)
    data = json.dumps({"title": title, "body": body, "url": f"{s.public_site_url}#/signals", "tag": f"signal-{row.id}"})
    sent = 0
    try:
        for sub in session.scalars(select(PushSubscription)).all():
            try:
                webpush(subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                        data=data, vapid_private_key=s.vapid_private_key, vapid_claims={"sub": s.vapid_subject}, ttl=3600)
                sent += 1
            except Exception as exc:  # pywebpush raises WebPushException with .response
                code = getattr(getattr(exc, "response", None), "status_code", None)
                if code in (404, 410):
                    session.delete(sub)
                else:
                    log.warning("Push failed: %s %s", exc.__class__.__name__, code)
        session.commit()
    finally:
        if own:
            session.close()
    return sent


def send_email_alerts(row: Signal, session=None) -> int:
    from sqlalchemy import select

    from . import mailer
    from .db import get_session
    from .models import User
    if not mailer.enabled():
        return 0
    own = session is None
    session = session or next(get_session())
    title, body = plain_text(row)
    s = get_settings()
    sent = 0
    try:
        for u in session.scalars(select(User).where(User.email_alerts.is_(True))).all():
            if mailer.send(u.email, f"TRADE-AI: {title}", f"{body}\n\n{s.public_site_url}#/signals\n\n"
                           f"Experimental strategy. TRADE-AI never places trades. Turn these emails off in Alerts → Notifications."):
                sent += 1
    finally:
        if own:
            session.close()
    return sent


def notify_new_signal(row: Signal) -> bool:
    for fn in (send_push_all, send_email_alerts):
        try:
            fn(row)
        except Exception as exc:  # never break a scan
            log.warning("%s failed: %s", fn.__name__, exc.__class__.__name__)
    return send_telegram(format_signal(row))
