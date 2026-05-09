"""Send messages to a Telegram chat via Bot API."""

import logging
import time
from typing import Optional

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_CHARS = 4096


def _send_single(text: str, parse_mode: Optional[str] = None) -> bool:
    url = SEND_URL.format(token=TELEGRAM_BOT_TOKEN)
    payload: dict = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Telegram send failed: %s", exc)
        return False


def send_telegram(message: str, parse_mode: Optional[str] = None) -> None:
    """Send message, splitting into chunks if it exceeds 4096 chars."""
    if len(message) <= MAX_CHARS:
        _send_single(message, parse_mode)
        return

    # Split on newlines to avoid cutting mid-word
    chunks: list[str] = []
    current = ""
    for line in message.splitlines(keepends=True):
        if len(current) + len(line) > MAX_CHARS:
            if current:
                chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)

    for i, chunk in enumerate(chunks):
        _send_single(chunk, parse_mode)
        if i < len(chunks) - 1:
            time.sleep(1)
