"""Summarize NBA picks via the Gemini API."""

import logging
from typing import Optional

import google.generativeai as genai

from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a sports betting assistant. Extract all NBA picks clearly and concisely. "
    "For each pick, output: Game | Pick | Line/Spread/Total | Confidence or Units if mentioned. "
    "Also note any key reasoning if briefly stated. Be terse. Output as a clean list."
)

MAX_TRANSCRIPT_CHARS = 80_000


def summarize_with_gemini(
    transcript: Optional[str],
    scraped_picks: Optional[str],
    channel_name: str,
    video_title: str,
) -> str:
    """Return an AI-formatted picks summary string."""
    if not transcript and not scraped_picks:
        return "(No transcript or picks sheet available — cannot summarize.)"

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
    )

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

    try:
        response = model.generate_content(user_message)
        return response.text.strip()
    except Exception as exc:
        logger.error("Gemini API error for %s: %s", channel_name, exc)
        # Fallback: return the first 1500 chars of transcript so the report is still useful
        fallback = (transcript or scraped_picks or "")[:1500]
        return f"(Gemini unavailable — raw excerpt)\n\n{fallback}"
