"""Scrape picks content from an external article URL."""

import logging
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag
from urllib.parse import quote

from config import WEBSHARE_PROXY_PASSWORD, WEBSHARE_PROXY_USERNAME

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

RETRY_DELAYS = [5, 15, 30]  # seconds between attempts on 429/5xx


def _proxies() -> Optional[dict]:
    if WEBSHARE_PROXY_USERNAME and WEBSHARE_PROXY_PASSWORD:
        user = quote(WEBSHARE_PROXY_USERNAME, safe="")
        passwd = quote(WEBSHARE_PROXY_PASSWORD, safe="")
        proxy_url = f"http://{user}:{passwd}@p.webshare.io:80"
        return {"http": proxy_url, "https": proxy_url}
    return None

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
    resp = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            logger.info("Scrape attempt %d for %s, waiting %ds", attempt + 1, url, delay)
            time.sleep(delay)
        try:
            resp = requests.get(url, headers=HEADERS, proxies=_proxies(), timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning("Got %d from %s, will retry", resp.status_code, url)
                continue
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            logger.error("Failed to fetch picks page %s: %s", url, exc)
            return None
    else:
        logger.error("All retries exhausted for %s (last status: %s)", url, resp.status_code if resp else "N/A")
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
