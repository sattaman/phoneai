"""Post-call summary via LangChain + OpenRouter with structured output."""

from __future__ import annotations

from langchain_openrouter import ChatOpenRouter
from pydantic import BaseModel, Field, SecretStr

from phoneai.domain import CallSummary, Scenario, Turn


class _Summary(BaseModel):
    bullets: list[str] = Field(description="3-5 short factual bullet points about the call")
    messages_for_owner: list[str] = Field(
        default_factory=list, description="Messages the callee asked to pass on, word for word"
    )
    goal_reached: bool = Field(description="Whether the call brief's goal was achieved")


class OpenRouterSummariser:
    def __init__(self, model: str, api_key: str) -> None:
        llm = ChatOpenRouter(
            model=model, api_key=SecretStr(api_key), temperature=0, max_tokens=400, max_retries=2
        )
        self._llm = llm.with_structured_output(_Summary)

    async def summarise(
        self, owner: str, scenario: Scenario, transcript: list[Turn], notes: list[str]
    ) -> CallSummary:
        text = "\n".join(f"{t.role}: {t.text}" for t in transcript)
        result = await self._llm.ainvoke(
            [
                (
                    "system",
                    f"Summarise a phone call made by an AI assistant ('agent') on behalf of "
                    f"{owner} to another person ('callee'). Refer to the callee in the third "
                    f"person. Only state facts present in the transcript.\n\n"
                    f"Call brief:\n{scenario.brief}",
                ),
                ("user", f"Transcript:\n{text}\n\nNotes saved during the call:\n{notes}"),
            ],
            config={"run_name": "call_summary", "tags": ["summary"]},
        )
        assert isinstance(result, _Summary)
        return CallSummary(
            bullets=tuple(result.bullets),
            messages_for_owner=tuple(result.messages_for_owner),
            goal_reached=result.goal_reached,
        )
