"""NBA Picks Automation — daily orchestrator."""

import logging
import sys
from datetime import datetime

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
from fetch_video import daft_filter, ev_filter, ev_score, fetch_latest_video
from get_pinned_comment import get_pinned_comment_url
from get_transcript import get_transcript
from scrape_picks import scrape_picks_page
from send_email import send_email
from summarize import summarize_with_gemini

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

DIVIDER = "━" * 25


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

    video = fetch_latest_video(channel_id, filter_fn, channel_label, score_fn)
    if not video:
        result["error"] = "No qualifying video found for today."
        return result

    result["video"] = video
    logger.info("[%s] Video: %s", channel_label, video["title"])

    result["transcript"] = get_transcript(video["video_id"])

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


def _format_channel_block(result: dict) -> str:
    icon = "📺"
    name = result["channel_name"]
    lines = [DIVIDER, f"{icon} {name}", DIVIDER]

    if result["error"]:
        lines.append(f"⚠️ {result['error']}")
        return "\n".join(lines)

    video = result["video"]
    lines.append(f"🎬 {video['title']}")
    lines.append(f"🔗 {video['url']}")
    lines.append("")

    summary = result["summary"] or "(AI summary unavailable.)"
    lines.append(summary)

    lines.append("")
    lines.append("📋 PINNED PICKS SHEET:")
    if result["scraped_picks"]:
        lines.append(result["scraped_picks"])
    elif result["picks_url"]:
        lines.append(f"(Could not scrape: {result['picks_url']})")
    else:
        lines.append("Not found.")

    return "\n".join(lines)


def build_report(ev_result: dict, daft_result: dict) -> tuple[str, str]:
    """Return (subject, body) for the email."""
    pht_tz = pytz.timezone(PHT)
    now_pht = datetime.now(pht_tz)
    date_str = now_pht.strftime("%B %d, %Y")
    ts_str = now_pht.strftime("%Y-%m-%d %H:%M PHT")

    subject = f"🏀 NBA Picks Report — {date_str}"

    header = f"🏀 NBA PICKS REPORT — {date_str}"
    ev_block = _format_channel_block(ev_result)
    daft_block = _format_channel_block(daft_result)
    footer = f"{DIVIDER}\n⏱ Generated {ts_str}"
    body = "\n\n".join([header, ev_block, daft_block, footer])

    return subject, body


def main() -> None:
    _check_secrets()
    logger.info("Starting NBA picks pipeline")

    ev_result = _process_channel(
        channel_id=EV_CHANNEL_ID,
        channel_label="EV",
        channel_name="EV (GuyBostonSports)",
        filter_fn=ev_filter,
        score_fn=ev_score,
        allowed_domains=EV_PICKS_DOMAINS,
    )

    daft_result = _process_channel(
        channel_id=DAFT_CHANNEL_ID,
        channel_label="DAFT",
        channel_name="DAFT (DaftPreviews)",
        filter_fn=daft_filter,
        allowed_domains=None,
    )

    subject, body = build_report(ev_result, daft_result)
    logger.info("Report built (%d chars)", len(body))

    send_email(subject, body)
    logger.info("Report emailed to %s", REPORT_RECIPIENT)


if __name__ == "__main__":
    main()
