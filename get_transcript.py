"""Fetch YouTube transcripts via Supadata API."""

import logging
import re
import time
from typing import Optional

from supadata import Supadata

from config import SUPADATA_API_KEY

logger = logging.getLogger(__name__)

# Captions for a freshly uploaded video may not be ready yet, and Supadata can
# return transient errors — retry a few times before giving up.
_RETRY_DELAYS = [5, 15, 30]


def _fetch_transcript(client: Supadata, video_id: str):
    last_exc: Optional[Exception] = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            logger.info("Retrying transcript for %s (attempt %d) after %ds", video_id, attempt + 1, delay)
            time.sleep(delay)
        try:
            result = client.youtube.transcript(video_id=video_id, lang="en")
        except Exception as exc:  # noqa: BLE001 — SDK raises several error types
            last_exc = exc
            logger.warning("Transcript attempt %d failed for %s: %s", attempt + 1, video_id, exc)
            continue
        if result and result.content:
            return result
        logger.warning("Empty transcript for %s (attempt %d)", video_id, attempt + 1)
    if last_exc:
        logger.warning("Transcript unavailable for %s after retries: %s", video_id, last_exc)
    return None


def get_transcript(video_id: str) -> Optional[str]:
    """Return clean plaintext transcript using Supadata (bypasses YouTube IP blocks)."""
    if not SUPADATA_API_KEY:
        logger.warning("SUPADATA_API_KEY not set — skipping transcript")
        return None

    client = Supadata(api_key=SUPADATA_API_KEY)
    result = _fetch_transcript(client, video_id)
    if not result or not result.content:
        return None

    if isinstance(result.content, str):
        cleaned = result.content.strip()
    else:
        lines: list[str] = []
        prev = ""
        for chunk in result.content:
            text = re.sub(r"\s+", " ", chunk.text).strip()
            if text and text != prev:
                lines.append(text)
                prev = text
        cleaned = " ".join(lines)

    logger.info("Transcript fetched for %s (%d chars)", video_id, len(cleaned))
    return cleaned if cleaned else None
