"""In-memory adapters for tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from phoneai.domain import CallRecord, CallSummary, Contact, Scenario, Turn
from phoneai.ports import CalendarUnavailable


@dataclass
class FakeCalendar:
    events: list[tuple[datetime, datetime]] = field(default_factory=list)
    available: bool = True
    queries: list[tuple[datetime, datetime]] = field(default_factory=list)

    async def busy(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        self.queries.append((start, end))
        if not self.available:
            raise CalendarUnavailable("fake outage")
        return [(s, e) for s, e in self.events if e > start and s < end]


@dataclass
class FixedClock:
    at: datetime

    def now(self) -> datetime:
        return self.at


@dataclass
class DictContacts:
    contacts: dict[str, Contact] = field(default_factory=dict)

    def get(self, contact_id: str) -> Contact:
        return self.contacts[contact_id]


@dataclass
class InMemoryCallRecords:
    records: list[CallRecord] = field(default_factory=list)

    def save(self, record: CallRecord) -> None:
        self.records.append(record)

    def recent(self, limit: int = 20) -> list[CallRecord]:
        return self.records[-limit:][::-1]


@dataclass
class StubSummariser:
    summary: CallSummary = field(default_factory=lambda: CallSummary(bullets=("stub",)))

    async def summarise(
        self, owner: str, scenario: Scenario, transcript: list[Turn], notes: list[str]
    ) -> CallSummary:
        return self.summary
