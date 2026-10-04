"""Read-only calendar from an iCal feed (e.g. Google Calendar's secret iCal address)."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

from phoneai.ports import CalendarUnavailable

logger = logging.getLogger(__name__)


def _as_datetime(value: object, tz: ZoneInfo) -> datetime:
    """iCal date values: datetime (aware or floating) or date (all-day)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=tz)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tz)
    raise ValueError(f"unsupported iCal date value: {type(value).__name__}")


def busy_intervals(
    ics: bytes, start: datetime, end: datetime, tz: ZoneInfo
) -> list[tuple[datetime, datetime]]:
    """Opaque events overlapping [start, end], as tz-aware intervals.

    All-day events (date-valued DTSTART) block whole local days. Event length comes
    from DTEND, else DURATION, else RFC 5545 defaults (one day if all-day, else zero).
    """
    cal = icalendar.Calendar.from_ical(ics)
    busy = []
    for event in recurring_ical_events.of(cal).between(start, end):
        if str(event.get("TRANSP", "OPAQUE")).upper() == "TRANSPARENT":
            continue
        raw_start = event.decoded("DTSTART")
        all_day = isinstance(raw_start, date) and not isinstance(raw_start, datetime)
        ev_start = _as_datetime(raw_start, tz)
        if "DTEND" in event:
            ev_end = _as_datetime(event.decoded("DTEND"), tz)
        elif "DURATION" in event:
            duration = event.decoded("DURATION")
            assert isinstance(duration, timedelta)
            ev_end = ev_start + duration
        else:
            ev_end = ev_start + (timedelta(days=1) if all_day else timedelta())
        busy.append((ev_start.astimezone(tz), ev_end.astimezone(tz)))
    return busy


class IcalCalendar:
    def __init__(self, url: str, tz: ZoneInfo, timeout: float = 10.0) -> None:
        self._url = url
        self._tz = tz
        self._timeout = timeout

    async def busy(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(self._url)
                resp.raise_for_status()
            return busy_intervals(resp.content, start, end, self._tz)
        except Exception as e:
            logger.warning("calendar unavailable: %s", type(e).__name__)
            raise CalendarUnavailable from e


class NoCalendar:
    """Used when no calendar is configured: availability is always unknown."""

    async def busy(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        raise CalendarUnavailable("no calendar configured")
