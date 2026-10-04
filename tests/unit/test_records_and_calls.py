from datetime import date, time
from pathlib import Path

from phoneai.adapters.fakes import FixedClock, InMemoryCallRecords, StubSummariser
from phoneai.adapters.records_files import FileCallRecords, from_json, to_json, to_markdown
from phoneai.calls import finish_call
from phoneai.domain import (
    Arrangement,
    ArrangementStatus,
    CallRecord,
    CallState,
    CallSummary,
    Outcome,
    Scenario,
    Turn,
)
from tests.conftest import at


def record(**kw) -> CallRecord:
    return CallRecord(
        call_id="abc123",
        contact_id="friend",
        scenario="book_gym_session",
        profile="uk_default",
        started_at=at(3, 10),
        **kw,
    )


def test_json_round_trip():
    r = record(
        ended_at=at(3, 10, 5),
        answered=True,
        outcome=Outcome.PROVISIONAL,
        arrangement=Arrangement(date(2026, 10, 4), time(15), "Gym", ArrangementStatus.PROVISIONAL),
        notes=["paint the house"],
        summary=CallSummary(("b1",), ("m1",), True),
        transcript=[Turn("agent", "hi"), Turn("callee", "hello")],
        metrics={"e2e_latency_p50": 1.2},
        models={"llm": "x"},
    )
    assert from_json(to_json(r)) == r


def test_markdown_has_outcome_and_transcript():
    md = to_markdown(record(outcome=Outcome.AGREED, transcript=[Turn("agent", "hi")]))
    assert "**agreed**" in md
    assert "**agent:** hi" in md


def test_file_records_save_and_list(tmp_path: Path):
    store = FileCallRecords(tmp_path)
    store.save(record())
    assert [r.call_id for r in store.recent()] == ["abc123"]
    assert len(list(tmp_path.glob("*.md"))) == 1


async def test_finish_call_provisional_outcome_from_tool_state():
    state = CallState(
        notes=["hi Tom"],
        arrangement=Arrangement(date(2026, 10, 4), time(15), "Gym", ArrangementStatus.PROVISIONAL),
    )
    store = InMemoryCallRecords()
    r = await finish_call(
        record=record(answered=True),
        state=state,
        transcript=[Turn("agent", "hello")],
        failed=False,
        owner="Tom",
        scenario=Scenario("s", "b", "o", ()),
        summariser=StubSummariser(),
        records=store,
        clock=FixedClock(at(3, 10, 4)),
    )
    assert r.outcome is Outcome.PROVISIONAL
    assert r.ended_at == at(3, 10, 4)
    assert r.notes == ["hi Tom"]
    assert r.summary is not None
    assert store.records == [r]


class BrokenSummariser:
    async def summarise(self, owner, scenario, transcript, notes):
        raise RuntimeError("LLM down")


async def test_finish_call_survives_summary_failure_and_skips_empty_calls():
    store = InMemoryCallRecords()
    r = await finish_call(
        record=record(),
        state=CallState(),
        transcript=[Turn("agent", "hello")],
        failed=True,
        owner="Tom",
        scenario=Scenario("s", "b", "o", ()),
        summariser=BrokenSummariser(),
        records=store,
        clock=FixedClock(at(3, 10, 1)),
    )
    assert r.outcome is Outcome.FAILED
    assert r.summary is None
    assert store.records == [r]
