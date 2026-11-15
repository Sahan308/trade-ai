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


def notify_new_signal(row: Signal) -> bool:
    return send_telegram(format_signal(row))
