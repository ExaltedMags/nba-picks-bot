"""Extract and clean YouTube captions via youtube-transcript-api."""

import logging
import re
from typing import Optional

from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

from config import WEBSHARE_PROXY_PASSWORD, WEBSHARE_PROXY_USERNAME

logger = logging.getLogger(__name__)


def _make_api() -> YouTubeTranscriptApi:
    if WEBSHARE_PROXY_USERNAME and WEBSHARE_PROXY_PASSWORD:
        return YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                proxy_username=WEBSHARE_PROXY_USERNAME,
                proxy_password=WEBSHARE_PROXY_PASSWORD,
            )
        )
    return YouTubeTranscriptApi()


def get_transcript(video_id: str) -> Optional[str]:
    """Fetch manual or auto-generated captions and return clean plaintext."""
    try:
        api = _make_api()
        transcript_list = api.list(video_id)
        try:
            transcript = transcript_list.find_manually_created_transcript(["en"])
        except NoTranscriptFound:
            transcript = transcript_list.find_generated_transcript(["en"])
        entries = transcript.fetch()
    except TranscriptsDisabled:
        logger.warning("Captions disabled for %s", video_id)
        return None
    except NoTranscriptFound:
        logger.warning("No English transcript found for %s", video_id)
        return None
    except Exception as exc:
        logger.error("Transcript fetch failed for %s: %s", video_id, exc)
        return None

    lines: list[str] = []
    prev = ""
    for entry in entries:
        text = re.sub(r"\s+", " ", entry.text).strip()
        if text and text != prev:
            lines.append(text)
            prev = text

    cleaned = " ".join(lines)
    logger.info("Transcript extracted for %s (%d chars)", video_id, len(cleaned))
    return cleaned if cleaned else None
