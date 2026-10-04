"""Use cases around a call's lifecycle: connecting the callee, finishing the call."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace

from phoneai.domain import (
    CallRecord,
    CallState,
    Contact,
    Scenario,
    Turn,
    decide_outcome,
    redact_phone_numbers,
)
from phoneai.ports import CallRecords, Clock, Contacts, DialFailed, Summariser

logger = logging.getLogger(__name__)

MIN_CALL_SECONDS = 20  # don't start a call that would be cut off almost immediately
MAX_DISPATCH_AGE_SECONDS = 60  # never ring someone long after the call was requested


def call_deadline(dispatched_at: float, started_at: float, max_call_seconds: int) -> float | None:
    """Wall-clock deadline for the call, measured from when the worker starts it, so a slow
    network doesn't eat into talk time. None if the request is too old to act on."""
    if started_at - dispatched_at > MAX_DISPATCH_AGE_SECONDS:
        return None
    return started_at + max_call_seconds


async def connect_callee(
    contacts: Contacts,
    contact_id: str,
    dial: Callable[[Contact, int], Awaitable[None]],
    remaining_seconds: float,
) -> str | None:
    """Look up the contact and dial them. Returns a failure category, or None if answered."""
    if remaining_seconds < MIN_CALL_SECONDS:
        return "deadline"
    try:
        contact = contacts.get(contact_id)
    except KeyError:
        return "unknown_contact"
    except Exception as e:  # message/traceback may contain personal data: log the type only
        logger.warning("contacts unavailable: %s", type(e).__name__)
        return "contacts_error"
    try:
        await dial(contact, int(remaining_seconds))
    except DialFailed as e:
        return e.category
    except Exception as e:
        logger.warning("dial setup failed: %s", type(e).__name__)
        return "setup_error"
    return None


async def finish_call(
    *,
    record: CallRecord,
    state: CallState,
    transcript: list[Turn],
    owner: str,
    scenario: Scenario,
    summariser: Summariser,
    records: CallRecords,
    clock: Clock,
) -> CallRecord:
    """Decide the outcome from facts, summarise and persist. Phone numbers spoken during
    the call are redacted before anything is summarised or stored."""
    record.ended_at = clock.now()
    record.transcript = [Turn(t.role, redact_phone_numbers(t.text)) for t in transcript]
    record.notes = [redact_phone_numbers(n) for n in state.notes]
    record.arrangement = (
        replace(state.arrangement, place=redact_phone_numbers(state.arrangement.place))
        if state.arrangement
        else None
    )
    record.outcome = decide_outcome(record.answered, record.failure, record.arrangement)
    if record.transcript:
        try:
            summary = await summariser.summarise(
                owner, scenario, record.transcript, record.notes, call_id=record.call_id
            )
            record.summary = replace(
                summary,
                bullets=tuple(redact_phone_numbers(b) for b in summary.bullets),
                messages_for_owner=tuple(
                    redact_phone_numbers(m) for m in summary.messages_for_owner
                ),
            )
        except Exception as e:
            logger.warning("summary failed for call %s: %s", record.call_id, type(e).__name__)
    records.save(record)
    return record
