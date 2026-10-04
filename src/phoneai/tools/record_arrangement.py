from __future__ import annotations

from datetime import date, datetime, time, timedelta

from phoneai.domain import Arrangement, ArrangementStatus, describe_slots, free_slots
from phoneai.ports import CalendarUnavailable
from phoneai.tools import Tool, ToolDeps


def build(deps: ToolDeps) -> Tool:
    async def record_arrangement(day: str, start_time: str, place: str) -> str:
        """Record the day, time and place agreed on the call.

        The tool decides whether it is confirmed (owner is free) or provisional
        (calendar unknown). Tell the caller exactly what this returns.

        Args:
            day: The date, in YYYY-MM-DD format.
            start_time: The start time, 24-hour HH:MM.
            place: Where it will happen, e.g. the gym's name or area.
        """
        try:
            target = date.fromisoformat(day)
            at = time.fromisoformat(start_time)
        except ValueError:
            return "Day or time not understood; confirm the exact date and time with them."
        if not place.strip():
            return "No place given; ask where they'd like to meet before recording."

        start = datetime.combine(target, at, deps.tz)
        end = start + timedelta(minutes=deps.scenario.event_minutes)
        if start <= deps.clock.now():
            return "That time has already passed; ask for a future time."

        try:
            busy = await deps.calendar.busy(start, end)
        except CalendarUnavailable:
            status = ArrangementStatus.PROVISIONAL
        else:
            if free_slots(busy, start, end, min_minutes=deps.scenario.event_minutes):
                status = ArrangementStatus.AGREED
            else:
                window_start, window_end = deps.hours.window(target, deps.tz)
                other = free_slots(
                    await deps.calendar.busy(window_start, window_end), window_start, window_end
                )
                return (
                    f"{deps.owner} is busy then, so nothing was recorded. "
                    f"{describe_slots(other)} Suggest one of those instead."
                )

        deps.state.arrangement = Arrangement(target, at, place.strip(), status)
        when = f"{start:%A %d %B} at {start:%H:%M}, {place.strip()}"
        if status is ArrangementStatus.AGREED:
            return f"{deps.owner} is free then, so it's agreed: {when}. Read this back to them."
        return (
            f"Recorded provisionally: {when}. Tell them {deps.owner} will confirm, "
            f"because {deps.owner}'s calendar couldn't be checked."
        )

    return record_arrangement
