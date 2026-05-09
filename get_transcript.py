"""Extract and clean YouTube auto-captions via yt-dlp."""

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _clean_vtt(raw: str) -> str:
    """Strip VTT timestamps and deduplicate overlapping caption lines."""
    lines = []
    seen = set()

    # Remove the WEBVTT header block and cue identifiers
    for line in raw.splitlines():
        # Skip timestamp lines (e.g. "00:00:01.000 --> 00:00:04.000 ...")
        if re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}", line):
            continue
        # Skip the WEBVTT header and NOTE blocks
        if line.startswith("WEBVTT") or line.startswith("NOTE") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        # Strip inline VTT tags like <00:00:01.000><c>word</c>
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line:
            continue
        # Deduplicate consecutive repeated lines (VTT overlap artifact)
        if line not in seen:
            seen.add(line)
            lines.append(line)
        # Reset seen set every ~50 lines to allow legitimate repetition across the video
        if len(seen) > 50:
            seen.clear()

    return " ".join(lines)


def get_transcript(video_id: str) -> Optional[str]:
    """Download auto-captions for video_id and return clean plaintext."""
    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "yt-dlp",
            "--write-auto-sub",
            "--sub-lang", "en",
            "--skip-download",
            "--sub-format", "vtt",
            "--output", f"{tmpdir}/%(id)s.%(ext)s",
            "--no-playlist",
            "--quiet",
            url,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            logger.error("yt-dlp timed out for %s", video_id)
            return None
        except FileNotFoundError:
            logger.error("yt-dlp not found in PATH")
            return None

        # Find the downloaded .vtt file
        vtt_files = list(Path(tmpdir).glob("*.vtt"))
        if not vtt_files:
            logger.warning("No auto-captions found for %s. stderr: %s", video_id, result.stderr)
            return None

        raw = vtt_files[0].read_text(encoding="utf-8", errors="replace")

    cleaned = _clean_vtt(raw)
    logger.info("Transcript extracted for %s (%d chars)", video_id, len(cleaned))
    return cleaned if cleaned.strip() else None
