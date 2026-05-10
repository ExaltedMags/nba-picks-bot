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
    score_fn: Optional[Callable[[str], int]] = None,
    max_days_back: int = 1,
) -> Optional[dict]:
    """
    Return the best matching video from today (falling back up to max_days_back).

    If score_fn is provided, all videos passing filter_fn are scored and the
    highest scorer is returned — not just the first match.
    """
    for days_back in range(0, max_days_back + 1):
        date = datetime.now(timezone.utc) - timedelta(days=days_back)
        published_after = date.replace(hour=0, minute=0, second=0, microsecond=0).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        try:
            items = _search(channel_id, published_after)
        except requests.RequestException as exc:
            logger.error("YouTube search failed for %s: %s", channel_label, exc)
            return None

        matches = [item for item in items if filter_fn(item["snippet"]["title"])]
        if not matches:
            continue

        if score_fn:
            matches.sort(key=lambda x: score_fn(x["snippet"]["title"]), reverse=True)

        best = matches[0]
        video_id = best["id"]["videoId"]
        title = best["snippet"]["title"]

        if score_fn and len(matches) > 1:
            scores = [(m["snippet"]["title"], score_fn(m["snippet"]["title"])) for m in matches]
            logger.info("Video scores for %s: %s", channel_label, scores)

        logger.info("Selected video for %s: %s (%s)", channel_label, title, video_id)
        return {
            "video_id": video_id,
            "title": title,
            "published_at": best["snippet"]["publishedAt"],
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }

    logger.warning("No qualifying video found for %s", channel_label)
    return None


# ---------------------------------------------------------------------------
# Filter and score functions
# ---------------------------------------------------------------------------

def ev_filter(title: str) -> bool:
    """Return True if the video title matches Ev's NBA picks heuristic."""
    from config import NBA_TEAM_NAMES, EXCLUDE_SPORTS

    t = title.upper()

    for sport in EXCLUDE_SPORTS:
        if sport.upper() in t:
            return False

    if "NBA" in t:
        return True
    for team in NBA_TEAM_NAMES:
        if team.upper() in t:
            return True
    if "PICKS" in t or "BEST BETS" in t:
        return True
    return False


def ev_score(title: str) -> int:
    """
    Rank Ev's videos so his regular picks post wins over props/other-host videos.

    Higher is better.
    """
    t = title.upper()
    score = 0

    # Strong positive: explicit picks content (not a props-only video)
    if "PICKS" in t and "PLAYER PROPS" not in t:
        score += 10
    if "BEST BETS" in t and "PLAYER PROPS" not in t:
        score += 5

    # Mild positive: NBA label
    if "NBA" in t:
        score += 3

    # Negative: props-only videos are from a different segment/host
    if "PLAYER PROPS" in t:
        score -= 8
    elif "PROPS" in t:
        score -= 4

    return score


def daft_filter(_title: str) -> bool:
    """All videos from Daft's channel are relevant."""
    return True
