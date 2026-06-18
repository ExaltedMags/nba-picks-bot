"""Summarize WNBA picks via the Gemini API."""

import logging
import time
from typing import Optional

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a sports betting assistant. The content below is about WNBA "
    "(women's professional basketball) betting. Extract all betting picks "
    "clearly and concisely — including sides, totals, player props, and parlays. "
    "For each pick, output: Game | Pick | Line/Spread/Total | Confidence or Units if mentioned. "
    "Also note any key reasoning if briefly stated. Be terse. Output as a clean list. "
    "Do not say picks are missing just because a specific league name is absent — "
    "treat any basketball wager mentioned as a pick."
)

MAX_TRANSCRIPT_CHARS = 80_000

# Retry transient Gemini failures (503 model-overloaded, 429 rate limit, timeouts)
# before falling back to a raw excerpt.
_RETRY_DELAYS = [2, 5, 10]


def summarize_with_gemini(
    transcript: Optional[str],
    scraped_picks: Optional[str],
    channel_name: str,
    video_title: str,
) -> str:
    if not transcript and not scraped_picks:
        return "(No transcript or picks sheet available — cannot summarize.)"

    parts: list[str] = [f"Channel: {channel_name}", f"Video: {video_title}", ""]

    if transcript:
        truncated = transcript[:MAX_TRANSCRIPT_CHARS]
        if len(transcript) > MAX_TRANSCRIPT_CHARS:
            truncated += "\n[transcript truncated]"
        parts.append("=== VIDEO TRANSCRIPT ===")
        parts.append(truncated)

    if scraped_picks:
        parts.append("\n=== PICKS SHEET (from pinned comment article) ===")
        parts.append(scraped_picks)

    user_message = "\n".join(parts)

    client = genai.Client(api_key=GEMINI_API_KEY)
    last_exc: Optional[Exception] = None

    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            logger.info(
                "Retrying Gemini for %s (attempt %d) after %ds", channel_name, attempt + 1, delay
            )
            time.sleep(delay)
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                ),
            )
            text = (response.text or "").strip()
            if text:
                return text
            logger.warning("Gemini returned empty text for %s, will retry", channel_name)
        except Exception as exc:  # noqa: BLE001 — SDK raises many transient error types
            last_exc = exc
            logger.warning("Gemini attempt %d failed for %s: %s", attempt + 1, channel_name, exc)

    logger.error("Gemini unavailable for %s after retries: %s", channel_name, last_exc)
    fallback = (transcript or scraped_picks or "")[:1500]
    return f"(Gemini unavailable — raw excerpt)\n\n{fallback}"
