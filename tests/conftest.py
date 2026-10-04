from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from phoneai.adapters.fakes import FakeCalendar, FixedClock
from phoneai.domain import CallState, Scenario, WorkingHours
from phoneai.tools import ToolDeps

TZ = ZoneInfo("Europe/London")


def at(day: int, hour: int, minute: int = 0, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=TZ)


@pytest.fixture
def scenario() -> Scenario:
    return Scenario(
        name="test",
        brief="Arrange a gym session.",
        opening="Say hello.",
        tools=("check_availability", "record_arrangement", "save_note", "end_call"),
        event_minutes=60,
    )


@pytest.fixture
def calendar() -> FakeCalendar:
    return FakeCalendar()


@pytest.fixture
def deps(scenario: Scenario, calendar: FakeCalendar) -> ToolDeps:
    return ToolDeps(
        owner="Tom",
        calendar=calendar,
        clock=FixedClock(at(3, 10)),  # Saturday 3 Oct 2026, 10:00
        tz=TZ,
        hours=WorkingHours(),
        scenario=scenario,
        state=CallState(),
    )
