"""Builds the LiveKit Agent for a call: instructions from the scenario, tools from the registry."""

from __future__ import annotations

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


def transcript_from(history: ChatContext) -> list[Turn]:
    roles = {"assistant": "agent", "user": "callee"}
    return [
        Turn(roles[item.role], item.text_content)
        for item in history.items
        if item.type == "message" and item.role in roles and item.text_content
    ]


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
