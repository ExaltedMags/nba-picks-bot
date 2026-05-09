"""Send the picks report via Gmail SMTP using smtplib (stdlib only)."""

import logging
import smtplib
import ssl
from email.mime.text import MIMEText

from config import GMAIL_APP_PASSWORD, GMAIL_SENDER, REPORT_RECIPIENT

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def send_email(subject: str, body: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = GMAIL_SENDER
    msg["To"] = REPORT_RECIPIENT

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, REPORT_RECIPIENT, msg.as_string())
        logger.info("Report emailed to %s", REPORT_RECIPIENT)
    except smtplib.SMTPException as exc:
        logger.error("Failed to send email: %s", exc)
        raise
