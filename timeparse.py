"""Parse the reset time the user reads off Codex: either "in 2h 14m" or "at 6:45 PM"."""
import re
from datetime import datetime, timedelta

_UNIT = r"(?:hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)(?![a-z])"
_TOKEN = re.compile(rf"(\d+)\s*({_UNIT})")
_FULL_COUNTDOWN = re.compile(rf"(?:\s*\d+\s*{_UNIT})+\s*")

_TIME_ONLY = ["%H:%M", "%H:%M:%S", "%I:%M%p", "%I:%M:%S%p", "%I%p"]
_DATE_TIME = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %I:%M%p", "%Y-%m-%d %I:%M:%S%p"]
_YEARLESS = ["%b %d %H:%M", "%b %d %I:%M%p", "%B %d %H:%M", "%B %d %I:%M%p",
             "%d %b %H:%M", "%d %b %I:%M%p", "%d %B %H:%M", "%d %B %I:%M%p"]


def parse_countdown(text):
    """Seconds from "2h 14m", "2h14m", "45m", "1:05" (h:mm), "1:05:30" or a bare number of minutes."""
    t = re.sub(r"[,]|\band\b", " ", text.strip().lower())
    if not t.strip():
        raise ValueError("enter how long until the reset, e.g. 2h 14m")
    m = re.fullmatch(r"\s*(\d+):(\d{1,2})(?::(\d{1,2}))?\s*", t)
    if m:
        return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3] or 0)
    if re.fullmatch(r"\s*\d+\s*", t):
        return int(t) * 60
    if not _FULL_COUNTDOWN.fullmatch(t):
        raise ValueError(f"can't read {text.strip()!r} as a countdown (try 2h 14m)")
    scale = {"h": 3600, "m": 60, "s": 1}
    return sum(int(n) * scale[unit[0]] for n, unit in _TOKEN.findall(t))


def parse_clock(text, now):
    """Next occurrence of a clock time ("18:45", "6:45 PM"), or an exact date-time ("2026-10-21 03:15", "Oct 21 3:15 AM")."""
    t = re.sub(r"\b(AT|ON|RESETS?)\b", " ", text.upper().replace(",", " "))
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s*(AM|PM)$", r"\1", t)
    if not t:
        raise ValueError("enter the reset time, e.g. 18:45 or 6:45 PM")

    for fmt in _TIME_ONLY:
        try:
            tm = datetime.strptime(t, fmt).time()
        except ValueError:
            continue
        target = datetime.combine(now.date(), tm)
        return target if target > now else target + timedelta(days=1)

    for fmt in _DATE_TIME:
        try:
            target = datetime.strptime(t, fmt)
        except ValueError:
            continue
        if target <= now:
            raise ValueError(f"{target:%Y-%m-%d %H:%M} is already in the past")
        return target

    for fmt in _YEARLESS:
        for year in (now.year, now.year + 1):
            try:
                target = datetime.strptime(f"{t} {year}", f"{fmt} %Y")
            except ValueError:
                break
            if target > now:
                return target
    raise ValueError(f"can't read {text.strip()!r} as a time (try 18:45 or 6:45 PM)")


def resolve_target(mode, text, now, buffer_s=0):
    """Datetime at which to fire: the parsed time plus a safety buffer."""
    if mode == "clock":
        target = parse_clock(text, now)
    else:
        seconds = parse_countdown(text)
        if seconds <= 0:
            raise ValueError("the countdown must be longer than zero")
        target = now + timedelta(seconds=seconds)
    return target + timedelta(seconds=max(0, buffer_s))


def format_remaining(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"
