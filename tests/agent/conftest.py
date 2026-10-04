"""Agent behaviour tests: real LLM (OpenRouter), real tools, fake calendar. Opt-in: -m llm."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from livekit.agents import AgentSession

from phoneai.adapters.fakes import FakeCalendar, FixedClock
from phoneai.config import Settings, load_profile
from phoneai.domain import CallState, Scenario, WorkingHours
from phoneai.runtime import bootstrap
from phoneai.tools import ToolDeps
from phoneai.voice.agent import build_agent
from phoneai.voice.session import build_llm
from tests.conftest import TZ, at

bootstrap()

SCENARIO = Scenario(
    name="gym_test",
    opening="Say hello and ask when suits them for a gym session with Tom.",
    brief="""You are calling a friend of Tom's to arrange a gym session with Tom.
Goal: settle the DAY, the TIME and the PLACE (which gym), then call record_arrangement.
- When you need to suggest times, use check_availability. When they propose a day, time
    and place, call record_arrangement straight away; it checks the calendar itself.
- If they ask Tom to do DIY or work on their house, say exactly: "Tom's flat out with work at the
  moment, so can we just stick to the gym?"
- Offer to pass on messages to Tom; save each one with save_note.""",
    tools=("check_availability", "record_arrangement", "save_note", "end_call"),
)


@dataclass
class Harness:
    session: AgentSession
    deps: ToolDeps
    calendar: FakeCalendar
    llm: object


@pytest.fixture
async def harness() -> AsyncIterator[Harness]:
    settings = Settings()
    if not settings.openrouter_api_key:
        pytest.skip("OPENROUTER_API_KEY not set")
    profile = load_profile(settings.profiles_file, "uk_default")
    calendar = FakeCalendar()
    deps = ToolDeps(
        owner="Tom",
        calendar=calendar,
        clock=FixedClock(at(3, 10)),  # Saturday 3 Oct 2026; "Sunday" = 2026-10-04
        tz=TZ,
        hours=WorkingHours(),
        scenario=SCENARIO,
        state=CallState(),
    )
    async with build_llm(profile, settings) as llm, AgentSession(llm=llm) as session:
        await session.start(build_agent(deps))
        yield Harness(session, deps, calendar, llm)
