"""Decide what this workflow run should do about tonight's report.

GitHub's `schedule` trigger starts runs hours late (3–8h has been normal for
this repo), so the workflow doesn't rely on it starting on time. Instead it
schedules several runs through the afternoon. The first run that shows up
early waits on the runner until the target time, then sends. In other words,
the job itself keeps the clock, not GitHub's scheduler.

Actions, written to $GITHUB_OUTPUT as `action`:
  wait  – arrived before the target time but within MAX_EARLY_WAIT_MIN of it:
          sleep `wait_seconds`, then run.
  run   – inside the send window (or forced): run now.
  skip  – too early to wait (a later scheduled run will cover it) or past the
          window (e.g. a run that turned up at 4 AM): do nothing.

Also written:
  report_day   – "tonight's" date (runs before 06:00 PHT count as the previous
                 evening). Used as the once-per-night key.
  retry_until  – Unix time after which no new attempt should start. Runs that
                 find no fresh videos yet retry every 30 min until then.
  in_window    – whether the report time falls in the window. A forced 9 AM
                 test run must not mark tonight as already sent.
  reason       – human-readable explanation.

Env (all optional):
  FORCE               "true": run now, ignoring the window.
  SEND_WINDOW_START   "HH:MM" PHT, target send time. Default 22:00.
  SEND_WINDOW_END     "HH:MM" PHT, latest start time. Default 01:00.
  RETRY_UNTIL         "HH:MM" PHT, last retry start. Default 23:30.
  MAX_EARLY_WAIT_MIN  How long an early run may wait. Default 240.
  GUARD_NOW           ISO timestamp override, for testing.

Stdlib only, so it runs before Python dependencies are installed.
"""

import os
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

PHT = ZoneInfo("Asia/Manila")

# Runs before 06:00 PHT belong to the previous evening's report.
_DAY_ROLLOVER = timedelta(hours=6)


def _parse_hhmm(value: str, default: str) -> time:
    raw = (value or "").strip() or default
    try:
        hh, mm = raw.split(":")
        return time(int(hh), int(mm))
    except ValueError:
        print(f"Invalid time {raw!r}, using {default}", file=sys.stderr)
        hh, mm = default.split(":")
        return time(int(hh), int(mm))


def _at(day: datetime, t: time, base: time) -> datetime:
    """`t` on the report day, pushed to the next calendar day if it is
    earlier than `base` (i.e. the window wraps past midnight)."""
    dt = day.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    if t < base:
        dt += timedelta(days=1)
    return dt


def decide(
    now: datetime,
    force: bool,
    start_t: time,
    end_t: time,
    retry_t: time,
    max_wait: timedelta,
) -> dict:
    report_date = (now - _DAY_ROLLOVER).date()
    day0 = datetime.combine(report_date, time(0), tzinfo=PHT)
    start = _at(day0, start_t, start_t)
    end = _at(day0, end_t, start_t)
    retry_until = min(_at(day0, retry_t, start_t), end)
    window = f"{start_t:%H:%M}–{end_t:%H:%M} PHT"

    in_window = start <= now < end
    result = {
        "report_day": report_date.isoformat(),
        "in_window": in_window,
        "wait_seconds": 0,
        # A run that starts after retry_until still gets exactly one attempt.
        "retry_until": int(max(retry_until, now).timestamp()),
    }

    if force:
        result.update(action="run", reason=f"Forced run (window {window} ignored)")
        result["retry_until"] = int(now.timestamp())  # single attempt
    elif in_window:
        result.update(action="run", reason=f"{now:%H:%M} PHT is inside the send window {window}")
    elif now < start and start - now <= max_wait:
        wait = int((start - now).total_seconds())
        result.update(
            action="wait",
            wait_seconds=wait,
            reason=f"Early by {wait // 60} min; waiting on the runner until {start:%H:%M} PHT",
        )
    elif now < start:
        result.update(
            action="skip",
            reason=(
                f"{now:%H:%M} PHT is more than {int(max_wait.total_seconds() // 60)} min "
                f"before {start:%H:%M}; leaving it to a later scheduled run"
            ),
        )
    else:
        result.update(action="skip", reason=f"{now:%H:%M} PHT is past the send window {window}")
    return result


def main() -> None:
    override = os.environ.get("GUARD_NOW")
    now = (datetime.fromisoformat(override) if override else datetime.now(PHT)).astimezone(PHT)

    result = decide(
        now,
        force=os.environ.get("FORCE", "").strip().lower() == "true",
        start_t=_parse_hhmm(os.environ.get("SEND_WINDOW_START", ""), "22:00"),
        end_t=_parse_hhmm(os.environ.get("SEND_WINDOW_END", ""), "01:00"),
        retry_t=_parse_hhmm(os.environ.get("RETRY_UNTIL", ""), "23:30"),
        max_wait=timedelta(minutes=int(os.environ.get("MAX_EARLY_WAIT_MIN") or 240)),
    )

    print(f"now={now.isoformat()}")
    for key in ("action", "wait_seconds", "report_day", "in_window", "retry_until", "reason"):
        print(f"  {key}={result[key]}")

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            for key, val in result.items():
                if isinstance(val, bool):
                    val = "true" if val else "false"
                fh.write(f"{key}={val}\n")


if __name__ == "__main__":
    main()
