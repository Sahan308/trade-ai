"""Branded HTML emails (table layout + inline styles so they render in Gmail, Outlook and Apple Mail).

Every email also has a plain-text part. No tracking pixels or remote images: the logo is drawn with text/CSS."""
from html import escape

BG, PANEL, LINE, TEXT, MUTED = "#0B1016", "#121B24", "#1F2C37", "#E8F0F5", "#91A3B0"
CYAN, TEAL, GREEN, RED = "#36D6E7", "#18B89A", "#35C98A", "#F16B75"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _button(href: str, label: str) -> str:
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 4px"><tr>'
            f'<td align="center" bgcolor="{CYAN}" style="border-radius:12px;background:{CYAN};'
            f'background-image:linear-gradient(90deg,{CYAN},{TEAL});box-shadow:0 0 18px rgba(54,214,231,.45)">'
            f'<a href="{escape(href)}" target="_blank" style="display:inline-block;padding:14px 28px;font-family:{FONT};'
            f'font-size:16px;font-weight:700;color:#06232A;text-decoration:none;border-radius:12px">{escape(label)}</a>'
            f'</td></tr></table>')


def _layout(preheader: str, inner: str, footer: str) -> str:
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light"><meta name="supported-color-schemes" content="dark light"><title>TRADE-AI</title></head>
<body style="margin:0;padding:0;background:{BG};-webkit-text-size-adjust:100%">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{BG}" style="background:{BG}">
<tr><td align="center" style="padding:28px 12px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px">
    <tr><td style="padding:0 4px 18px;font-family:{FONT}">
      <span style="display:inline-block;width:34px;height:34px;line-height:34px;text-align:center;border-radius:10px;background:{PANEL};border:1px solid {CYAN};color:{CYAN};font-weight:800;font-size:18px;vertical-align:middle">&#8599;</span>
      <span style="font-size:20px;font-weight:800;letter-spacing:.5px;color:{TEXT};vertical-align:middle;margin-left:8px">TRADE<span style="color:{CYAN}">-AI</span></span>
    </td></tr>
    <tr><td style="height:4px;line-height:4px;font-size:0;border-radius:4px 4px 0 0;background:{CYAN};background-image:linear-gradient(90deg,{TEAL},{CYAN},#7A8CFF)">&nbsp;</td></tr>
    <tr><td bgcolor="{PANEL}" style="background:{PANEL};border:1px solid {LINE};border-top:0;border-radius:0 0 18px 18px;padding:30px 28px;font-family:{FONT};color:{TEXT}">
      {inner}
    </td></tr>
    <tr><td style="padding:18px 8px 0;font-family:{FONT};font-size:12px;line-height:18px;color:{MUTED};text-align:center">
      {footer}<br>TRADE-AI is an analysis tool. It is not financial advice and never places trades.
    </td></tr>
  </table>
</td></tr></table></body></html>'''


def password_reset(link: str, ttl_minutes: int = 30) -> tuple[str, str, str]:
    subject = "Reset your TRADE-AI password"
    inner = f'''
      <div style="display:inline-block;padding:6px 12px;border-radius:999px;background:rgba(54,214,231,.12);border:1px solid rgba(54,214,231,.4);color:{CYAN};font-size:12px;font-weight:700;letter-spacing:.6px;text-transform:uppercase">Account security</div>
      <h1 style="margin:16px 0 10px;font-size:26px;line-height:32px;font-weight:800;color:{TEXT}">Reset your password</h1>
      <p style="margin:0 0 20px;font-size:16px;line-height:24px;color:#C9D6DF">Someone asked to reset the password for your TRADE-AI account. Click the button to choose a new one.</p>
      {_button(link, "Choose a new password")}
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:22px 0 0"><tr>
        <td style="padding:14px 16px;border-radius:12px;background:{BG};border:1px solid {LINE};font-size:14px;line-height:21px;color:{MUTED}">
          &#9201;&nbsp; This link works <b style="color:{TEXT}">once</b> and expires in <b style="color:{TEXT}">{ttl_minutes} minutes</b>.<br>
          &#128274;&nbsp; Didn't ask for this? Ignore this email. Your password stays the same.</td></tr></table>
      <p style="margin:20px 0 0;font-size:12px;line-height:18px;color:{MUTED};word-break:break-all">Button not working? Copy this link into your browser:<br><a href="{escape(link)}" style="color:{CYAN}">{escape(link)}</a></p>'''
    html = _layout("Choose a new password for TRADE-AI. The link expires in 30 minutes.", inner,
                   "You received this because a password reset was requested for your account.")
    text = (f"Reset your TRADE-AI password\n\nSomeone asked to reset the password for your TRADE-AI account.\n"
            f"Open this link to choose a new one (works once, expires in {ttl_minutes} minutes):\n{link}\n\n"
            f"Didn't ask for this? Ignore this email. Your password stays the same.\n")
    return subject, html, text


def signal_alert(side: str, pair: str, market: str, timeframe: str, score, link: str, settings_link: str) -> tuple[str, str, str]:
    long = side == "LONG"
    col, arrow, word = (GREEN, "&#9650;", "LONG") if long else (RED, "&#9660;", "SHORT")
    tint = "rgba(53,201,138,.12)" if long else "rgba(241,107,117,.12)"
    sc = "n/a" if score is None else f"{int(score)}"
    pct = 0 if score is None else max(0, min(100, int(score)))
    subject = f"TRADE-AI: new {word} setup · {pair} ({timeframe})"
    inner = f'''
      <div style="display:inline-block;padding:6px 12px;border-radius:999px;background:rgba(54,214,231,.12);border:1px solid rgba(54,214,231,.4);color:{CYAN};font-size:12px;font-weight:700;letter-spacing:.6px;text-transform:uppercase">New setup</div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:18px 0 6px"><tr>
        <td style="font-size:30px;line-height:36px;font-weight:800;color:{TEXT}">{escape(pair)}</td>
        <td align="right"><span style="display:inline-block;padding:8px 14px;border-radius:10px;background:{tint};border:1px solid {col};color:{col};font-size:16px;font-weight:800;letter-spacing:.8px">{arrow} {word}</span></td></tr></table>
      <p style="margin:0 0 18px;font-size:14px;color:{MUTED}">{escape(market.capitalize())} &middot; {escape(timeframe)} candles</p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-radius:12px;background:{BG};border:1px solid {LINE}"><tr><td style="padding:16px">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
          <td style="font-size:13px;color:{MUTED};text-transform:uppercase;letter-spacing:.6px">Setup score</td>
          <td align="right" style="font-size:20px;font-weight:800;color:{CYAN}">{sc}<span style="font-size:13px;color:{MUTED};font-weight:600">/100</span></td></tr></table>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:10px"><tr>
          <td width="{pct}%" style="height:8px;line-height:8px;font-size:0;border-radius:8px;background:{CYAN};background-image:linear-gradient(90deg,{TEAL},{CYAN})">&nbsp;</td>
          <td style="height:8px;line-height:8px;font-size:0;background:{LINE};border-radius:8px">&nbsp;</td></tr></table>
        <p style="margin:10px 0 0;font-size:12px;line-height:18px;color:{MUTED}">A checklist rating of how many conditions lined up. It is <b style="color:{TEXT}">not</b> a win probability.</p>
      </td></tr></table>
      <p style="margin:20px 0 16px;font-size:15px;line-height:23px;color:#C9D6DF">Entry zone, stop and targets, with the reasoning behind each, are in the app.</p>
      {_button(link, "View the setup")}
      <p style="margin:18px 0 0;font-size:12px;line-height:18px;color:{MUTED}">The strategy is experimental and lost money in our published backtests. Treat this as research, not a recommendation.</p>'''
    html = _layout(f"{word} {pair} on {timeframe}, setup score {sc}/100. Levels are in the app.", inner,
                   f'You get these because you turned on email alerts. <a href="{escape(settings_link)}" style="color:{CYAN}">Turn them off</a>.')
    text = (f"New {word} setup: {pair} ({market}, {timeframe})\nSetup score: {sc}/100 (not a win probability)\n\n"
            f"Entry, stop and targets are in the app:\n{link}\n\n"
            f"Experimental strategy; research, not a recommendation. TRADE-AI never places trades.\n"
            f"Turn these emails off: {settings_link}\n")
    return subject, html, text
