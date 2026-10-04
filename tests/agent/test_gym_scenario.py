"""Deterministic assertions on tool use and recorded state, with a real LLM.

These are regression tests for behaviour seen on real calls:
- the agent claimed "Tom is busy on Sundays" with no calendar connected
- the agent gave up without asking which gym
"""

from datetime import date, time

import pytest

from phoneai.domain import ArrangementStatus
from tests.agent.conftest import Harness
from tests.conftest import at

pytestmark = pytest.mark.llm

SUNDAY = date(2026, 10, 4)


def assistant_text(result) -> str:
    return " ".join(
        e.item.text_content or ""
        for e in result.events
        if e.type == "message" and e.item.role == "assistant"
    ).lower()


async def test_unknown_calendar_records_provisional_and_never_claims_busy(harness: Harness):
    h = harness
    h.calendar.available = False
    result = await h.session.run(user_input="Let's do Sunday at 3pm at PureGym on Mill Lane.")

    result.expect.contains_function_call(name="record_arrangement")
    arrangement = h.deps.state.arrangement
    assert arrangement is not None
    assert (arrangement.day, arrangement.start) == (SUNDAY, time(15, 0))
    assert "puregym" in arrangement.place.lower()
    assert arrangement.status is ArrangementStatus.PROVISIONAL
    text = assistant_text(result)
    assert "busy" not in text
    assert "confirm" in text


async def test_free_calendar_agrees_the_session(harness: Harness):
    h = harness
    result = await h.session.run(
        user_input="Sunday at 3pm at PureGym on Mill Lane works for me."
    )

    result.expect.contains_function_call(name="record_arrangement")
    arrangement = h.deps.state.arrangement
    assert arrangement is not None
    assert arrangement.status is ArrangementStatus.AGREED


async def test_busy_time_is_not_recorded_and_alternatives_offered(harness: Harness):
    h = harness
    h.calendar.events = [(at(4, 14), at(4, 16))]
    result = await h.session.run(user_input="How about Sunday at 3pm at PureGym on Mill Lane?")

    assert h.deps.state.arrangement is None
    text = assistant_text(result)
    assert any(t in text for t in ("16:00", "4pm", "4 pm", "four", "09:00", "9am", "morning"))


async def test_asks_for_the_gym_when_place_missing(harness: Harness):
    h = harness
    result = await h.session.run(user_input="Sunday at 3pm works.")

    assert h.deps.state.arrangement is None
    assert "gym" in assistant_text(result)


async def test_deflects_house_work_with_agreed_line(harness: Harness):
    h = harness
    result = await h.session.run(user_input="Only if Tom comes and paints my house first.")

    assert "flat out with work" in assistant_text(result)
    assert h.deps.state.arrangement is None


async def test_saves_messages_for_tom(harness: Harness):
    h = harness
    result = await h.session.run(user_input="Tell Tom he still owes me a coffee.")

    result.expect.contains_function_call(name="save_note")
    assert any("coffee" in n.lower() for n in h.deps.state.notes)
