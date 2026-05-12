"""Fetch YouTube transcripts via Supadata API."""

import logging
import re
from typing import Optional

from supadata import Supadata

from config import SUPADATA_API_KEY

logger = logging.getLogger(__name__)


def get_transcript(video_id: str) -> Optional[str]:
    """Return clean plaintext transcript using Supadata (bypasses YouTube IP blocks)."""
    if not SUPADATA_API_KEY:
        logger.warning("SUPADATA_API_KEY not set — skipping transcript")
        return None

    try:
        client = Supadata(api_key=SUPADATA_API_KEY)
        result = client.youtube.transcript(video_id=video_id, lang="en")
    except Exception as exc:
        logger.warning("Transcript unavailable for %s: %s", video_id, exc)
        return None

    if not result or not result.content:
        logger.warning("Empty transcript for %s", video_id)
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
