"""Fetch YouTube transcripts via Apify YouTube Transcript Scraper actor."""

import logging
import re
from typing import Optional

import requests

from config import APIFY_API_KEY

logger = logging.getLogger(__name__)

_ACTOR = "apify~youtube-transcript-scraper"
_RUN_URL = f"https://api.apify.com/v2/acts/{_ACTOR}/run-sync-get-dataset-items"
_TIMEOUT = 120  # seconds; actor cold-start can take ~30s


def get_transcript(video_id: str) -> Optional[str]:
    """Return clean plaintext transcript using Apify (bypasses YouTube IP blocks)."""
    if not APIFY_API_KEY:
        logger.warning("APIFY_API_KEY not set — skipping transcript")
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        resp = requests.post(
            _RUN_URL,
            params={"token": APIFY_API_KEY},
            json={"videoUrls": [url]},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as exc:
        logger.warning("Transcript unavailable for %s: %s", video_id, exc)
        return None

    if not items:
        logger.warning("Empty transcript response for %s", video_id)
        return None

    item = items[0]
    chunks = item.get("transcript") or item.get("captions") or []
    if not chunks:
        logger.warning("No transcript chunks for %s (keys: %s)", video_id, list(item.keys()))
        return None

    lines: list[str] = []
    prev = ""
    for chunk in chunks:
        text = re.sub(r"\s+", " ", chunk.get("text", "")).strip()
        if text and text != prev:
            lines.append(text)
            prev = text

    cleaned = " ".join(lines).strip()
    logger.info("Transcript fetched for %s (%d chars)", video_id, len(cleaned))
    return cleaned if cleaned else None
