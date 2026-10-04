"""Core types and pure rules. No I/O, no framework imports."""

from __future__ import annotations

import re
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


_VAGUE_PLACES = {"", "gym", "a gym", "the gym", "tbc", "tbd", "unknown", "somewhere", "anywhere"}


def is_specific_place(place: str) -> bool:
    """Reject placeholders a model might invent when the caller hasn't named a place."""
    return place.strip().lower().rstrip(".") not in _VAGUE_PLACES


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
    opening_line: str = ""  # exact first words (AI disclosure); spoken instantly if set
    keyterms: tuple[str, ...] = ()  # names the speech-to-text should expect, e.g. "PureGym"


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
    failure: str | None = None  # fixed category, e.g. "unknown_contact", "sip_486"


def decide_outcome(answered: bool, failure: str | None, arrangement: Arrangement | None) -> Outcome:
    """The outcome comes from recorded facts (tool state), never from the LLM's own claims."""
    if failure:
        return Outcome.FAILED
    if not answered:
        return Outcome.NO_ANSWER
    if arrangement is None:
        return Outcome.INCOMPLETE
    if arrangement.status is ArrangementStatus.AGREED:
        return Outcome.AGREED
    return Outcome.PROVISIONAL


LATENCY_METRICS = (
    "e2e_latency",
    "llm_node_ttft",
    "tts_node_ttfb",
    "end_of_turn_delay",
    "transcription_delay",
)


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (pct in 0-100). Values must be non-empty."""
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * pct // 100))  # ceil
    return ordered[int(rank) - 1]


def aggregate_turn_metrics(
    turns: list[dict[str, float]], usage: dict[str, float] | None = None
) -> dict[str, float]:
    """Per-call metrics from per-turn metrics: p50/p95 of each latency (seconds, rounded to
    ms) over the turns that report it, plus summed token usage and the turn count."""
    out: dict[str, float] = {"agent_turns": float(sum("e2e_latency" in t for t in turns))}
    for name in LATENCY_METRICS:
        values = [t[name] for t in turns if isinstance(t.get(name), int | float)]
        if values:
            out[f"{name}_p50"] = round(percentile(values, 50), 3)
            out[f"{name}_p95"] = round(percentile(values, 95), 3)
    out.update(usage or {})
    return out


_PHONE_LIKE = re.compile(r"(?<![\w])\+?\d[\d ()-]{6,}\d")


def redact_phone_numbers(text: str) -> str:
    """Replace anything that looks like a phone number (9+ digits) with [number].

    9+ digits keeps dates (2026-10-04) and times intact; UK/US numbers have 10-12 digits.
    """

    def sub(m: re.Match[str]) -> str:
        return "[number]" if sum(c.isdigit() for c in m.group()) >= 9 else m.group()

    return _PHONE_LIKE.sub(sub, text)


def may_record_audio(requested: bool, contact: Contact | None) -> bool:
    """Audio is only recorded for browser sessions or calls to the owner themself."""
    return requested and (contact is None or contact.relationship == "self")


def build_instructions(owner: str, scenario: Scenario, today: date) -> str:
    return f"""You are {owner}'s personal assistant, speaking on a phone call.
You speak British English.
Always be open that you are an AI assistant calling on behalf of {owner}.

Call brief:
{scenario.brief}

Today is {today:%A %d %B %Y}. Times are UK time.
Keep every reply to one or two short spoken sentences. No lists, symbols or emojis.
Never state or guess {owner}'s availability yourself; only repeat what the tools return.
As soon as you have a day, time and place, call record_arrangement straight away
(only use a place they actually named; if they haven't said where, ask)
(it checks the calendar itself) and tell them exactly what it returns.
Use check_availability only when you need to suggest times.
After you ask a question, stop and wait for their answer: don't call tools or say more first.
Confirm a day with its date ("Saturday the 10th?"), and if a name sounds unusual, read it
back so they can correct it.
Use save_note for anything {owner} should know, such as messages, preferences or requests.
When the brief is done or the other person wants to go, say goodbye and end the call."""
