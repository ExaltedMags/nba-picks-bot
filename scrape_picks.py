"""Scrape picks content from an external article URL."""

import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

PICKS_KEYWORDS = {"pick", "bet", "prediction", "best bet", "best bets", "plays"}


def _heading_is_picks_related(tag: Tag) -> bool:
    return any(kw in tag.get_text(separator=" ").lower() for kw in PICKS_KEYWORDS)


def _table_to_text(table: Tag) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(separator=" ", strip=True) for td in tr.find_all(["th", "td"])]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _list_to_text(lst: Tag) -> str:
    items = [li.get_text(separator=" ", strip=True) for li in lst.find_all("li")]
    return "\n".join(f"• {item}" for item in items if item)


def scrape_picks_page(url: str) -> Optional[str]:
    """Return a plaintext picks block extracted from the article at url."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch picks page %s: %s", url, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    blocks: list[str] = []

    # Strategy 1: extract tables/lists that follow a picks-related heading
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5"])
    for heading in headings:
        if not _heading_is_picks_related(heading):
            continue
        # Walk siblings until the next heading
        sibling = heading.find_next_sibling()
        while sibling and sibling.name not in ("h1", "h2", "h3", "h4", "h5"):
            if sibling.name == "table":
                text = _table_to_text(sibling)
                if text:
                    blocks.append(f"[{heading.get_text(strip=True)}]\n{text}")
            elif sibling.name in ("ul", "ol"):
                text = _list_to_text(sibling)
                if text:
                    blocks.append(f"[{heading.get_text(strip=True)}]\n{text}")
            elif sibling.name in ("p", "div"):
                # Include paragraphs that mention picks keywords
                t = sibling.get_text(separator=" ", strip=True)
                if any(kw in t.lower() for kw in PICKS_KEYWORDS) and len(t) > 20:
                    blocks.append(t)
            sibling = sibling.find_next_sibling()

    # Strategy 2: any table on the page if nothing found yet
    if not blocks:
        for table in soup.find_all("table"):
            text = _table_to_text(table)
            if text:
                blocks.append(text)

    if not blocks:
        logger.warning("No picks content found at %s", url)
        return None

    result = "\n\n".join(blocks)
    logger.info("Scraped %d chars from %s", len(result), url)
    return result
