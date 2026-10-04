from __future__ import annotations

from datetime import date

from phoneai.domain import describe_slots, free_slots
from phoneai.ports import CalendarUnavailable
from phoneai.tools import Tool, ToolDeps

UNKNOWN = (
    "{owner}'s calendar can't be checked right now, so {owner}'s availability is unknown. "
    "Do not say {owner} is busy or free. You may accept a suggested time provisionally "
    "and say {owner} will confirm."
)


def build(deps: ToolDeps) -> Tool:
    async def check_availability(day: str) -> str:
        """Check the owner's calendar for free time on a day.

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
        return describe_slots(free_slots(busy, start, end))

    return check_availability
