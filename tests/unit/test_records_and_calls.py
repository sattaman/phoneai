from datetime import date, time
from pathlib import Path

from phoneai.adapters.fakes import DictContacts, FixedClock, InMemoryCallRecords, StubSummariser
from phoneai.adapters.records_files import FileCallRecords, from_json, to_json, to_markdown
from phoneai.calls import MIN_CALL_SECONDS, connect_callee, finish_call
from phoneai.domain import (
    Arrangement,
    ArrangementStatus,
    CallRecord,
    CallState,
    CallSummary,
    Contact,
    Outcome,
    Scenario,
    Turn,
)
from phoneai.ports import DialFailed
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
        failure=None,
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
        record=record(failure="sip_486"),
        state=CallState(),
        transcript=[Turn("agent", "hello")],
        owner="Tom",
        scenario=Scenario("s", "b", "o", ()),
        summariser=BrokenSummariser(),
        records=store,
        clock=FixedClock(at(3, 10, 1)),
    )
    assert r.outcome is Outcome.FAILED
    assert r.summary is None
    assert store.records == [r]


async def test_finish_call_redacts_numbers_before_summary_and_storage():
    seen = {}

    class Spy:
        async def summarise(self, owner, scenario, transcript, notes):
            seen["text"] = " ".join(t.text for t in transcript) + " ".join(notes)
            return CallSummary(("ok",))

    store = InMemoryCallRecords()
    r = await finish_call(
        record=record(answered=True),
        state=CallState(notes=["ring her on 07700 900123"]),
        transcript=[Turn("callee", "my number is +44 7700 900123")],
        owner="Tom",
        scenario=Scenario("s", "b", "o", ()),
        summariser=Spy(),
        records=store,
        clock=FixedClock(at(3, 10, 1)),
    )
    assert "900123" not in seen["text"]
    assert r.transcript[0].text == "my number is [number]"
    assert r.notes == ["ring her on [number]"]


FRIEND = Contact("friend", "A Friend", "+447700900001", "friend")


async def test_connect_callee_success_passes_remaining_time():
    calls = []

    async def dial(contact, max_seconds):
        calls.append((contact.id, max_seconds))

    failure = await connect_callee(DictContacts({"friend": FRIEND}), "friend", dial, 250.7)
    assert failure is None
    assert calls == [("friend", 250)]


async def test_connect_callee_failure_categories():
    async def ok(contact, max_seconds):
        pass

    async def sip_busy(contact, max_seconds):
        raise DialFailed("sip_486")

    async def broken(contact, max_seconds):
        raise RuntimeError("boom")

    contacts = DictContacts({"friend": FRIEND})
    assert await connect_callee(contacts, "nobody", ok, 200) == "unknown_contact"
    assert await connect_callee(contacts, "friend", sip_busy, 200) == "sip_486"
    assert await connect_callee(contacts, "friend", broken, 200) == "setup_error"
    assert await connect_callee(contacts, "friend", ok, MIN_CALL_SECONDS - 1) == "deadline"
