"""Builds the LiveKit Agent for a call: instructions from the scenario, tools from the registry."""

from __future__ import annotations

from livekit.agents import Agent
from livekit.agents.llm import ChatContext

from phoneai.domain import Turn, build_instructions
from phoneai.tools import ToolDeps, build_tools
from phoneai.voice.tool_adapter import to_livekit_tools


def build_agent(deps: ToolDeps) -> Agent:
    tools = build_tools(deps.scenario.tools, deps)
    return Agent(
        instructions=build_instructions(deps.owner, deps.scenario, deps.clock.now().date()),
        tools=to_livekit_tools(tools, deps.scenario.tools),
    )


def transcript_from(history: ChatContext) -> list[Turn]:
    roles = {"assistant": "agent", "user": "callee"}
    return [
        Turn(roles[item.role], item.text_content)
        for item in history.items
        if item.type == "message" and item.role in roles and item.text_content
    ]
