"""Fetch the latest qualifying YouTube video for a channel."""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import requests

from config import YOUTUBE_API_KEY, MAX_VIDEO_AGE_HOURS

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


def _parse_published(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def fetch_latest_video(
    channel_id: str,
    filter_fn: Callable[[str], bool],
    channel_label: str = "",
    score_fn: Optional[Callable[[str], int]] = None,
    max_age_hours: Optional[int] = None,
) -> Optional[dict]:
    """
    Return the freshest qualifying video published within the freshness window.

    A strict age window (config.MAX_VIDEO_AGE_HOURS) is enforced so we never grab
    a previous day's video and present it as today's: if today's video isn't up
    yet, this returns None (treated as an EMPTY channel) rather than a stale one.

    If score_fn is provided, qualifying videos are scored and the highest scorer
    wins; ties break toward the most recent upload.
    """
    if max_age_hours is None:
        max_age_hours = MAX_VIDEO_AGE_HOURS

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)
    published_after = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        items = _search(channel_id, published_after)
    except requests.RequestException as exc:
        logger.error("YouTube search failed for %s: %s", channel_label, exc)
        return None

    # Keep only videos that pass the filter AND are genuinely within the window.
    # (publishedAfter already filters server-side; the explicit check guards
    # against any edge cases and lets us log the real age.)
    matches: list[tuple[dict, datetime]] = []
    for item in items:
        title = item["snippet"]["title"]
        if not filter_fn(title):
            continue
        pub_dt = _parse_published(item["snippet"].get("publishedAt", ""))
        if pub_dt is None or pub_dt < cutoff:
            continue
        matches.append((item, pub_dt))

    if not matches:
        logger.warning(
            "No qualifying video within %dh for %s", max_age_hours, channel_label
        )
        return None

    if score_fn:
        matches.sort(key=lambda m: (score_fn(m[0]["snippet"]["title"]), m[1]), reverse=True)
    else:
        matches.sort(key=lambda m: m[1], reverse=True)

    best, best_pub = matches[0]
    video_id = best["id"]["videoId"]
    title = best["snippet"]["title"]
    age_hours = (now - best_pub).total_seconds() / 3600

    if score_fn and len(matches) > 1:
        scores = [(m[0]["snippet"]["title"], score_fn(m[0]["snippet"]["title"])) for m in matches]
        logger.info("Video scores for %s: %s", channel_label, scores)

    logger.info(
        "Selected video for %s: %s (%s, %.1fh old)", channel_label, title, video_id, age_hours
    )
    return {
        "video_id": video_id,
        "title": title,
        "published_at": best["snippet"]["publishedAt"],
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }


# ---------------------------------------------------------------------------
# Filter and score functions
# ---------------------------------------------------------------------------

def _has_word(word: str, text: str) -> bool:
    """Whole-word match (so 'NBA' does not match inside 'WNBA')."""
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def wnba_filter(title: str) -> bool:
    """Return True if the video title is about WNBA picks."""
    from config import WNBA_TEAM_NAMES, EXCLUDE_SPORTS

    t = title.upper()

    # Drop videos for other sports (e.g. men's NBA, MLB) so we only keep WNBA.
    for sport in EXCLUDE_SPORTS:
        if _has_word(sport.upper(), t):
            return False

    if "WNBA" in t:
        return True
    for team in WNBA_TEAM_NAMES:
        if _has_word(team.upper(), t):
            return True
    return False


def wnba_score(title: str) -> int:
    """
    Rank a channel's videos so the main picks post wins over props-only videos.

    Higher is better.
    """
    t = title.upper()
    score = 0

    # Strong positive: explicit picks / best-bets content.
    if "PICKS" in t:
        score += 10
    if "BEST BETS" in t:
        score += 5

    # Negative: a dedicated player-props video (no broader picks coverage).
    if "PROPS" in t and "PICKS" not in t and "BEST BETS" not in t:
        score -= 8

    return score
