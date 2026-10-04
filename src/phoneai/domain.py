"""Core types and pure rules. No I/O, no framework imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo


class Outcome(StrEnum):
    AGREED = "agreed"  # time agreed and confirmed free in the owner's calendar
    PROVISIONAL = "provisional"  # time proposed but calendar unknown; owner must confirm
    INCOMPLETE = "incomplete"  # call happened, goal not reached
    NO_ANSWER = "no_answer"
    FAILED = "failed"


class ArrangementStatus(StrEnum):
    AGREED = "agreed"
    PROVISIONAL = "provisional"


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime

    def covers(self, start: datetime, end: datetime) -> bool:
        return self.start <= start and end <= self.end


@dataclass(frozen=True)
class WorkingHours:
    start: time = time(9, 0)
    end: time = time(18, 0)

    def window(self, day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
        return datetime.combine(day, self.start, tz), datetime.combine(day, self.end, tz)


def free_slots(
    busy: list[tuple[datetime, datetime]],
    window_start: datetime,
    window_end: datetime,
    min_minutes: int = 30,
) -> list[Slot]:
    """Free windows inside [window_start, window_end], given busy intervals.

    Busy intervals are clamped to the window, so events crossing its edges
    (e.g. overnight events) only block the part inside it.
    """
    clamped = sorted(
        (max(s, window_start), min(e, window_end))
        for s, e in busy
        if e > window_start and s < window_end
    )
    slots: list[Slot] = []
    cursor = window_start
    for start, end in clamped:
        if start > cursor:
            slots.append(Slot(cursor, start))
        cursor = max(cursor, end)
    if cursor < window_end:
        slots.append(Slot(cursor, window_end))
    return [s for s in slots if s.end - s.start >= timedelta(minutes=min_minutes)]


def describe_slots(slots: list[Slot]) -> str:
    if not slots:
        return "No free time in working hours that day."
    return "Free: " + ", ".join(f"{s.start:%H:%M} to {s.end:%H:%M}" for s in slots)


@dataclass(frozen=True)
class Contact:
    id: str
    name: str
    phone: str  # E.164; never leaves the local contacts store, logs or traces
    relationship: str = ""


@dataclass(frozen=True)
class Scenario:
    name: str
    brief: str
    opening: str
    tools: tuple[str, ...]
    success_criteria: tuple[str, ...] = ()
    event_minutes: int = 60  # length of the thing being arranged


@dataclass(frozen=True)
class Arrangement:
    day: date
    start: time
    place: str
    status: ArrangementStatus


@dataclass
class CallState:
    """Mutable state the tools build up during one call."""

    notes: list[str] = field(default_factory=list)
    arrangement: Arrangement | None = None


@dataclass(frozen=True)
class Turn:
    role: str  # "agent" | "callee"
    text: str


@dataclass(frozen=True)
class CallSummary:
    bullets: tuple[str, ...]
    messages_for_owner: tuple[str, ...] = ()
    goal_reached: bool = False


@dataclass
class CallRecord:
    call_id: str
    contact_id: str | None
    scenario: str
    profile: str
    started_at: datetime
    ended_at: datetime | None = None
    answered: bool = False
    outcome: Outcome = Outcome.INCOMPLETE
    arrangement: Arrangement | None = None
    notes: list[str] = field(default_factory=list)
    summary: CallSummary | None = None
    transcript: list[Turn] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    models: dict[str, str] = field(default_factory=dict)


def decide_outcome(answered: bool, failed: bool, arrangement: Arrangement | None) -> Outcome:
    """The outcome comes from recorded facts (tool state), never from the LLM's own claims."""
    if failed:
        return Outcome.FAILED
    if not answered:
        return Outcome.NO_ANSWER
    if arrangement is None:
        return Outcome.INCOMPLETE
    if arrangement.status is ArrangementStatus.AGREED:
        return Outcome.AGREED
    return Outcome.PROVISIONAL


def build_instructions(owner: str, scenario: Scenario, today: date) -> str:
    return f"""You are {owner}'s personal assistant, speaking on a phone call.
You speak British English.
Always be open that you are an AI assistant calling on behalf of {owner}.

Call brief:
{scenario.brief}

Today is {today:%A %d %B %Y}. Times are UK time.
Keep every reply to one or two short spoken sentences. No lists, symbols or emojis.
Never state or guess {owner}'s availability yourself;
only repeat what check_availability returns.
When a day, time and place are settled, call record_arrangement
and tell them exactly what it returns.
Use save_note for anything {owner} should know, such as messages, preferences or requests.
When the brief is done or the other person wants to go, say goodbye and end the call."""
