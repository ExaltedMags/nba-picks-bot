"""Extract and clean YouTube captions via youtube-transcript-api."""

import logging
import re
from typing import Optional

from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

logger = logging.getLogger(__name__)


def get_transcript(video_id: str) -> Optional[str]:
    """Fetch manual or auto-generated captions and return clean plaintext.

    Note: YouTube blocks transcript requests from cloud runner IPs (GitHub Actions,
    AWS, Azure, etc.). This will return None on those environments unless a
    residential proxy is configured at the YouTubeTranscriptApi level.
    The pipeline falls back to the scraped picks sheet when this happens.
    """
    try:
        api = YouTubeTranscriptApi()
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
        logger.warning("Transcript unavailable for %s (likely IP block): %s", video_id, exc)
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
