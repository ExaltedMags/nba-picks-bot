"""Extract the pinned comment URL from a YouTube video."""

import logging
import re
from typing import Optional

import requests

from config import YOUTUBE_API_KEY

logger = logging.getLogger(__name__)

COMMENTS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
URL_RE = re.compile(r"https?://[^\s)>\]\"']+")


def _extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text)


def get_pinned_comment_url(
    video_id: str,
    channel_id: str,
    allowed_domains: Optional[list[str]] = None,
) -> Optional[str]:
    """
    Return the first external URL from the pinned (or channel-owner) comment.

    YouTube's API doesn't expose a 'pinned' flag. We approximate it by:
    1. Preferring a comment authored by the channel owner.
    2. Falling back to the comment with the highest likeCount.
    """
    params = {
        "key": YOUTUBE_API_KEY,
        "videoId": video_id,
        "part": "snippet",
        "order": "relevance",
        "maxResults": 20,
    }
    try:
        resp = requests.get(COMMENTS_URL, params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch comments for %s: %s", video_id, exc)
        return None

    items = resp.json().get("items", [])
    if not items:
        logger.info("No comments found for %s", video_id)
        return None

    # Rank: owner comments first, then by likeCount
    def rank(item: dict) -> tuple:
        top = item["snippet"]["topLevelComment"]["snippet"]
        is_owner = top.get("authorChannelId", {}).get("value", "") == channel_id
        likes = top.get("likeCount", 0)
        return (not is_owner, -likes)

    candidates = sorted(items, key=rank)

    for item in candidates:
        text = item["snippet"]["topLevelComment"]["snippet"].get("textOriginal", "")
        urls = _extract_urls(text)
        for url in urls:
            # Skip YouTube-internal links
            if "youtube.com" in url or "youtu.be" in url:
                continue
            if allowed_domains:
                if any(domain in url for domain in allowed_domains):
                    logger.info("Pinned comment URL found for %s: %s", video_id, url)
                    return url
            else:
                logger.info("Pinned comment URL found for %s: %s", video_id, url)
                return url

    logger.info("No qualifying external URL in comments for %s", video_id)
    return None
