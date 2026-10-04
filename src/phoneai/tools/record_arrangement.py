from __future__ import annotations

from datetime import date, datetime, time, timedelta

from phoneai.domain import (
    Arrangement,
    ArrangementStatus,
    describe_slots,
    free_slots,
    is_specific_place,
)
from phoneai.ports import CalendarUnavailable
from phoneai.tools import Tool, ToolDeps


def build(deps: ToolDeps) -> Tool:
    def describe(a: Arrangement) -> str:
        return f"{a.day:%A %d %B} at {a.start:%H:%M}, {a.place}"

    async def alternatives(target: date) -> str:
        window_start, window_end = deps.hours.window(target, deps.tz)
        try:
            busy = await deps.calendar.busy(window_start, window_end)
        except CalendarUnavailable:
            return "Ask them for another time."
        slots = free_slots(busy, window_start, window_end, deps.scenario.event_minutes)
        return f"{describe_slots(slots)} Suggest one of those instead."

    def keep_earlier() -> str:
        earlier = deps.state.arrangement
        return f" The earlier arrangement ({describe(earlier)}) still stands." if earlier else ""

    async def record_arrangement(day: str, start_time: str, place: str) -> str:
        """Record the day, time and place once they are settled. It checks the owner's
        calendar itself and decides whether it is agreed (owner free) or provisional
        (calendar unknown). A new successful call replaces any earlier arrangement.
        Tell the caller exactly what this returns.

        Args:
            day: The date, in YYYY-MM-DD format.
            start_time: The start time, 24-hour HH:MM.
            place: Where it will happen, as the caller named it (e.g. "PureGym Leeds").
        """
        try:
            target = date.fromisoformat(day)
            at = time.fromisoformat(start_time)
        except ValueError:
            return "Day or time not understood; confirm the exact date and time with them."
        if not is_specific_place(place):
            return "No specific place given; ask which gym or place before recording."

        start = datetime.combine(target, at, deps.tz)
        end = start + timedelta(minutes=deps.scenario.event_minutes)
        if start <= deps.clock.now():
            return "That time has already passed; ask for a future time."
        window_start, window_end = deps.hours.window(target, deps.tz)
        if start < window_start or end > window_end:
            return (
                f"That's outside the hours {deps.owner} is available "
                f"({window_start:%H:%M} to {window_end:%H:%M}), so nothing was recorded."
                f"{keep_earlier()} Ask for a time within those hours."
            )

        try:
            busy = await deps.calendar.busy(start, end)
        except CalendarUnavailable:
            status = ArrangementStatus.PROVISIONAL
        else:
            if not free_slots(busy, start, end, min_minutes=deps.scenario.event_minutes):
                return (
                    f"{deps.owner} is busy then, so nothing was recorded.{keep_earlier()} "
                    f"{await alternatives(target)}"
                )
            status = ArrangementStatus.AGREED

        arrangement = Arrangement(target, at, place.strip(), status)
        deps.state.arrangement = arrangement
        if status is ArrangementStatus.AGREED:
            return (
                f"{deps.owner} is free then, so it's agreed: {describe(arrangement)}. "
                "Read this back to them."
            )
        return (
            f"Recorded provisionally: {describe(arrangement)}. Tell them {deps.owner} will "
            f"confirm, because {deps.owner}'s calendar couldn't be checked."
        )

    return record_arrangement
