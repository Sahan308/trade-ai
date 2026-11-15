import httpx

from app.config import get_settings
from app.models import Signal
from app.notify import format_signal, send_telegram


def row(**kw):
    d = dict(id="x", symbol="BTCUSDT", market="spot", timeframe="1H", side="LONG", score=72)
    d.update(kw)
    return Signal(**d)


def test_message_is_a_teaser_without_levels():
    msg = format_signal(row())
    assert "LONG" in msg and "BTC/USDT" in msg and "72/100" in msg and "not a win probability" in msg
    assert "stop" not in msg.lower().replace("entry, stop and targets are in the app", "")


def test_disabled_without_config(monkeypatch):
    monkeypatch.setenv("TRADEAI_TELEGRAM_BOT_TOKEN", ""); get_settings.cache_clear()
    assert send_telegram("hi") is False


def test_sends_and_survives_errors(monkeypatch):
    monkeypatch.setenv("TRADEAI_TELEGRAM_BOT_TOKEN", "123:abc"); monkeypatch.setenv("TRADEAI_TELEGRAM_CHAT_ID", "@chan"); get_settings.cache_clear()
    seen = {}

    def ok(req):
        seen["url"], seen["body"] = str(req.url), req.content
        return httpx.Response(200, json={"ok": True})
    assert send_telegram("hello", httpx.Client(transport=httpx.MockTransport(ok))) is True
    assert seen["url"].endswith("/bot123:abc/sendMessage") and b"@chan" in seen["body"]
    assert send_telegram("hello", httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403)))) is False
    def boom(req): raise httpx.ConnectError("down")
    assert send_telegram("hello", httpx.Client(transport=httpx.MockTransport(boom))) is False
    get_settings.cache_clear()
