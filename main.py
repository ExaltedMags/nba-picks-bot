"""WNBA Picks Automation — daily orchestrator."""

import logging
import sys
from datetime import datetime

import pytz

from config import (
    DYJ_CHANNEL_ID,
    EV_CHANNEL_ID,
    EV_PICKS_DOMAINS,
    GEMINI_API_KEY,
    GMAIL_APP_PASSWORD,
    GMAIL_SENDER,
    PHT,
    REPORT_RECIPIENT,
    YOUTUBE_API_KEY,
)
from fetch_video import fetch_latest_video, wnba_filter, wnba_score
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
    max_days_back: int = 1,
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

    video = fetch_latest_video(channel_id, filter_fn, channel_label, score_fn, max_days_back)
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


def _result_health(result: dict) -> tuple[str, str]:
    """Classify a channel result as OK / DEGRADED / FAILED with a short note."""
    if result["error"]:
        return "FAILED", result["error"]

    summary = (result["summary"] or "").strip()
    if not summary:
        return "DEGRADED", "AI summary missing."
    if summary.startswith("(Gemini unavailable"):
        return "DEGRADED", "AI summary failed; showing raw transcript excerpt."
    if not result["transcript"] and not result["scraped_picks"]:
        return "DEGRADED", "No transcript or picks sheet could be retrieved."
    return "OK", ""


def _format_channel_block(result: dict) -> str:
    icon = "📺"
    name = result["channel_name"]
    lines = [DIVIDER, f"{icon} {name}", DIVIDER]

    if result["error"]:
        lines.append(f"⚠️ {result['error']}")
        return "\n".join(lines)

    status, note = _result_health(result)
    if status != "OK":
        lines.append(f"⚠️ [{status}] {note}")

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


def build_report(ev_result: dict, dyj_result: dict) -> tuple[str, str]:
    """Return (subject, body) for the email."""
    pht_tz = pytz.timezone(PHT)
    now_pht = datetime.now(pht_tz)
    date_str = now_pht.strftime("%B %d, %Y")
    ts_str = now_pht.strftime("%Y-%m-%d %H:%M PHT")

    statuses = [_result_health(ev_result)[0], _result_health(dyj_result)[0]]
    flag = "⚠️ " if any(s != "OK" for s in statuses) else ""

    subject = f"{flag}🏀 WNBA Picks Report — {date_str}"

    header = f"🏀 WNBA PICKS REPORT — {date_str}"
    ev_block = _format_channel_block(ev_result)
    dyj_block = _format_channel_block(dyj_result)
    footer = f"{DIVIDER}\n⏱ Generated {ts_str}"
    body = "\n\n".join([header, ev_block, dyj_block, footer])

    return subject, body


def main() -> None:
    _check_secrets()
    logger.info("Starting WNBA picks pipeline")

    ev_result = _process_channel(
        channel_id=EV_CHANNEL_ID,
        channel_label="EV",
        channel_name="Guy Boston Sports (WNBA)",
        filter_fn=wnba_filter,
        score_fn=wnba_score,
        allowed_domains=EV_PICKS_DOMAINS,
    )

    dyj_result = _process_channel(
        channel_id=DYJ_CHANNEL_ID,
        channel_label="DYJ",
        channel_name="Do Your Job Sports (WNBA)",
        filter_fn=wnba_filter,
        score_fn=wnba_score,
        allowed_domains=None,
    )

    subject, body = build_report(ev_result, dyj_result)
    logger.info("Report built (%d chars)", len(body))

    send_email(subject, body)
    logger.info("Report emailed to %s", REPORT_RECIPIENT)


if __name__ == "__main__":
    main()
