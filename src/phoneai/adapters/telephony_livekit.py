"""Outbound calling through LiveKit SIP (Twilio Elastic SIP trunk) and agent dispatch."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from google.protobuf.duration_pb2 import Duration
from livekit import api

from phoneai.domain import Contact
from phoneai.ports import DialFailed

logger = logging.getLogger(__name__)

AGENT_NAME = "phoneai"


@dataclass(frozen=True)
class SipTrunk:
    domain: str
    username: str
    password: str
    caller_id: str


@dataclass(frozen=True)
class CallRequest:
    """What the dispatcher sends to the agent. Deliberately contains no phone number."""

    call_id: str
    contact_id: str | None
    scenario: str
    profile: str
    dispatched_at: float = field(default_factory=time.time)  # deadline is measured from here

    def to_metadata(self) -> str:
        return json.dumps(self.__dict__)

    @classmethod
    def from_metadata(cls, raw: str | None, default_scenario: str, default_profile: str):
        d = json.loads(raw) if raw else {}
        return cls(
            call_id=d.get("call_id") or "",
            contact_id=d.get("contact_id"),
            scenario=d.get("scenario") or default_scenario,
            profile=d.get("profile") or default_profile,
            dispatched_at=float(d.get("dispatched_at") or time.time()),
        )


async def dispatch_call(request: CallRequest) -> None:
    """Ask a running agent worker to place the call (used by the CLI)."""
    async with api.LiveKitAPI() as lk:
        await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=f"call-{request.call_id}",
                metadata=request.to_metadata(),
            )
        )


async def dial(
    lkapi: api.LiveKitAPI,
    *,
    room: str,
    call_id: str,
    contact: Contact,
    trunk: SipTrunk,
    ringing_timeout_s: int,
    max_call_duration_s: int,
) -> None:
    """Dial and wait until answered. SIP enforces the hard cap on call duration.

    Raises DialFailed with a fixed category; the SIP error text is not logged because it
    can contain the dialled number.
    """
    try:
        await lkapi.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=room,
                trunk=api.SIPOutboundConfig(
                    hostname=trunk.domain,
                    auth_username=trunk.username,
                    auth_password=trunk.password,
                ),
                sip_number=trunk.caller_id,
                sip_call_to=contact.phone,
                participant_identity=f"callee-{call_id}",  # no phone number in identity
                participant_name="callee",
                hide_phone_number=True,
                ringing_timeout=Duration(seconds=min(ringing_timeout_s, max_call_duration_s)),
                max_call_duration=Duration(seconds=max_call_duration_s),
                wait_until_answered=True,
            )
        )
    except api.TwirpError as e:
        status = (e.metadata or {}).get("sip_status_code") or e.code
        logger.warning("call %s failed: sip_%s", call_id, status)
        raise DialFailed(f"sip_{status}") from None
