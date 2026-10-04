"""Call records as JSON files, plus a human-readable markdown rendering."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from phoneai.domain import (
    Arrangement,
    ArrangementStatus,
    CallRecord,
    CallSummary,
    Outcome,
    Turn,
)


def _default(o: Any) -> Any:
    if isinstance(o, datetime | date | time):
        return o.isoformat()
    raise TypeError(type(o))


def to_json(record: CallRecord) -> str:
    return json.dumps(asdict(record), default=_default, indent=2)


def from_json(text: str) -> CallRecord:
    d = json.loads(text)
    arr = d.get("arrangement")
    summ = d.get("summary")
    return CallRecord(
        call_id=d["call_id"],
        contact_id=d.get("contact_id"),
        scenario=d["scenario"],
        profile=d["profile"],
        started_at=datetime.fromisoformat(d["started_at"]),
        ended_at=datetime.fromisoformat(d["ended_at"]) if d.get("ended_at") else None,
        answered=d.get("answered", False),
        outcome=Outcome(d["outcome"]),
        arrangement=Arrangement(
            day=date.fromisoformat(arr["day"]),
            start=time.fromisoformat(arr["start"]),
            place=arr["place"],
            status=ArrangementStatus(arr["status"]),
        )
        if arr
        else None,
        notes=d.get("notes", []),
        summary=CallSummary(
            bullets=tuple(summ["bullets"]),
            messages_for_owner=tuple(summ.get("messages_for_owner", ())),
            goal_reached=summ.get("goal_reached", False),
        )
        if summ
        else None,
        transcript=[Turn(**t) for t in d.get("transcript", [])],
        metrics=d.get("metrics", {}),
        models=d.get("models", {}),
    )


def to_markdown(r: CallRecord) -> str:
    lines = [
        f"# Call {r.call_id}",
        "",
        f"- Contact: {r.contact_id or 'browser'}",
        f"- Scenario: {r.scenario} · Profile: {r.profile}",
        f"- Started: {r.started_at:%Y-%m-%d %H:%M}",
        f"- Outcome: **{r.outcome.value}**",
    ]
    if r.arrangement:
        a = r.arrangement
        lines.append(
            f"- Arrangement ({a.status.value}): {a.day:%a %d %b} {a.start:%H:%M}, {a.place}"
        )
    if r.models:
        lines.append("- Models: " + ", ".join(f"{k}={v}" for k, v in r.models.items()))
    if r.metrics:
        lines.append("- Metrics: " + ", ".join(f"{k}={v:g}" for k, v in r.metrics.items()))
    if r.summary:
        lines += ["", "## Summary", *[f"- {b}" for b in r.summary.bullets]]
        if r.summary.messages_for_owner:
            lines += ["", "## Messages", *[f"- {m}" for m in r.summary.messages_for_owner]]
    lines += ["", "## Notes", *([f"- {n}" for n in r.notes] or ["- (none)"])]
    lines += ["", "## Transcript", *[f"**{t.role}:** {t.text}  " for t in r.transcript]]
    return "\n".join(lines) + "\n"


class FileCallRecords:
    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def save(self, record: CallRecord) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        stem = f"{record.started_at:%Y-%m-%d_%H%M%S}_{record.call_id}"
        (self._dir / f"{stem}.json").write_text(to_json(record))
        (self._dir / f"{stem}.md").write_text(to_markdown(record))

    def recent(self, limit: int = 20) -> list[CallRecord]:
        files = sorted(self._dir.glob("*.json"), reverse=True)[:limit]
        return [from_json(f.read_text()) for f in files]
