"""Fetch the latest qualifying YouTube video for a channel."""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import requests

from config import YOUTUBE_API_KEY, MAX_VIDEO_AGE_HOURS

logger = logging.getLogger(__name__)

PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"

# How many recent uploads to pull from a channel's uploads playlist. We read the
# uploads playlist instead of search.list because search.list's index lags
# uploads by minutes-to-hours, which was silently dropping videos posted shortly
# before the run (e.g. a World Cup picks video uploaded ~1h before the 16:00 UTC
# run never appeared). The uploads playlist reflects new videos in real time and
# is returned newest-first; 50 comfortably spans the freshness window even for
# high-volume channels.
_MAX_UPLOADS = 50


def _uploads_playlist_id(channel_id: str) -> str:
    """A channel's uploads playlist ID is its channel ID with the 'UC' prefix
    swapped for 'UU' — a stable YouTube convention that avoids an extra
    channels.list call."""
    if channel_id.startswith("UC"):
        return "UU" + channel_id[2:]
    return channel_id


def _list_recent_uploads(channel_id: str) -> list[dict]:
    """Return the channel's most-recent uploads (newest first), normalized to the
    same shape fetch_latest_video expects (id.videoId, snippet.title,
    snippet.publishedAt)."""
    params = {
        "key": YOUTUBE_API_KEY,
        "playlistId": _uploads_playlist_id(channel_id),
        "part": "snippet,contentDetails",
        "maxResults": _MAX_UPLOADS,
    }
    resp = requests.get(PLAYLIST_ITEMS_URL, params=params, timeout=30)
    resp.raise_for_status()

    normalized: list[dict] = []
    for item in resp.json().get("items", []):
        snippet = item.get("snippet", {})
        details = item.get("contentDetails", {})
        video_id = details.get("videoId") or snippet.get("resourceId", {}).get("videoId")
        if not video_id:
            continue
        # videoPublishedAt is the true upload time; snippet.publishedAt is when
        # the item was added to the uploads playlist (effectively identical, but
        # prefer the former when present).
        published_at = details.get("videoPublishedAt") or snippet.get("publishedAt")
        normalized.append(
            {
                "id": {"videoId": video_id},
                "snippet": {"title": snippet.get("title", ""), "publishedAt": published_at},
            }
        )
    return normalized


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

    try:
        items = _list_recent_uploads(channel_id)
    except requests.RequestException as exc:
        logger.error("YouTube uploads fetch failed for %s: %s", channel_label, exc)
        return None

    # Keep only videos that pass the filter AND are within the freshness window.
    # The uploads playlist isn't filtered server-side, so this cutoff check is the
    # sole freshness gate (and lets us log the real age).
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


def world_cup_filter(title: str) -> bool:
    """Return True if the video title is about (FIFA) World Cup picks."""
    t = title.upper()
    return "WORLD CUP" in t or "FIFA" in t


def picks_score(title: str) -> int:
    """
    Rank a channel's videos so the main picks post wins over props-only videos.

    Sport-agnostic. Higher is better.
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
