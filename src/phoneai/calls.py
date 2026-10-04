"""Use case: finish a call: decide the outcome, summarise, persist."""

from __future__ import annotations

import logging

from phoneai.domain import CallRecord, CallState, Scenario, Turn, decide_outcome
from phoneai.ports import CallRecords, Clock, Summariser

logger = logging.getLogger(__name__)


async def finish_call(
    *,
    record: CallRecord,
    state: CallState,
    transcript: list[Turn],
    failed: bool,
    owner: str,
    scenario: Scenario,
    summariser: Summariser,
    records: CallRecords,
    clock: Clock,
) -> CallRecord:
    record.ended_at = clock.now()
    record.transcript = transcript
    record.notes = list(state.notes)
    record.arrangement = state.arrangement
    record.outcome = decide_outcome(record.answered, failed, state.arrangement)
    if transcript:
        try:
            record.summary = await summariser.summarise(owner, scenario, transcript, state.notes)
        except Exception:
            logger.exception("summary failed for call %s", record.call_id)
    records.save(record)
    return record
