"""NBA Picks Automation — daily orchestrator."""

import logging
import sys
import time
from datetime import datetime
from typing import Optional

import pytz

from config import (
    DAFT_CHANNEL_ID,
    EV_CHANNEL_ID,
    EV_PICKS_DOMAINS,
    GEMINI_API_KEY,
    GMAIL_APP_PASSWORD,
    GMAIL_SENDER,
    PHT,
    REPORT_RECIPIENT,
    YOUTUBE_API_KEY,
)
from fetch_video import fetch_latest_video, nba_filter, picks_score
from get_pinned_comment import get_pinned_comment_url
from get_transcript import get_transcript
from render_report import render_html, render_text
from scrape_picks import scrape_picks_page
from send_email import send_email
from summarize import summarize_with_gemini

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Full-pipeline retry policy: re-run a channel that produced DEGRADED output
# (e.g. the AI fell back to a raw excerpt) before giving up on it.
_CHANNEL_ATTEMPTS = 3
_CHANNEL_BACKOFF = [20, 60]  # seconds between full-pipeline attempts


def _check_secrets() -> None:
    missing = [
        name
        for name, val in [
            ("YOUTUBE_API_KEY", YOUTUBE_API_KEY),
            ("GEMINI_API_KEY", GEMINI_API_KEY),
            ("GMAIL_SENDER", GMAIL_SENDER),
            ("GMAIL_APP_PASSWORD", GMAIL_APP_PASSWORD),
            ("REPORT_RECIPIENT", REPORT_RECIPIENT),
        ]
        if not val
    ]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)


def _process_channel(
    channel_id: str,
    channel_label: str,
    channel_name: str,
    filter_fn,
    score_fn=None,
    allowed_domains=None,
    max_age_hours=None,
) -> dict:
    """Run the full pipeline for one channel and return a result dict."""
    result = {
        "channel_name": channel_name,
        "video": None,
        "transcript": None,
        "picks_url": None,
        "scraped_picks": None,
        "summary": None,
        "error": None,
    }

    video = fetch_latest_video(channel_id, filter_fn, channel_label, score_fn, max_age_hours)
    if not video:
        result["error"] = "No fresh video found for today."
        return result

    result["video"] = video
    logger.info("[%s] Video: %s", channel_label, video["title"])

    result["transcript"] = get_transcript(video["video_id"])

    # Only sources with a known picks-sheet domain look at the pinned comment;
    # for the rest it's typically sportsbook/affiliate links, not picks.
    picks_url = None
    if allowed_domains:
        picks_url = get_pinned_comment_url(video["video_id"], channel_id, allowed_domains)
    result["picks_url"] = picks_url

    if picks_url:
        result["scraped_picks"] = scrape_picks_page(picks_url)

    result["summary"] = summarize_with_gemini(
        result["transcript"],
        result["scraped_picks"],
        channel_name,
        video["title"],
    )

    return result


def _result_health(result: dict) -> tuple[str, str]:
    """
    Classify a channel result with a short note.

    - OK:       clean, usable summary.
    - EMPTY:    no qualifying video (legitimate off-day) — safe to report as-is.
    - DEGRADED: a video existed but could not be turned into a usable summary.
                This is the state that triggers a full retry and, if it
                persists, blocks the whole email.
    """
    if result["error"]:
        return "EMPTY", result["error"]

    summary = result["summary"] or {}
    if not isinstance(summary, dict) or (not summary.get("picks") and not summary.get("no_picks") and not summary.get("degraded")):
        return "DEGRADED", "AI summary missing."
    if summary.get("degraded"):
        return "DEGRADED", summary["degraded"]
    if not result["transcript"] and not result["scraped_picks"]:
        return "DEGRADED", "No transcript or picks sheet could be retrieved."
    return "OK", ""


def _process_channel_resilient(spec: dict) -> dict:
    """Run a channel pipeline, fully re-running it while the output is DEGRADED."""
    result = _process_channel(**spec)
    attempt = 1
    while attempt < _CHANNEL_ATTEMPTS:
        status, note = _result_health(result)
        if status != "DEGRADED":
            return result
        delay = _CHANNEL_BACKOFF[min(attempt - 1, len(_CHANNEL_BACKOFF) - 1)]
        logger.warning(
            "[%s] degraded (%s) — full pipeline retry %d/%d after %ds",
            spec["channel_label"], note, attempt + 1, _CHANNEL_ATTEMPTS, delay,
        )
        time.sleep(delay)
        result = _process_channel(**spec)
        attempt += 1
    return result


def build_report(
    results: list[dict], skipped: Optional[list[tuple[str, str]]] = None
) -> tuple[str, str, str]:
    """
    Return (subject, text_body, html_body) for the email.

    `results` are the OK channel results to show; `skipped` is a list of
    (channel_name, reason) for sources that were checked but not included, listed
    transparently so the recipient always knows the full picture.
    """
    pht_tz = pytz.timezone(PHT)
    now_pht = datetime.now(pht_tz)
    date_str = now_pht.strftime("%B %d, %Y")
    ts_str = now_pht.strftime("%Y-%m-%d %H:%M PHT")

    subject = f"🎯 Daily Picks Report — {date_str}"
    text_body = render_text(results, skipped, date_str, ts_str)
    html_body = render_html(results, skipped, date_str, ts_str)

    return subject, text_body, html_body


def main() -> None:
    _check_secrets()
    logger.info("Starting daily picks pipeline")

    sources = [
        dict(
            channel_id=EV_CHANNEL_ID,
            channel_label="EV",
            channel_name="Guy Boston Sports (NBA)",
            filter_fn=nba_filter,
            score_fn=picks_score,
            allowed_domains=EV_PICKS_DOMAINS,
        ),
        dict(
            channel_id=DAFT_CHANNEL_ID,
            channel_label="DAFT",
            channel_name="Daft Previews (NBA)",
            filter_fn=nba_filter,
            score_fn=picks_score,
            allowed_domains=None,
        ),
    ]

    processed = []  # (result, status, note)
    for spec in sources:
        result = _process_channel_resilient(spec)
        status, note = _result_health(result)
        processed.append((result, status, note))

    # Send whenever at least one source produced clean content. Every source is
    # treated the same:
    #   - OK       → shown.
    #   - EMPTY    → omitted, listed transparently in "Not included today".
    #   - DEGRADED → omitted (never shown broken), also listed there.
    to_show = [result for result, st, _ in processed if st == "OK"]
    skipped = [
        (result["channel_name"], note) for result, st, note in processed if st != "OK"
    ]
    for result, st, note in processed:
        if st != "OK":
            logger.warning("[%s] %s: %s", result["channel_name"], st, note)

    if not to_show:
        # Nothing usable. Fail loudly only if something actually broke; a pure
        # off-day (everything EMPTY) is a clean no-op.
        has_degraded = any(st == "DEGRADED" for _, st, _ in processed)
        if has_degraded:
            logger.error("No usable content and a source broke. No email sent.")
            sys.exit(1)
        logger.info("No fresh videos for any source today. No email sent.")
        sys.exit(0)

    subject, text_body, html_body = build_report(to_show, skipped)
    logger.info("Report built (%d chars text, %d chars html)", len(text_body), len(html_body))

    send_email(subject, text_body, html_body)
    logger.info("Report emailed to %s", REPORT_RECIPIENT)


if __name__ == "__main__":
    main()
