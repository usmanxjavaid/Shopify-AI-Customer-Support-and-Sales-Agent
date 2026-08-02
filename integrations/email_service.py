"""
integrations/email_service.py
--------------------------------
Outbound email via Gmail SMTP. Used for ALL outbound sending (owner
ticket notifications, customer replies) since Resend's free testing
domain (onboarding@resend.dev) only delivers to the account owner's
own signup email — a hard restriction until a custom domain is
verified. Gmail SMTP has no such restriction and is genuinely free.

Resend is still used separately for INBOUND email (receiving the
owner's replies) — that direction has no such restriction.
"""

import smtplib
from email.mime.text import MIMEText

from config import settings
from logger import get_logger

logger = get_logger(__name__)


def send_email(to: str, subject: str, body: str) -> bool:
    """
    Sends a plain text email via Gmail SMTP.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain text email body.

    Returns:
        True if sent successfully, False otherwise.
    """
    if not settings.GMAIL_ADDRESS or not settings.GMAIL_APP_PASSWORD:
        logger.warning("Gmail SMTP not configured, skipping email send")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = f"Velvora Support <{settings.GMAIL_ADDRESS}>"
    msg["To"] = to

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD)
            server.sendmail(settings.GMAIL_ADDRESS, [to], msg.as_string())
        logger.info(f"Email sent to {to}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return False


logger.debug("integrations.email_service loaded successfully")