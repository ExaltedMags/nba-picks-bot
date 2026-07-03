"""Render the daily picks report as plain text and email-safe HTML.

The HTML uses tables + inline styles only (no <style> blocks, no external
assets) so it renders consistently in Gmail, Apple Mail, and Outlook, on both
mobile and desktop. Layout principles, in order:

  1. The PICK is the headline of each card — bold, first, largest.
  2. Picks are grouped under their game so matchups are never repeated.
  3. Line and units render as small chips — scannable at a glance.
  4. Reasoning is present but visually quiet (small, muted).
"""

import html as _html
import re
from typing import Optional

NO_PICKS_MESSAGE = "No betting picks were stated in this video."

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_LEAN_RE = re.compile(r"\blean\b|not\s+(an\s+)?official", re.IGNORECASE)


def _group_by_game(picks: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group picks by game, preserving first-seen order of games."""
    groups: dict[str, list[dict]] = {}
    for pick in picks:
        game = pick.get("game", "").strip() or "Other picks"
        groups.setdefault(game, []).append(pick)
    return list(groups.items())


def _is_lean(pick: dict) -> bool:
    return bool(_LEAN_RE.search(pick.get("units", "")))


# ---------------------------------------------------------------------------
# Plain-text body (fallback part for clients that don't render HTML)
# ---------------------------------------------------------------------------

_DIVIDER = "─" * 30


def render_text(
    results: list[dict],
    skipped: Optional[list[tuple[str, str]]],
    date_str: str,
    ts_str: str,
) -> str:
    parts = [f"DAILY PICKS REPORT — {date_str}"]

    for result in results:
        lines = [_DIVIDER, result["channel_name"].upper(), _DIVIDER]
        video = result["video"]
        lines.append(video["title"])
        lines.append(video["url"])
        lines.append("")

        summary = result.get("summary") or {}
        if summary.get("no_picks"):
            lines.append(NO_PICKS_MESSAGE)
        for game, picks in _group_by_game(summary.get("picks", [])):
            lines.append(game)
            for p in picks:
                detail = "  ·  ".join(x for x in (p.get("line"), p.get("units")) if x)
                lines.append(f"  • {p['pick']}" + (f"   ({detail})" if detail else ""))
                if p.get("reasoning"):
                    lines.append(f"      {p['reasoning']}")
            lines.append("")

        if result.get("scraped_picks"):
            lines.append("PINNED PICKS SHEET")
            lines.append(result["scraped_picks"])
        elif result.get("picks_url"):
            lines.append(f"Picks sheet (could not scrape): {result['picks_url']}")

        parts.append("\n".join(lines).rstrip())

    if skipped:
        lines = [_DIVIDER, "Not included today:"]
        lines += [f"  • {name} — {reason}" for name, reason in skipped]
        parts.append("\n".join(lines))

    parts.append(f"{_DIVIDER}\nGenerated {ts_str}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# HTML body
# ---------------------------------------------------------------------------

_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,"
    "sans-serif"
)


def _esc(text: str) -> str:
    return _html.escape(text, quote=True)


def _chip(label: str, bg: str, fg: str) -> str:
    return (
        f'<span style="display:inline-block;background:{bg};color:{fg};'
        f"font-family:{_FONT};font-size:12px;font-weight:600;line-height:1;padding:4px 9px;"
        f'border-radius:999px;margin:0 6px 4px 0;">{_esc(label)}</span>'
    )


def _pick_card(pick: dict) -> str:
    # Leans get an amber accent so official plays and leans are separable at a
    # glance; official plays get the indigo accent.
    accent = "#d97706" if _is_lean(pick) else "#4f46e5"

    chips = []
    if pick.get("line"):
        chips.append(_chip(pick["line"], "#eef2ff", "#4338ca"))
    if pick.get("units"):
        if _is_lean(pick):
            chips.append(_chip(pick["units"], "#fef3c7", "#92400e"))
        else:
            chips.append(_chip(pick["units"], "#ecfdf5", "#047857"))
    chips_html = (
        f'<div style="padding-top:7px;">{"".join(chips)}</div>' if chips else ""
    )

    reasoning_html = ""
    if pick.get("reasoning"):
        reasoning_html = (
            f'<div style="font-family:{_FONT};font-size:13px;color:#64748b;'
            f'line-height:1.5;padding-top:6px;">{_esc(pick["reasoning"])}</div>'
        )

    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border:1px solid #e2e8f0;border-left:4px solid {accent};'
        f'border-radius:8px;margin:0 0 8px;background:#ffffff;">'
        f'<tr><td style="padding:10px 14px;font-family:{_FONT};">'
        f'<div style="font-size:16px;font-weight:700;'
        f'color:#0f172a;line-height:1.3;">{_esc(pick["pick"])}</div>'
        f"{chips_html}{reasoning_html}"
        f"</td></tr></table>"
    )


def _game_group(game: str, picks: list[dict]) -> str:
    header = (
        f'<div style="font-family:{_FONT};font-size:13px;font-weight:700;'
        f"color:#475569;text-transform:uppercase;letter-spacing:0.04em;"
        f'padding:14px 0 6px;">{_esc(game)}</div>'
    )
    return header + "".join(_pick_card(p) for p in picks)


def _channel_section(result: dict) -> str:
    video = result["video"]
    summary = result.get("summary") or {}

    header = (
        f'<div style="font-family:{_FONT};font-size:18px;font-weight:800;'
        f'color:#0f172a;padding-bottom:2px;">📺 {_esc(result["channel_name"])}</div>'
        f'<div style="font-family:{_FONT};font-size:13px;line-height:1.4;">'
        f'<a href="{_esc(video["url"])}" style="color:#4f46e5;'
        f'text-decoration:none;">▶ {_esc(video["title"])}</a></div>'
    )

    body = ""
    if summary.get("no_picks"):
        body = (
            f'<div style="font-family:{_FONT};font-size:14px;color:#64748b;'
            f'padding-top:10px;">{_esc(NO_PICKS_MESSAGE)}</div>'
        )
    else:
        body = "".join(
            _game_group(game, picks)
            for game, picks in _group_by_game(summary.get("picks", []))
        )

    sheet = ""
    if result.get("scraped_picks"):
        sheet = (
            f'<div style="font-family:{_FONT};font-size:12px;font-weight:700;'
            f"color:#94a3b8;text-transform:uppercase;letter-spacing:0.04em;"
            f'padding:14px 0 6px;">📋 Pinned picks sheet</div>'
            f'<div style="font-family:{_FONT};font-size:12px;color:#475569;'
            f"line-height:1.55;background:#f8fafc;border:1px solid #e2e8f0;"
            f"border-radius:8px;padding:10px 14px;white-space:pre-wrap;"
            f'word-break:break-word;">{_esc(result["scraped_picks"])}</div>'
        )
    elif result.get("picks_url"):
        sheet = (
            f'<div style="font-family:{_FONT};font-size:12px;color:#94a3b8;'
            f'padding-top:12px;">Picks sheet (could not scrape): '
            f'<a href="{_esc(result["picks_url"])}" style="color:#4f46e5;">'
            f'{_esc(result["picks_url"])}</a></div>'
        )

    return (
        f'<tr><td style="padding:18px 20px;border-top:1px solid #e2e8f0;">'
        f"{header}{body}{sheet}</td></tr>"
    )


def render_html(
    results: list[dict],
    skipped: Optional[list[tuple[str, str]]],
    date_str: str,
    ts_str: str,
) -> str:
    sections = "".join(_channel_section(r) for r in results)

    skipped_html = ""
    if skipped:
        items = "".join(
            f'<div style="padding-top:2px;">• {_esc(name)} — {_esc(reason)}</div>'
            for name, reason in skipped
        )
        skipped_html = (
            f'<tr><td style="padding:14px 20px;border-top:1px solid #e2e8f0;'
            f'font-family:{_FONT};font-size:12px;color:#94a3b8;line-height:1.5;">'
            f"<div>Not included today:</div>{items}</td></tr>"
        )

    return f"""\
<div style="margin:0;padding:0;background:#f1f5f9;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;">
<tr><td align="center" style="padding:20px 10px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:12px;border:1px solid #e2e8f0;">
<tr><td style="padding:20px 20px 14px;">
<div style="font-family:{_FONT};font-size:20px;font-weight:800;color:#0f172a;">🎯 Daily Picks Report</div>
<div style="font-family:{_FONT};font-size:13px;color:#64748b;padding-top:2px;">{_esc(date_str)}</div>
</td></tr>
{sections}
{skipped_html}
<tr><td style="padding:12px 20px 16px;border-top:1px solid #e2e8f0;font-family:{_FONT};font-size:11px;color:#94a3b8;">⏱ Generated {_esc(ts_str)}</td></tr>
</table>
</td></tr>
</table>
</div>
"""
