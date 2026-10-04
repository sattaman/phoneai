"""Ports: the interfaces the app depends on. Adapters implement them."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from phoneai.domain import CallRecord, CallSummary, Contact, Scenario, Turn


class CalendarUnavailable(Exception):
    """The calendar could not be read; availability is unknown."""


class Calendar(Protocol):
    async def busy(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        """Busy intervals overlapping [start, end]. Raises CalendarUnavailable."""
        ...


class Contacts(Protocol):
    def get(self, contact_id: str) -> Contact:
        """Raises KeyError if unknown."""
        ...


class CallRecords(Protocol):
    def save(self, record: CallRecord) -> None: ...

    def recent(self, limit: int = 20) -> list[CallRecord]: ...


class Summariser(Protocol):
    async def summarise(
        self, owner: str, scenario: Scenario, transcript: list[Turn], notes: list[str]
    ) -> CallSummary: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
