"""Sending sign-in emails.

Providers (``EMAIL_PROVIDER``):

* ``console``: only logs the link. For local development.
* ``resend``: Resend's HTTPS API. Needs ``RESEND_API_KEY`` and an ``EMAIL_FROM``
  on a domain verified with Resend.
* ``smtp``: any SMTP server (``SMTP_HOST``, ``SMTP_PORT``, ``SMTP_USER``,
  ``SMTP_PASSWORD``).

``send_magic_link`` returns True once the provider accepted the message and
False if it could not be sent. Callers decide what to tell the person.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_local() -> bool:
    return settings.API_BASE_URL.startswith("http://localhost")


def magic_link_message(link: str) -> tuple[str, str, str]:
    """(subject, plain text, html) for the sign-in email."""
    minutes = max(1, settings.MAGIC_LINK_MAX_AGE // 60)
    subject = "Your tbqh sign-in link"
    text = (
        "Tap the link below to sign in to tbqh.\n\n"
        f"{link}\n\n"
        f"The link works for {minutes} minutes. If you did not ask for it, you can "
        "ignore this email.\n"
    )
    html = f"""\
<div style="background:#ECEBE6;padding:32px 16px;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1A1916">
  <div style="max-width:420px;margin:0 auto">
    <div style="font-family:Georgia,'Times New Roman',serif;font-size:28px;margin-bottom:20px">tbqh</div>
    <p style="font-size:17px;line-height:1.5;margin:0 0 24px">Tap the button to sign in.</p>
    <a href="{link}" style="display:block;text-align:center;background:#1A1916;color:#FEFAF7;text-decoration:none;padding:16px 24px;border-radius:6px;font-size:17px">Sign in to tbqh</a>
    <p style="font-size:14px;line-height:1.5;color:#5E5A52;margin:24px 0 0">The link works for {minutes} minutes. If you did not ask for it, you can ignore this email.</p>
  </div>
</div>
"""
    return subject, text, html


def send_magic_link(to: str, link: str) -> bool:
    provider = (settings.EMAIL_PROVIDER or "console").lower()
    try:
        if provider == "console":
            if not _is_local():
                logger.warning(
                    "EMAIL_PROVIDER is 'console' on a deployed server: the sign-in "
                    "email for %s was NOT sent. Set EMAIL_PROVIDER to 'resend' or 'smtp'.",
                    to,
                )
            logger.info("Magic link for %s: %s", to, link)
            return True
        subject, text, html = magic_link_message(link)
        if provider == "resend":
            return _send_resend(to, subject, text, html)
        if provider == "smtp":
            return _send_smtp(to, subject, text, html)
        logger.error("Unknown EMAIL_PROVIDER %r", provider)
        return False
    except Exception:
        # Never log the link: it signs the person in.
        logger.exception("Could not send the sign-in email to %s", to)
        return False


def _send_resend(to: str, subject: str, text: str, html: str) -> bool:
    if not settings.RESEND_API_KEY:
        logger.error("EMAIL_PROVIDER is 'resend' but RESEND_API_KEY is not set")
        return False
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json={
            "from": settings.EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "text": text,
            "html": html,
        },
        timeout=10.0,
    )
    if resp.status_code >= 300:
        logger.error("Resend rejected the email (%s): %s", resp.status_code, resp.text[:300])
        return False
    return True


def _send_smtp(to: str, subject: str, text: str, html: str) -> bool:
    if not settings.SMTP_HOST:
        logger.error("EMAIL_PROVIDER is 'smtp' but SMTP_HOST is not set")
        return False
    name, addr = parseaddr(settings.EMAIL_FROM)
    msg = EmailMessage()
    msg["From"] = formataddr((name, addr)) if addr else settings.EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        if settings.SMTP_STARTTLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
    return True
