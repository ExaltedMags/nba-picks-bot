"""WNBA Picks Automation — daily orchestrator."""

import logging
import sys
import time
from datetime import datetime
from typing import Optional

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
from fetch_video import fetch_latest_video, picks_score, wnba_filter, world_cup_filter
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

    summary = (result["summary"] or "").strip()
    if not summary:
        return "DEGRADED", "AI summary missing."
    if summary.startswith("(Gemini unavailable"):
        return "DEGRADED", "AI summary failed; only a raw excerpt is available."
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


def build_report(results: list[dict], notes: Optional[list[str]] = None) -> tuple[str, str]:
    """Return (subject, body) for the email from the channel results to show."""
    pht_tz = pytz.timezone(PHT)
    now_pht = datetime.now(pht_tz)
    date_str = now_pht.strftime("%B %d, %Y")
    ts_str = now_pht.strftime("%Y-%m-%d %H:%M PHT")

    subject = f"🎯 Daily Picks Report — {date_str}"
    header = f"🎯 DAILY PICKS REPORT — {date_str}"

    parts = [header, *[_format_channel_block(r) for r in results]]
    if notes:
        parts.append(f"{DIVIDER}\nℹ️ " + "\n".join(notes))
    parts.append(f"{DIVIDER}\n⏱ Generated {ts_str}")
    body = "\n\n".join(parts)

    return subject, body


def main() -> None:
    _check_secrets()
    logger.info("Starting daily picks pipeline")

    # Each source: (label, required, pipeline kwargs).
    #  - required sources (the two WNBA channels) must be OK or the email is
    #    blocked — you never get a partial/misleading report.
    #  - optional sources (Guy Boston's World Cup video) are additive: shown when
    #    OK, quietly skipped when there's no fresh video (e.g. once the World Cup
    #    is over), and noted but never shown broken if they fail.
    sources = [
        ("WNBA-EV", True, dict(
            channel_id=EV_CHANNEL_ID,
            channel_label="EV",
            channel_name="Guy Boston Sports (WNBA)",
            filter_fn=wnba_filter,
            score_fn=picks_score,
            allowed_domains=EV_PICKS_DOMAINS,
        )),
        ("WNBA-DYJ", True, dict(
            channel_id=DYJ_CHANNEL_ID,
            channel_label="DYJ",
            channel_name="Do Your Job Sports (WNBA)",
            filter_fn=wnba_filter,
            score_fn=picks_score,
            allowed_domains=None,
        )),
        ("WC-EV", False, dict(
            channel_id=EV_CHANNEL_ID,
            channel_label="EV-WC",
            channel_name="Guy Boston Sports (World Cup)",
            filter_fn=world_cup_filter,
            score_fn=picks_score,
            allowed_domains=EV_PICKS_DOMAINS,
        )),
    ]

    processed = []  # (label, required, result, status, note)
    for label, required, spec in sources:
        result = _process_channel_resilient(spec)
        status, note = _result_health(result)
        processed.append((label, required, result, status, note))

    # Required-source guardrail: only send when every required source is OK.
    #   - DEGRADED (a video existed but couldn't be processed) → block + exit 1
    #     so the run goes red and you're alerted that something broke.
    #   - EMPTY (no fresh video — off-day or not posted yet) → block + exit 0,
    #     since nothing actually broke; there's just nothing to report.
    required_bad = [(lbl, st, nt) for lbl, req, _, st, nt in processed if req and st != "OK"]
    if required_bad:
        for lbl, st, nt in required_bad:
            logger.error("[%s] %s: %s", lbl, st, nt)
        has_degraded = any(st == "DEGRADED" for _, st, _ in required_bad)
        logger.error("Email blocked — required source(s) not OK. No report sent.")
        sys.exit(1 if has_degraded else 0)

    # Show every source that produced a clean result; note (but don't show)
    # optional sources that had a video but failed to summarize.
    to_show = [result for _, _, result, st, _ in processed if st == "OK"]
    notes = [
        f"{result['channel_name']}: video found but could not be summarized — skipped."
        for _, req, result, st, _ in processed
        if not req and st == "DEGRADED"
    ]

    subject, body = build_report(to_show, notes)
    logger.info("Report built (%d chars)", len(body))

    send_email(subject, body)
    logger.info("Report emailed to %s", REPORT_RECIPIENT)


if __name__ == "__main__":
    main()
