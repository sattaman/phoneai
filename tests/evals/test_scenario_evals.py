"""Judged scenario evals, one LangSmith experiment per model. Run via `phoneai eval`.

Each case: scripted callee turns against the real `book_gym_session` scenario and tools,
with a fake calendar. Scored by deterministic checks on recorded state (pass/fail) and
LiveKit's LLM judges (task completion, tool use), logged as LangSmith feedback.
"""

import os
from dataclasses import replace
from pathlib import Path

import pytest
from langsmith import testing as t
from livekit.agents import AgentSession
from livekit.agents.evals import JudgeGroup, task_completion_judge, tool_use_judge

from phoneai.adapters.fakes import FixedClock
from phoneai.config import Settings, load_profile, load_scenario
from phoneai.domain import CallState
from phoneai.evals import EvalRow, append_row, check_expectations, load_cases
from phoneai.runtime import bootstrap
from phoneai.tools import ToolDeps
from phoneai.voice.agent import build_agent, metrics_from, transcript_from
from phoneai.voice.session import build_llm
from tests.conftest import TZ, at

bootstrap()

ROOT = Path(__file__).resolve().parents[2]
MODEL = os.getenv("EVAL_MODEL", "google/gemini-2.5-flash-lite")
JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "google/gemini-2.5-flash")
REASONING = os.getenv("EVAL_REASONING_EFFORT") or None
SAMPLES = int(os.getenv("EVAL_SAMPLES", "1"))
RESULTS = Path(os.getenv("EVAL_RESULTS", str(ROOT / "evals" / "results" / "latest.jsonl")))
CASES = load_cases(ROOT / "evals" / "cases.yaml")

pytestmark = pytest.mark.eval


@pytest.mark.langsmith
@pytest.mark.parametrize("sample", range(SAMPLES))
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
async def test_scenario_case(case, sample):
    settings = Settings()
    if not settings.openrouter_api_key:
        pytest.skip("OPENROUTER_API_KEY not set")
    profile = load_profile(settings.profiles_file, "uk_default")
    scenario = load_scenario(settings.scenarios_dir, "book_gym_session", "Tom")
    state = CallState()
    deps = ToolDeps(
        owner="Tom",
        calendar=case.make_calendar(TZ),
        clock=FixedClock(at(3, 10)),
        tz=TZ,
        hours=settings.hours,
        scenario=scenario,
        state=state,
    )
    t.log_inputs({"case": case.id, "turns": list(case.turns), "model": MODEL})
    t.log_reference_outputs(case.expect)

    model_profile = replace(profile, llm_model=MODEL, llm_reasoning_effort=REASONING)
    judge_profile = replace(profile, llm_model=JUDGE_MODEL)
    async with (
        build_llm(model_profile, settings, fallback=False) as llm,
        build_llm(judge_profile, settings, fallback=False) as judge_llm,
        AgentSession(llm=llm) as session,
    ):
        await session.start(build_agent(deps))
        await session.generate_reply(instructions=scenario.opening)  # as on a real call
        opening_text = " ".join(t_.text for t_ in transcript_from(session.history))
        for turn in case.turns:
            await session.run(user_input=turn)
        transcript = transcript_from(session.history)
        agent_text = " ".join(t_.text for t_ in transcript if t_.role == "agent")
        failures = check_expectations(case, state, agent_text, opening_text)
        judged = await JudgeGroup(
            llm=judge_llm, judges=[task_completion_judge(), tool_use_judge()]
        ).evaluate(session.history)
        metrics = metrics_from(session)

    a = state.arrangement
    t.log_outputs(
        {
            "arrangement": None
            if a is None
            else {
                "day": str(a.day),
                "start": f"{a.start:%H:%M}",
                "place": a.place,
                "status": a.status.value,
            },
            "notes": state.notes,
            "transcript": [f"{x.role}: {x.text}" for x in transcript],
        }
    )
    t.log_feedback(key="checks_passed", score=int(not failures))
    for name, j in judged.judgments.items():
        t.log_feedback(key=f"judge_{name}", score=int(j.passed), comment=j.reasoning)
    if "llm_node_ttft_p50" in metrics:
        t.log_feedback(key="llm_ttft_p50", score=metrics["llm_node_ttft_p50"])

    append_row(
        RESULTS,
        EvalRow(
            model=MODEL,
            case=case.id,
            sample=sample,
            checks_passed=not failures,
            failures=failures,
            judges_passed=sum(j.passed for j in judged.judgments.values()),
            judges_total=len(judged.judgments),
            llm_ttft_p50=metrics.get("llm_node_ttft_p50"),
            input_tokens=metrics.get("llm_input_tokens", 0.0),
            output_tokens=metrics.get("llm_output_tokens", 0.0),
            judgments={k: v.verdict for k, v in judged.judgments.items()},
        ),
    )
    assert not failures, failures
