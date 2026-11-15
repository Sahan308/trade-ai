"""Minimal SMTP mailer (STARTTLS on 587, or SSL on 465). Disabled when TRADEAI_SMTP_HOST is empty."""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from .config import get_settings

log = logging.getLogger("tradeai.mail")


def enabled() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.mail_from)


def send(to: str, subject: str, text: str, html: str | None = None) -> bool:
    s = get_settings()
    if not enabled():
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.mail_from, to, subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        ctx = ssl.create_default_context()
        if s.smtp_port == 465:
            with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, context=ctx, timeout=15) as smtp:
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
                smtp.starttls(context=ctx)
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("Email to recipient failed: %s", exc.__class__.__name__)
        return False
