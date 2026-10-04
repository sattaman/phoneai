"""Builds the LiveKit Agent for a call: instructions from the scenario, tools from the registry."""

from __future__ import annotations

import re

from livekit.agents import Agent, AgentSession
from livekit.agents.llm import ChatContext

from phoneai.domain import Turn, aggregate_turn_metrics, build_instructions
from phoneai.tools import ToolDeps, build_tools
from phoneai.voice.tool_adapter import to_livekit_tools


def build_agent(deps: ToolDeps, voice_style: str = "") -> Agent:
    tools = build_tools(deps.scenario.tools, deps)
    instructions = build_instructions(deps.owner, deps.scenario, deps.clock.now().date())
    if voice_style:
        instructions += f"\n\nVoice and delivery: {voice_style}"
    return Agent(
        instructions=instructions,
        tools=to_livekit_tools(tools, deps.scenario.tools),
    )


_MARKUP = re.compile(r"<[^<>]*/?>")  # expressive-mode delivery tags, e.g. <expr .../>


def clean_text(text: str) -> str:
    return " ".join(_MARKUP.sub(" ", text).split())


def transcript_from(history: ChatContext) -> list[Turn]:
    roles = {"assistant": "agent", "user": "callee"}
    turns = (
        (roles[item.role], clean_text(item.text_content or ""))
        for item in history.items
        if item.type == "message" and item.role in roles
    )
    return [Turn(role, text) for role, text in turns if text]


def metrics_from(session: AgentSession) -> dict[str, float]:
    """Per-call latency percentiles and LLM token usage from a finished session."""
    turns = [
        {k: float(v) for k, v in (item.metrics or {}).items() if isinstance(v, int | float)}
        for item in session.history.items
        if item.type == "message"
    ]
    usage: dict[str, float] = {}
    for u in session.usage.model_usage:
        if getattr(u, "type", "") == "llm_usage":
            for key in ("input_tokens", "output_tokens"):
                usage[f"llm_{key}"] = usage.get(f"llm_{key}", 0.0) + float(getattr(u, key, 0) or 0)
    return aggregate_turn_metrics(turns, usage)
