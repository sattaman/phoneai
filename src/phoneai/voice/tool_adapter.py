"""Adapts framework-free tools to LiveKit function tools."""

from __future__ import annotations

from livekit.agents import function_tool
from livekit.agents.beta.tools import EndCallTool

from phoneai.tools import Tool


def to_livekit_tools(tools: dict[str, Tool], allowed: tuple[str, ...]) -> list:
    """Wrap each tool; add LiveKit's EndCallTool if the scenario allows 'end_call'."""
    wrapped: list = [function_tool(fn, name=name) for name, fn in tools.items()]
    if "end_call" in allowed:
        wrapped += EndCallTool(
            end_instructions="Say a brief, warm goodbye.",
            delete_room=True,
        ).tools
    return wrapped
