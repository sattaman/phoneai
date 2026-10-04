"""Outbound calling through LiveKit SIP (Twilio Elastic SIP trunk) and agent dispatch."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from google.protobuf.duration_pb2 import Duration
from livekit import api

logger = logging.getLogger(__name__)

AGENT_NAME = "phoneai"


class CallFailed(Exception):
    def __init__(self, reason: str, sip_status: str | None = None) -> None:
        super().__init__(reason)
        self.sip_status = sip_status


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
    phone: str,
    trunk: SipTrunk,
    ringing_timeout_s: int,
    max_call_duration_s: int,
) -> None:
    """Dial and wait until answered. SIP enforces the hard cap on call duration."""
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
                sip_call_to=phone,
                participant_identity=f"callee-{call_id}",  # no phone number in identity
                participant_name="callee",
                hide_phone_number=True,
                ringing_timeout=Duration(seconds=ringing_timeout_s),
                max_call_duration=Duration(seconds=max_call_duration_s),
                wait_until_answered=True,
            )
        )
    except api.TwirpError as e:
        status = (e.metadata or {}).get("sip_status_code")
        logger.warning("call %s failed: %s (SIP %s)", call_id, e.message, status)
        raise CallFailed(e.message, status) from e
