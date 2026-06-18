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
# AND broken/empty content before falling back to a raw excerpt.
_RETRY_DELAYS = [2, 5, 10]

# Explicit sentinel the model must return when a video genuinely states no picks.
# This lets us distinguish "model refused / produced junk" (retry) from
# "there really are no picks" (stop cleanly).
NO_PICKS_SENTINEL = "NO_PICKS_STATED"
NO_PICKS_MESSAGE = "(No betting picks were stated in this video.)"

# Phrases that signal the model declined or returned a non-answer rather than picks.
_REFUSAL_PHRASES = (
    "no picks", "no betting", "no wagers", "no bets", "cannot summarize",
    "unable to", "i don't see", "i do not see", "i cannot", "i can't",
    "as an ai", "i'm sorry", "i am sorry", "no relevant", "not found",
)

# Appended on retry to push the model to either extract picks or emit the sentinel.
_ESCALATION = (
    "\n\n[RETRY] The previous attempt did not return usable picks. Re-read the "
    "content and list EVERY wager mentioned — sides, totals, player props, and "
    "parlays — including casually stated leans ('I like', 'I'm leaning', 'lean', "
    "'play', 'side', 'total'). If and ONLY IF no wager is stated anywhere, reply "
    f"with exactly this and nothing else: {NO_PICKS_SENTINEL}"
)


def _is_broken_summary(text: str) -> Optional[str]:
    """Return a reason string if the summary is broken/unusable, else None."""
    if not text:
        return "empty response"
    if text.strip() == NO_PICKS_SENTINEL:
        return None  # valid, explicit "no picks" outcome — not broken
    low = text.lower()
    # A genuine picks list is rarely short; a refusal/non-answer almost always is.
    if len(text) < 400 and any(phrase in low for phrase in _REFUSAL_PHRASES):
        return "refusal/no-content phrasing"
    return None


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
        # Escalate the prompt on every retry so we don't just re-trigger the same
        # refusal/empty output.
        contents = user_message if attempt == 0 else user_message + _ESCALATION
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                ),
            )
            text = (response.text or "").strip()
        except Exception as exc:  # noqa: BLE001 — SDK raises many transient error types
            last_exc = exc
            logger.warning("Gemini attempt %d failed for %s: %s", attempt + 1, channel_name, exc)
            continue

        reason = _is_broken_summary(text)
        if reason is None:
            if text.strip() == NO_PICKS_SENTINEL:
                return NO_PICKS_MESSAGE
            return text
        logger.warning(
            "Gemini attempt %d for %s produced broken output (%s), will retry",
            attempt + 1, channel_name, reason,
        )

    logger.error("Gemini unusable for %s after retries: %s", channel_name, last_exc)
    fallback = (transcript or scraped_picks or "")[:1500]
    return f"(Gemini unavailable — raw excerpt)\n\n{fallback}"
