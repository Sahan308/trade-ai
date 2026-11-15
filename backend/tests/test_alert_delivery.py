from app.config import get_settings
from app.models import PushSubscription, Signal
from app.notify import send_push_all, send_email_alerts
from tests.test_accounts import c, signup  # noqa: F401  (fixture)
from app import db

EP = "https://fcm.googleapis.com/fcm/send/abc123"
KEYS = {"p256dh": "BPk" + "x" * 80, "auth": "y" * 22}


def test_push_subscribe_validation_and_delivery(c, monkeypatch):
    monkeypatch.setenv("TRADEAI_VAPID_PUBLIC_KEY", ""); get_settings.cache_clear()
    assert c.post("/api/alerts/push", json={"endpoint": EP, "keys": KEYS}).status_code == 503
    monkeypatch.setenv("TRADEAI_VAPID_PUBLIC_KEY", "PUB"); monkeypatch.setenv("TRADEAI_VAPID_PRIVATE_KEY", "PRIV"); get_settings.cache_clear()
    assert c.get("/api/alerts/delivery").json()["push_public_key"] == "PUB"
    assert c.post("/api/alerts/push", json={"endpoint": "https://evil.example.com/x", "keys": KEYS}).status_code == 422   # no SSRF
    assert c.post("/api/alerts/push", json={"endpoint": "http://fcm.googleapis.com/x", "keys": KEYS}).status_code == 422
    assert c.post("/api/alerts/push", json={"endpoint": EP, "keys": KEYS}).status_code == 201
    assert c.post("/api/alerts/push", json={"endpoint": EP, "keys": KEYS}).status_code == 201                         # idempotent
    gone = "https://updates.push.services.mozilla.com/wpush/v2/gone"
    c.post("/api/alerts/push", json={"endpoint": gone, "keys": KEYS})
    calls = []

    class Resp:
        status_code = 410

    class Gone(Exception):
        response = Resp()

    def fake(subscription_info, data, **kw):
        calls.append((subscription_info["endpoint"], data))
        if subscription_info["endpoint"] == gone:
            raise Gone()
    s = next(db.get_session())
    sig = Signal(id="s1", symbol="ETHUSDT", market="spot", timeframe="1H", side="SHORT", score=80)
    assert send_push_all(sig, session=s, webpush=fake) == 1
    assert len(calls) == 2 and "SHORT · ETH/USDT" in calls[0][1] and "entry" not in calls[0][1].lower()
    assert [p.endpoint for p in s.query(PushSubscription)] == [EP]        # expired one removed
    s.close()
    assert c.post("/api/alerts/push/remove", json={"endpoint": EP}).json() == {"ok": True}


def test_email_alert_opt_in(c, monkeypatch):
    h = signup(c)
    assert c.post("/api/alerts/email", headers=h, json={"enabled": True}).status_code == 503       # needs SMTP
    monkeypatch.setenv("TRADEAI_SMTP_HOST", "smtp.example.com"); monkeypatch.setenv("TRADEAI_MAIL_FROM", "x@example.com"); get_settings.cache_clear()
    assert c.post("/api/alerts/email", headers=h, json={"enabled": True}).json() == {"email_alerts": True}
    assert c.get("/api/alerts/delivery", headers=h).json()["email_alerts"] is True
    from app import mailer
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subj, text, html=None: sent.append((to, subj)) or True)
    s = next(db.get_session())
    assert send_email_alerts(Signal(id="s2", symbol="BTCUSDT", market="spot", timeframe="1H", side="LONG", score=70), session=s) == 1
    assert sent == [("a@example.com", "TRADE-AI: new LONG setup · BTC/USDT (1H)")]
    s.close()
    assert c.post("/api/alerts/email", json={"enabled": False}).status_code == 401
