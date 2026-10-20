"""Extract structured betting picks via the Gemini API (JSON mode)."""

import json
import logging
import time
from typing import Optional

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a sports betting assistant. Extract EVERY betting pick from the "
    "content below — sides, totals, money lines, spreads, player props, and "
    "parlays — including casually stated leans ('I like', 'I'm leaning', "
    "'lean', 'play', 'side'). Respond ONLY with JSON in this exact shape:\n"
    "{\n"
    '  "no_picks_stated": false,\n'
    '  "picks": [\n'
    "    {\n"
    '      "game": "matchup, e.g. \'Boston Celtics vs. New York Knicks\'",\n'
    '      "pick": "the wager, short and specific, e.g. \'Lynx ML\' or \'Under 173.5\'",\n'
    '      "line": "odds/spread/total plus any line-movement note, or \\"\\" if not stated",\n'
    '      "units": "units or confidence as stated, e.g. \'0.5u\' or \'Lean — not official\', or \\"\\"",\n'
    '      "reasoning": "key reasoning in one terse sentence, or \\"\\""\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "Keep every field terse. Do not invent picks, odds, or reasoning that were "
    "not stated. Treat any wager mentioned as a pick even if the league name is "
    "absent. If and ONLY IF no wager is stated anywhere, return "
    '{"no_picks_stated": true, "picks": []}.'
)

MAX_TRANSCRIPT_CHARS = 80_000

# Retry transient Gemini failures (503 model-overloaded, 429 rate limit, timeouts)
# AND broken/empty content before giving up.
_RETRY_DELAYS = [2, 5, 10]

# Appended on retry to push the model to either extract picks or flag no-picks.
_ESCALATION = (
    "\n\n[RETRY] The previous attempt did not return usable JSON picks. Re-read "
    "the content and list EVERY wager mentioned — sides, totals, player props, "
    "and parlays — including casually stated leans. If and ONLY IF no wager is "
    'stated anywhere, return {"no_picks_stated": true, "picks": []}.'
)


def _parse_picks_json(text: str) -> Optional[dict]:
    """Parse and validate the model's JSON. Return a summary dict, or None if broken."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    raw_picks = data.get("picks")
    if not isinstance(raw_picks, list):
        return None

    picks = []
    for item in raw_picks:
        if not isinstance(item, dict):
            continue
        pick = str(item.get("pick") or "").strip()
        if not pick:
            continue
        picks.append(
            {
                "game": str(item.get("game") or "").strip(),
                "pick": pick,
                "line": str(item.get("line") or "").strip(),
                "units": str(item.get("units") or "").strip(),
                "reasoning": str(item.get("reasoning") or "").strip(),
            }
        )

    no_picks = bool(data.get("no_picks_stated"))
    if not picks and not no_picks:
        # Neither picks nor an explicit "no picks" flag — a non-answer; retry.
        return None
    return {"picks": picks, "no_picks": no_picks and not picks}


def summarize_with_gemini(
    transcript: Optional[str],
    scraped_picks: Optional[str],
    channel_name: str,
    video_title: str,
) -> dict:
    """
    Return a summary dict:
      {"picks": [{game, pick, line, units, reasoning}], "no_picks": bool}
    or, when extraction is impossible, {"picks": [], "no_picks": False,
    "degraded": "<reason>"} so the caller can treat the channel as DEGRADED.
    """
    if not transcript and not scraped_picks:
        return {
            "picks": [],
            "no_picks": False,
            "degraded": "No transcript or picks sheet available — cannot summarize.",
        }

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
                    response_mime_type="application/json",
                ),
            )
            text = (response.text or "").strip()
        except Exception as exc:  # noqa: BLE001 — SDK raises many transient error types
            last_exc = exc
            logger.warning("Gemini attempt %d failed for %s: %s", attempt + 1, channel_name, exc)
            continue

        summary = _parse_picks_json(text)
        if summary is not None:
            return summary
        logger.warning(
            "Gemini attempt %d for %s produced broken/unparseable output, will retry",
            attempt + 1, channel_name,
        )

    logger.error("Gemini unusable for %s after retries: %s", channel_name, last_exc)
    return {
        "picks": [],
        "no_picks": False,
        "degraded": "AI pick extraction failed after retries.",
    }
