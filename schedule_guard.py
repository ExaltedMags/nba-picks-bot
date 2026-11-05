"""Decide whether this workflow run should do the daily report.

The workflow can be started by several triggers (an external cron calling
workflow_dispatch, GitHub's own `schedule`, or a manual click). This guard
makes them safe to stack:

- Send window: only runs whose start time falls inside the PHT window
  (default 21:30–01:00) proceed. A GitHub `schedule` run that shows up hours
  late (e.g. 3–4 AM) exits as a no-op instead of emailing in the middle of the
  night.
- Report day: a key like `2026-11-05` identifying "tonight's" report. Runs
  just after midnight still map to the previous evening, so a 00:30 run is the
  same report as a 22:00 run. The workflow uses this key to send at most one
  email per night.

Stdlib only, so it runs before Python dependencies are installed. Writes
`proceed`, `in_window`, `report_day` and `reason` to $GITHUB_OUTPUT when
available and always prints them. `in_window` is reported separately from
`proceed` so a forced run outside the window (e.g. a 9 AM test) doesn't mark
tonight's report as already sent.

Env:
  FORCE              "true" skips the window check (manual runs).
  SEND_WINDOW_START  "HH:MM" PHT, default 21:30.
  SEND_WINDOW_END    "HH:MM" PHT, default 01:00 (may be past midnight).
  GUARD_NOW          ISO timestamp override, for testing.
"""

import os
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

PHT = ZoneInfo("Asia/Manila")

# Shift used to assign post-midnight runs to the previous evening's report.
# Anything before 06:00 PHT counts as "last night".
_DAY_ROLLOVER = timedelta(hours=6)


def _parse_hhmm(value: str, default: str) -> time:
    raw = (value or "").strip() or default
    try:
        hh, mm = raw.split(":")
        return time(int(hh), int(mm))
    except ValueError:
        print(f"Invalid window time {raw!r}, using {default}", file=sys.stderr)
        hh, mm = default.split(":")
        return time(int(hh), int(mm))


def in_window(now: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= now < end
    # Window wraps past midnight, e.g. 21:30–01:00.
    return now >= start or now < end


def report_day(now_pht: datetime) -> str:
    return (now_pht - _DAY_ROLLOVER).date().isoformat()


def decide(now_pht: datetime, force: bool, start: time, end: time) -> tuple[bool, str]:
    window = f"{start:%H:%M}–{end:%H:%M} PHT"
    if force:
        return True, f"forced run (window {window} ignored)"
    if in_window(now_pht.time(), start, end):
        return True, f"{now_pht:%H:%M} PHT is inside the send window {window}"
    return False, f"{now_pht:%H:%M} PHT is outside the send window {window}; skipping"


def main() -> None:
    override = os.environ.get("GUARD_NOW")
    now = datetime.fromisoformat(override) if override else datetime.now(PHT)
    now_pht = now.astimezone(PHT)

    force = os.environ.get("FORCE", "").strip().lower() == "true"
    start = _parse_hhmm(os.environ.get("SEND_WINDOW_START", ""), "21:30")
    end = _parse_hhmm(os.environ.get("SEND_WINDOW_END", ""), "01:00")

    proceed, reason = decide(now_pht, force, start, end)
    inside = in_window(now_pht.time(), start, end)
    day = report_day(now_pht)

    print(f"now={now_pht.isoformat()} report_day={day} proceed={proceed} in_window={inside}")
    print(reason)

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"proceed={'true' if proceed else 'false'}\n")
            fh.write(f"in_window={'true' if inside else 'false'}\n")
            fh.write(f"report_day={day}\n")
            fh.write(f"reason={reason}\n")


if __name__ == "__main__":
    main()
