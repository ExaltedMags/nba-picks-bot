"""Fetch the latest qualifying YouTube video for a channel."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import requests

from config import YOUTUBE_API_KEY

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def _search(channel_id: str, published_after: str) -> list[dict]:
    params = {
        "key": YOUTUBE_API_KEY,
        "channelId": channel_id,
        "part": "snippet",
        "order": "date",
        "type": "video",
        "publishedAfter": published_after,
        "maxResults": 10,
    }
    resp = requests.get(SEARCH_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("items", [])


def fetch_latest_video(
    channel_id: str,
    filter_fn: Callable[[str], bool],
    channel_label: str = "",
) -> Optional[dict]:
    """Return the first video matching filter_fn from today, falling back to yesterday."""
    for days_back in (0, 1):
        date = datetime.now(timezone.utc) - timedelta(days=days_back)
        published_after = date.replace(hour=0, minute=0, second=0, microsecond=0).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        try:
            items = _search(channel_id, published_after)
        except requests.RequestException as exc:
            logger.error("YouTube search failed for %s: %s", channel_label, exc)
            return None

        for item in items:
            title = item["snippet"]["title"]
            if filter_fn(title):
                video_id = item["id"]["videoId"]
                logger.info("Found video for %s: %s (%s)", channel_label, title, video_id)
                return {
                    "video_id": video_id,
                    "title": title,
                    "published_at": item["snippet"]["publishedAt"],
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }

    logger.warning("No qualifying video found for %s", channel_label)
    return None


# ---------------------------------------------------------------------------
# Filter functions
# ---------------------------------------------------------------------------

def ev_filter(title: str) -> bool:
    """Return True if the video title matches Ev's NBA picks heuristic."""
    from config import NBA_TEAM_NAMES, EXCLUDE_SPORTS

    t = title.upper()

    # Exclude non-NBA sports
    for sport in EXCLUDE_SPORTS:
        if sport.upper() in t:
            return False

    if "NBA" in t:
        return True
    for team in NBA_TEAM_NAMES:
        if team.upper() in t:
            return True
    if ("PICKS" in t or "BEST BETS" in t):
        return True
    return False


def daft_filter(_title: str) -> bool:
    """All videos from Daft's channel are relevant."""
    return True
