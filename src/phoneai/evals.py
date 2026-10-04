"""Scenario evals: scripted callee turns against a real model, scored by deterministic
checks on recorded tool state plus LLM judges. Run via `phoneai eval`."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from phoneai.adapters.fakes import FakeCalendar
from phoneai.domain import Arrangement, CallState


@dataclass(frozen=True)
class EvalCase:
    id: str
    calendar: str | list[list[str]]
    turns: tuple[str, ...]
    expect: dict[str, Any]

    def make_calendar(self, tz: ZoneInfo) -> FakeCalendar:
        if self.calendar == "unknown":
            return FakeCalendar(available=False)
        if self.calendar == "free":
            return FakeCalendar()
        parse = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=tz)  # noqa: E731
        return FakeCalendar(events=[(parse(s), parse(e)) for s, e in self.calendar])


def load_cases(path: Path) -> list[EvalCase]:
    return [
        EvalCase(c["id"], c["calendar"], tuple(c["turns"]), c["expect"])
        for c in yaml.safe_load(path.read_text())
    ]


def check_expectations(case: EvalCase, state: CallState, agent_text: str) -> list[str]:
    """Deterministic checks on recorded state. Returns failure reasons (empty = pass)."""
    exp, a = case.expect, state.arrangement
    failures: list[str] = []
    if exp.get("status") == "none":
        if a is not None:
            failures.append(f"expected nothing recorded, got {a.status.value}")
    elif a is None:
        failures.append("nothing recorded")
    else:
        failures += _check_arrangement(exp, a)
    if (note := exp.get("note")) and not any(note in n.lower() for n in state.notes):
        failures.append(f"no note containing {note!r}")
    for phrase in exp.get("must_not_say", []):
        if phrase in agent_text.lower():
            failures.append(f"agent said {phrase!r}")
    return failures


def _check_arrangement(exp: dict[str, Any], a: Arrangement) -> list[str]:
    failures = []
    if a.status.value != exp["status"]:
        failures.append(f"status {a.status.value} != {exp['status']}")
    if (start := exp.get("start")) and a.start != time.fromisoformat(start):
        failures.append(f"start {a.start:%H:%M} != {start}")
    if (place := exp.get("place")) and place not in a.place.lower():
        failures.append(f"place {a.place!r} lacks {place!r}")
    return failures


@dataclass
class EvalRow:
    model: str
    case: str
    sample: int
    checks_passed: bool
    failures: list[str]
    judges_passed: int
    judges_total: int
    llm_ttft_p50: float | None
    input_tokens: float
    output_tokens: float
    judgments: dict[str, str] = field(default_factory=dict)


def append_row(path: Path, row: EvalRow) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row.__dict__) + "\n")


def read_rows(path: Path) -> list[EvalRow]:
    return [EvalRow(**json.loads(line)) for line in path.read_text().splitlines() if line]


def render_report(rows: list[EvalRow], prices: dict[str, tuple[float, float]]) -> str:
    """Markdown table per model. prices: model -> (USD per input token, per output token)."""
    lines = [
        "| Model | Samples | Checks pass | Judges pass | LLM TTFT p50 | Tokens in/out | "
        "Est. cost / conversation |",
        "|---|---|---|---|---|---|---|",
    ]
    for model in sorted({r.model for r in rows}):
        mine = [r for r in rows if r.model == model]
        checks = sum(r.checks_passed for r in mine) / len(mine)
        judged = sum(r.judges_total for r in mine)
        judges = sum(r.judges_passed for r in mine) / judged if judged else 0.0
        ttfts = [r.llm_ttft_p50 for r in mine if r.llm_ttft_p50 is not None]
        tin = statistics.mean(r.input_tokens for r in mine)
        tout = statistics.mean(r.output_tokens for r in mine)
        pin, pout = prices.get(model, (0.0, 0.0))
        cost = tin * pin + tout * pout
        ttft = f"{statistics.median(ttfts):.2f}s" if ttfts else "-"
        lines.append(
            f"| `{model}` | {len(mine)} | {checks:.0%} | {judges:.0%} | {ttft} | "
            f"{tin:,.0f} / {tout:,.0f} | ${cost:.4f} |"
        )
    failures = [r for r in rows if not r.checks_passed]
    if failures:
        lines += ["", "**Check failures**", ""]
        lines += [
            f"- `{r.model}` · {r.case} #{r.sample}: {'; '.join(r.failures)}" for r in failures
        ]
    return "\n".join(lines) + "\n"
