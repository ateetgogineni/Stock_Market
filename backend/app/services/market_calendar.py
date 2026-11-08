"""NSE session clock.

Only weekday and session-time rules are encoded. The exchange holiday calendar
is NOT loaded yet, so on an NSE holiday the market may be reported as "open" and
the expected last session may be one day too late. Every caller surfaces that
limitation instead of hiding it.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)
# End-of-day bars from the dev provider are usually complete about an hour after the close.
EOD_READY = time(16, 30)
HOLIDAY_NOTE = "NSE holiday calendar not loaded; session status may be wrong on exchange holidays."


def now_ist() -> datetime:
    return datetime.now(tz=IST)


def to_ist(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        raise ValueError("naive datetime")
    return ts.astimezone(IST)


def market_status(at: datetime) -> dict:
    local = to_ist(at)
    if local.weekday() >= 5:
        status = "closed_weekend"
    elif local.time() < SESSION_OPEN:
        status = "pre_open"
    elif local.time() <= SESSION_CLOSE:
        status = "open"
    else:
        status = "closed"
    return {
        "status": status,
        "exchange_time": local.isoformat(),
        "session": f"{SESSION_OPEN:%H:%M}-{SESSION_CLOSE:%H:%M} IST",
        "note": HOLIDAY_NOTE,
    }


def previous_weekday(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def expected_last_session(at: datetime) -> date:
    """The most recent session whose end-of-day bar should exist at `at`."""
    local = to_ist(at)
    d = local.date()
    if d.weekday() < 5 and local.time() >= EOD_READY:
        return d
    return previous_weekday(d) if d.weekday() < 5 else _last_weekday_on_or_before(d)


def _last_weekday_on_or_before(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def sessions_missing(last_bar: date, expected: date) -> int:
    """Weekdays after `last_bar` up to and including `expected`."""
    count = 0
    d = last_bar + timedelta(days=1)
    while d <= expected:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


def add_sessions(start: date, sessions: int) -> date:
    d = start
    added = 0
    while added < sessions:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d
