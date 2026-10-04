from datetime import date

from phoneai.domain import (
    Arrangement,
    ArrangementStatus,
    Contact,
    Outcome,
    Scenario,
    Slot,
    build_instructions,
    decide_outcome,
    describe_slots,
    free_slots,
    may_record_audio,
    redact_phone_numbers,
)
from tests.conftest import at


def window(day: int = 5):
    return at(day, 9), at(day, 18)


def test_free_day_is_one_slot():
    assert free_slots([], *window()) == [Slot(at(5, 9), at(5, 18))]


def test_busy_blocks_split_the_day():
    busy = [(at(5, 10), at(5, 11)), (at(5, 13), at(5, 14, 30))]
    assert free_slots(busy, *window()) == [
        Slot(at(5, 9), at(5, 10)),
        Slot(at(5, 11), at(5, 13)),
        Slot(at(5, 14, 30), at(5, 18)),
    ]


def test_overlapping_and_unsorted_busy_intervals_merge():
    busy = [(at(5, 12), at(5, 14)), (at(5, 10), at(5, 13))]
    assert free_slots(busy, *window()) == [Slot(at(5, 9), at(5, 10)), Slot(at(5, 14), at(5, 18))]


def test_overnight_event_only_blocks_inside_window():
    busy = [(at(4, 22), at(5, 10))]  # crosses midnight and window start
    assert free_slots(busy, *window()) == [Slot(at(5, 10), at(5, 18))]


def test_event_running_past_window_end_is_clamped():
    busy = [(at(5, 17), at(5, 23))]
    assert free_slots(busy, *window()) == [Slot(at(5, 9), at(5, 17))]


def test_event_outside_window_is_ignored():
    busy = [(at(5, 6), at(5, 8)), (at(5, 19), at(5, 20))]
    assert free_slots(busy, *window()) == [Slot(at(5, 9), at(5, 18))]


def test_short_gaps_are_dropped():
    busy = [(at(5, 9), at(5, 12)), (at(5, 12, 20), at(5, 18))]
    assert free_slots(busy, *window()) == []


def test_describe_slots():
    assert describe_slots([]) == "No free time in working hours that day."
    assert describe_slots([Slot(at(5, 9), at(5, 10))]) == "Free: 09:00 to 10:00"


def arrangement(status: ArrangementStatus) -> Arrangement:
    return Arrangement(date(2026, 10, 5), at(5, 14).time(), "PureGym", status)


def test_outcome_is_decided_from_recorded_facts():
    assert decide_outcome(True, "sip_486", None) is Outcome.FAILED
    assert decide_outcome(False, None, None) is Outcome.NO_ANSWER
    assert decide_outcome(True, None, None) is Outcome.INCOMPLETE
    assert decide_outcome(True, None, arrangement(ArrangementStatus.AGREED)) is Outcome.AGREED
    assert (
        decide_outcome(True, None, arrangement(ArrangementStatus.PROVISIONAL))
        is Outcome.PROVISIONAL
    )


def test_instructions_disclose_ai_and_forbid_guessing_availability():
    text = build_instructions("Tom", Scenario("s", "BRIEF", "hi", ()), date(2026, 10, 3))
    assert "AI assistant calling on behalf of Tom" in text
    assert "Never state or guess Tom's availability yourself" in text
    assert "call record_arrangement straight away" in text
    assert "BRIEF" in text
    assert "Saturday 03 October 2026" in text


def test_redact_phone_numbers():
    assert redact_phone_numbers("call me on 07700 900123 or +44 (0)7700-900124") == (
        "call me on [number] or [number]"
    )
    assert redact_phone_numbers("Sunday at 3pm, 2026-10-04, room 12") == (
        "Sunday at 3pm, 2026-10-04, room 12"
    )


def test_audio_only_recorded_for_owner_or_browser():
    me = Contact("me", "Tom", "+447700900000", "self")
    friend = Contact("friend", "A Friend", "+447700900001", "friend")
    assert may_record_audio(True, None)
    assert may_record_audio(True, me)
    assert not may_record_audio(True, friend)
    assert not may_record_audio(False, me)
