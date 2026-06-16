"""Minimal email sending for the reminder cron — Resend API or SMTP, whichever is configured."""
import os
import logging
import smtplib
from email.mime.text import MIMEText
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


async def send_email(to_email: str, subject: str, body: str) -> Tuple[bool, Optional[str]]:
    """Send a plain-text email. Returns (ok, error). If no provider is configured,
    logs a warning and returns (False, "no_email_provider_configured") without raising."""
    from_addr = os.environ.get("EMAIL_FROM") or os.environ.get("RESEND_FROM") or "noreply@delaybridge.app"

    resend_key = os.environ.get("RESEND_API_KEY")
    if resend_key:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                    json={"from": from_addr, "to": [to_email], "subject": subject, "text": body},
                )
                r.raise_for_status()
            return True, None
        except Exception as e:
            return False, str(e)

    smtp_host = os.environ.get("SMTP_HOST")
    if smtp_host:
        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = to_email
            smtp_port = int(os.environ.get("SMTP_PORT", "587"))
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if os.environ.get("SMTP_TLS", "true").lower() != "false":
                    server.starttls()
                user, pwd = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
                if user and pwd:
                    server.login(user, pwd)
                server.sendmail(from_addr, [to_email], msg.as_string())
            return True, None
        except Exception as e:
            return False, str(e)

    logger.warning("No email provider configured (RESEND_API_KEY / SMTP_HOST); skipping send to %s", to_email)
    return False, "no_email_provider_configured"
