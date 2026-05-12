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
_PICKS_KEYWORDS = {"pick", "bet", "prediction", "best bet", "best bets", "plays"}


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
    logger.info("Scraped %d chars from %s via Jina", len(result), url)
    return result


def _clean_section(text: str) -> str:
    """Strip image markdown, bare URLs, and sponsor/nav lines."""
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if re.match(r"^!\[.*?\]\(.*?\)$", stripped):          # image-only line
            continue
        if re.match(r"^https?://\S+$", stripped):              # bare URL
            continue
        if re.match(r"^\[.*?\]\(https?://\S+\)$", stripped):  # link-only line
            continue
        lines.append(line)
    return "\n".join(lines)


def _extract_picks_blocks(text: str) -> list[str]:
    lines = text.split("\n")
    blocks: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        # Skip H1 (page title) — only match H2–H5 to avoid pulling in the whole page
        heading_match = re.match(r"^(#{2,5})\s+(.+)$", line)
        if heading_match and any(kw in heading_match.group(2).lower() for kw in _PICKS_KEYWORDS):
            section_lines = [line]
            j = i + 1
            # Stop at the very next heading of any level
            while j < len(lines) and not re.match(r"^#{1,5}\s+", lines[j]):
                section_lines.append(lines[j])
                j += 1
            section = _clean_section("\n".join(section_lines)).strip()
            if section:
                blocks.append(section)
            i = j
            continue
        i += 1

    # Fallback: grab all markdown table rows if no headed sections matched
    if not blocks:
        table_lines = [l for l in lines if l.strip().startswith("|") and "|" in l[1:]]
        if table_lines:
            blocks.append("\n".join(table_lines))

    return blocks
