"""Scrape picks content from an external article URL via Jina Reader."""

import logging
import re
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_JINA_PREFIX = "https://r.jina.ai/"
_TIMEOUT = 30
_RETRY_DELAYS = [5, 15, 30]
_PICKS_KEYWORDS = {"pick", "bet", "prediction", "best bet", "best bets", "plays", "play"}

# Headings that mark the end of the article body — everything from here down is
# comment forms, related posts, navigation, etc. and must never be returned.
_NOISE_HEADINGS = (
    "related",
    "post navigation",
    "leave a reply",
    "leave a comment",
    "cancel reply",
    "comments",
    "you may also like",
    "more from",
    "recent posts",
    "subscribe",
    "newsletter",
)

# A real picks sheet carries at least one of these: odds (+150/-110), units,
# over/under totals, spreads, prop/ML language, or pick/bet wording.
_BET_SIGNAL = re.compile(
    r"([+-]\d{2,4}\b|\b\d+(?:\.\d+)?\s*units?\b|\bo/?\s*\d|\bu/?\s*\d|\bover\b|\bunder\b"
    r"|\bspread\b|\btotal\b|\bml\b|\bmoneyline\b|\bparlay\b|\bprop\b|\bpick\b|\bbet\b)",
    re.IGNORECASE,
)


def _has_bet_signal(text: str) -> bool:
    return _BET_SIGNAL.search(text) is not None


def scrape_picks_page(url: str) -> Optional[str]:
    """Return plaintext picks content fetched via Jina Reader (no proxy needed)."""
    jina_url = f"{_JINA_PREFIX}{url}"
    headers = {"Accept": "text/plain", "X-Return-Format": "markdown"}

    resp = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            logger.info("Scrape attempt %d for %s, waiting %ds", attempt + 1, url, delay)
            time.sleep(delay)
        try:
            resp = requests.get(jina_url, headers=headers, timeout=_TIMEOUT)
            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning("Got %d from Jina for %s, will retry", resp.status_code, url)
                continue
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            logger.error("Failed to fetch %s via Jina: %s", url, exc)
            return None
    else:
        logger.error("All retries exhausted for %s", url)
        return None

    text = resp.text.strip()
    if not text:
        logger.warning("Empty content from Jina for %s", url)
        return None

    blocks = _extract_picks_blocks(text)
    if not blocks:
        logger.warning("No picks content found at %s", url)
        return None

    result = "\n\n".join(blocks)

    # Backstop: only return content that actually carries a betting signal, so
    # stray boilerplate (comment forms, nav) never surfaces as a "picks sheet".
    if not _has_bet_signal(result):
        logger.warning("Scraped content for %s lacks any betting signal, discarding", url)
        return None

    logger.info("Scraped %d chars from %s via Jina", len(result), url)
    return result


def _clean_section(text: str) -> str:
    """Strip images, bare URLs, link-only lines, and nav/footer noise."""
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Skip standalone image or linked-image lines
        if re.match(r"^!?\[.*?\]\(.*?\)$", stripped):
            continue
        # Skip bare URLs
        if re.match(r"^https?://\S+$", stripped):
            continue
        # Skip nav/footer lines
        if re.match(r"^(Post navigation|Copyright ©|← |→ )", stripped):
            continue
        # Replace inline images: ![Image N: alt](url) → alt, ![alt](url) → alt
        line = re.sub(r"!\[(?:Image \d+: )?([^\]]*)\]\([^)]+\)", r"\1", line)
        # Replace linked images: [![alt](src)](href) → alt
        line = re.sub(r"\[!\[(?:Image \d+: )?([^\]]*)\]\([^)]+\)\]\([^)]+\)", r"\1", line)
        # Drop lines that are empty after cleanup
        if not line.strip():
            continue
        lines.append(line)
    return "\n".join(lines)


def _heading_text(line: str) -> Optional[str]:
    """Return the text of a markdown heading line, or None if not a heading."""
    m = re.match(r"^#{1,6}\s+(.+)$", line)
    return m.group(1).strip() if m else None


def _label_text(line: str) -> Optional[str]:
    """
    Return the text of a 'label' line that introduces picks.

    Matches markdown headings (## Picks) and standalone bold labels rendered by
    the article (e.g. **Trey's Plays:**), which is how this site marks its plays.
    """
    heading = _heading_text(line)
    if heading is not None:
        return heading
    bold = re.match(r"^\*{1,3}(.+?)\*{1,3}:?\s*$", line.strip())
    if bold:
        return bold.group(1).strip()
    return None


def _is_noise(text: str) -> bool:
    t = text.lower()
    return any(noise in t for noise in _NOISE_HEADINGS)


def _extract_picks_blocks(text: str) -> list[str]:
    lines = text.split("\n")

    # 1. Truncate the document at the first noise section (comments / related /
    #    navigation) so that junk like "Leave a Reply" can never be captured.
    end = len(lines)
    for idx, line in enumerate(lines):
        heading = _heading_text(line)
        if heading and _is_noise(heading):
            end = idx
            break
    body = lines[:end]

    blocks: list[str] = []

    # 2. Capture each picks section, anchored on a heading OR a bold label that
    #    contains a picks keyword, up to the next heading.
    i = 0
    while i < len(body):
        label = _label_text(body[i])
        if label and not _is_noise(label) and any(kw in label.lower() for kw in _PICKS_KEYWORDS):
            section_lines = [body[i]]
            j = i + 1
            while j < len(body) and _heading_text(body[j]) is None:
                section_lines.append(body[j])
                j += 1
            section = _clean_section("\n".join(section_lines)).strip()
            if section:
                blocks.append(section)
            i = j
            continue
        i += 1

    # 3. Fallback: markdown table rows (some articles post picks as a table).
    if not blocks:
        table_lines = [l for l in body if l.strip().startswith("|") and "|" in l.strip()[1:]]
        if table_lines:
            blocks.append("\n".join(table_lines))

    # 4. Last resort: any body line that mentions a pick keyword.
    if not blocks:
        cleaned = _clean_section("\n".join(body))
        keep = [l for l in cleaned.split("\n") if any(kw in l.lower() for kw in _PICKS_KEYWORDS)]
        if keep:
            blocks.append("\n".join(keep))

    return blocks
