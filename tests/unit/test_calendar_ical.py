from datetime import date
from zoneinfo import ZoneInfo

import pytest

from phoneai.adapters.calendar_ical import NoCalendar, busy_intervals
from phoneai.ports import CalendarUnavailable
from tests.conftest import at

TZ = ZoneInfo("Europe/London")

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:test
BEGIN:VEVENT
UID:utc
DTSTART:20261005T090000Z
DTEND:20261005T100000Z
SUMMARY:standup (UTC, 10:00 BST)
END:VEVENT
BEGIN:VEVENT
UID:weekly
DTSTART;TZID=Europe/London:20260928T130000
DTEND;TZID=Europe/London:20260928T143000
RRULE:FREQ=WEEKLY
SUMMARY:lunch
END:VEVENT
BEGIN:VEVENT
UID:free
DTSTART;TZID=Europe/London:20261005T160000
DTEND;TZID=Europe/London:20261005T170000
TRANSP:TRANSPARENT
SUMMARY:shown as free
END:VEVENT
BEGIN:VEVENT
UID:allday
DTSTART;VALUE=DATE:20261007
DTEND;VALUE=DATE:20261008
SUMMARY:holiday
END:VEVENT
END:VCALENDAR
"""


def test_timed_recurring_and_transparent_events():
    busy = sorted(busy_intervals(ICS, at(5, 0), at(6, 0), TZ))
    assert busy == [(at(5, 10), at(5, 11)), (at(5, 13), at(5, 14, 30))]


def test_all_day_event_blocks_the_local_day():
    busy = busy_intervals(ICS, at(7, 9), at(7, 18), TZ)
    assert (at(7, 0), at(8, 0)) in busy
    assert all(s.tzinfo is not None for s, _ in busy)
    assert date(2026, 10, 7) == busy[0][0].date()


async def test_no_calendar_is_always_unavailable():
    with pytest.raises(CalendarUnavailable):
        await NoCalendar().busy(at(5, 9), at(5, 18))
