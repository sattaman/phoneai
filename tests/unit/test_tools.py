from datetime import date, time

import pytest

from phoneai.adapters.fakes import FakeCalendar
from phoneai.domain import ArrangementStatus
from phoneai.tools import ToolDeps, build_tools, known_tools
from tests.conftest import at


def tool(deps: ToolDeps, name: str):
    return build_tools(deps.scenario.tools, deps)[name]


async def test_check_availability_lists_free_slots(deps: ToolDeps, calendar: FakeCalendar):
    calendar.events = [(at(5, 10), at(5, 12))]
    result = await tool(deps, "check_availability")("2026-10-05")
    assert result == "Free: 09:00 to 10:00, 12:00 to 18:00"
    assert calendar.queries == [(at(5, 9), at(5, 18))]


async def test_check_availability_when_calendar_unknown_never_claims_busy_or_free(
    deps: ToolDeps, calendar: FakeCalendar
):
    calendar.available = False
    result = await tool(deps, "check_availability")("2026-10-05")
    assert "availability is unknown" in result
    assert "Do not say Tom is busy or free" in result


async def test_check_availability_rejects_bad_dates(deps: ToolDeps):
    assert "isn't a valid date" in await tool(deps, "check_availability")("next sunday")


async def test_record_arrangement_agreed_when_free(deps: ToolDeps):
    result = await tool(deps, "record_arrangement")("2026-10-05", "14:00", "PureGym Leeds")
    assert "agreed" in result
    a = deps.state.arrangement
    assert a is not None
    assert (a.day, a.start, a.place, a.status) == (
        date(2026, 10, 5),
        time(14, 0),
        "PureGym Leeds",
        ArrangementStatus.AGREED,
    )


async def test_record_arrangement_provisional_when_calendar_unknown(
    deps: ToolDeps, calendar: FakeCalendar
):
    """Regression: the agent once told a caller 'Tom is busy on Sundays' with no calendar."""
    calendar.available = False
    result = await tool(deps, "record_arrangement")("2026-10-04", "15:00", "the usual gym")
    assert "provisionally" in result
    assert "Tom will confirm" in result
    assert deps.state.arrangement is not None
    assert deps.state.arrangement.status is ArrangementStatus.PROVISIONAL


async def test_record_arrangement_refuses_busy_time_and_offers_alternatives(
    deps: ToolDeps, calendar: FakeCalendar
):
    calendar.events = [(at(5, 13), at(5, 15))]
    result = await tool(deps, "record_arrangement")("2026-10-05", "14:00", "PureGym")
    assert "busy then" in result
    assert "Free: 09:00 to 13:00, 15:00 to 18:00" in result
    assert deps.state.arrangement is None


async def test_record_arrangement_partial_overlap_is_busy(deps: ToolDeps, calendar: FakeCalendar):
    calendar.events = [(at(5, 14, 30), at(5, 16))]
    result = await tool(deps, "record_arrangement")("2026-10-05", "14:00", "PureGym")
    assert "busy then" in result


@pytest.mark.parametrize(
    ("day", "start", "place", "expected"),
    [
        ("2026-10-05", "2pm", "Gym", "not understood"),
        ("tomorrow", "14:00", "Gym", "not understood"),
        ("2026-10-05", "14:00", "  ", "No place given"),
        ("2026-10-02", "14:00", "Gym", "already passed"),
    ],
)
async def test_record_arrangement_validates_input(deps: ToolDeps, day, start, place, expected):
    assert expected in await tool(deps, "record_arrangement")(day, start, place)
    assert deps.state.arrangement is None


async def test_save_note_appends_trimmed_notes(deps: ToolDeps):
    save = tool(deps, "save_note")
    await save("  Tell Tom to paint my house  ")
    await save("")
    assert deps.state.notes == ["Tell Tom to paint my house"]


def test_unknown_tool_in_scenario_is_rejected(deps: ToolDeps):
    with pytest.raises(ValueError, match="make_coffee"):
        build_tools(("save_note", "make_coffee"), deps)


def test_builtin_end_call_is_not_built_as_app_tool(deps: ToolDeps):
    assert "end_call" not in build_tools(deps.scenario.tools, deps)
    assert "end_call" in known_tools()
