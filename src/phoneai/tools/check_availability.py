from __future__ import annotations

from datetime import date

from phoneai.domain import describe_slots, free_slots
from phoneai.ports import CalendarUnavailable
from phoneai.tools import Tool, ToolDeps

UNKNOWN = (
    "{owner}'s calendar can't be checked right now, so {owner}'s availability is unknown. "
    "Do not say {owner} is busy or free. If they propose a time, accept it provisionally: "
    "once you have a day, time and place, call record_arrangement."
)


def build(deps: ToolDeps) -> Tool:
    async def check_availability(day: str) -> str:
        """List the owner's free times on a day. Use it when YOU need to suggest times;
        if they propose a specific time, call record_arrangement instead (it checks itself).

        Args:
            day: The date to check, in YYYY-MM-DD format.
        """
        try:
            target = date.fromisoformat(day)
        except ValueError:
            return "That isn't a valid date; ask which day they mean."
        start, end = deps.hours.window(target, deps.tz)
        try:
            busy = await deps.calendar.busy(start, end)
        except CalendarUnavailable:
            return UNKNOWN.format(owner=deps.owner)
        return describe_slots(free_slots(busy, start, end, deps.scenario.event_minutes))

    return check_availability
