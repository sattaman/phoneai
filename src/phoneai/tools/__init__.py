"""Agent tools. Each tool is a plain async function built from ToolDeps.

Tools are framework-free: the voice layer adapts them to LiveKit function tools.
Adding a capability = add a module here, register it in _registry(), list it in a scenario.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from phoneai.domain import CallState, Scenario, WorkingHours
from phoneai.ports import Calendar, Clock


@dataclass
class ToolDeps:
    owner: str
    calendar: Calendar
    clock: Clock
    tz: ZoneInfo
    hours: WorkingHours
    scenario: Scenario
    state: CallState


Tool = Callable[..., Awaitable[str]]
ToolBuilder = Callable[[ToolDeps], Tool]


def _registry() -> dict[str, ToolBuilder]:
    from phoneai.tools import check_availability, record_arrangement, save_note

    return {
        "check_availability": check_availability.build,
        "record_arrangement": record_arrangement.build,
        "save_note": save_note.build,
    }


# Handled by the voice layer, not by a module here.
BUILTIN_TOOLS = frozenset({"end_call"})


def build_tools(names: tuple[str, ...], deps: ToolDeps) -> dict[str, Tool]:
    registry = _registry()
    unknown = set(names) - registry.keys() - BUILTIN_TOOLS
    if unknown:
        raise ValueError(f"Unknown tools in scenario {deps.scenario.name!r}: {sorted(unknown)}")
    return {name: registry[name](deps) for name in names if name in registry}


def known_tools() -> set[str]:
    return set(_registry()) | BUILTIN_TOOLS
