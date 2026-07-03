"""Send the picks report via Gmail SMTP using smtplib (stdlib only)."""

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from config import GMAIL_APP_PASSWORD, GMAIL_SENDER, REPORT_RECIPIENT

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def send_email(subject: str, text_body: str, html_body: Optional[str] = None) -> None:
    if html_body:
        # multipart/alternative: clients render the HTML part and fall back to
        # the plain-text part; order matters (last part = preferred).
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
    else:
        msg = MIMEText(text_body, "plain", "utf-8")

    msg["Subject"] = subject
    msg["From"] = GMAIL_SENDER
    msg["To"] = REPORT_RECIPIENT

    # Strip all whitespace — app passwords copied from Google often contain
    # non-breaking spaces (\xa0) that break ASCII encoding in smtplib
    clean_password = "".join(GMAIL_APP_PASSWORD.split())

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(GMAIL_SENDER, clean_password)
            server.sendmail(GMAIL_SENDER, REPORT_RECIPIENT, msg.as_string())
        logger.info("Report emailed to %s", REPORT_RECIPIENT)
    except smtplib.SMTPException as exc:
        logger.error("Failed to send email: %s", exc)
        raise
