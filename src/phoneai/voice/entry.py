"""Composition root for the voice agent worker (LiveKit AgentServer)."""

from phoneai.runtime import bootstrap

bootstrap()

import asyncio  # noqa: E402
import contextlib  # noqa: E402
import logging  # noqa: E402
import time  # noqa: E402
from datetime import datetime  # noqa: E402

from livekit import agents  # noqa: E402
from livekit.agents import AgentServer, AgentSession, room_io  # noqa: E402
from livekit.plugins import ai_coustics  # noqa: E402

from phoneai.adapters.calendar_ical import IcalCalendar, NoCalendar  # noqa: E402
from phoneai.adapters.contacts_yaml import YamlContacts  # noqa: E402
from phoneai.adapters.records_files import FileCallRecords  # noqa: E402
from phoneai.adapters.summariser_openrouter import OpenRouterSummariser  # noqa: E402
from phoneai.adapters.telephony_livekit import (  # noqa: E402
    AGENT_NAME,
    CallRequest,
    SipTrunk,
    dial,
)
from phoneai.calls import call_deadline, connect_callee, finish_call  # noqa: E402
from phoneai.config import Settings, load_profile, load_scenario  # noqa: E402
from phoneai.domain import (  # noqa: E402
    CallRecord,
    CallState,
    Contact,
    Scenario,
    may_record_audio,
)
from phoneai.observability import setup_tracing, start_call_trace  # noqa: E402
from phoneai.tools import ToolDeps  # noqa: E402
from phoneai.voice.agent import build_agent, metrics_from, transcript_from  # noqa: E402
from phoneai.voice.session import build_session  # noqa: E402

logger = logging.getLogger("phoneai")

import os  # noqa: E402

# Used when no dispatch metadata is present (browser / console sessions).
DEFAULT_SCENARIO = os.getenv("PHONEAI_SCENARIO", "book_gym_session")
DEFAULT_PROFILE = os.getenv("PHONEAI_PROFILE", "uk_default")
WRAP_UP_SECONDS = 15  # graceful goodbye before SIP's hard max_call_duration cap


class SystemClock:
    def __init__(self, settings: Settings) -> None:
        self._tz = settings.tz

    def now(self) -> datetime:
        return datetime.now(self._tz)


setup_tracing()  # before AgentServer, per the LangSmith LiveKit integration docs
server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: agents.JobContext) -> None:
    settings = Settings()
    req = CallRequest.from_metadata(ctx.job.metadata, DEFAULT_SCENARIO, DEFAULT_PROFILE)
    deadline = call_deadline(req.dispatched_at, settings.max_call_seconds)
    clock = SystemClock(settings)
    call_id = req.call_id or ctx.job.id
    record = CallRecord(
        call_id=call_id,
        contact_id=req.contact_id,
        scenario=req.scenario,
        profile=req.profile,
        started_at=clock.now(),
    )
    state = CallState()
    session: AgentSession | None = None
    scenario: Scenario | None = None

    async def on_shutdown() -> None:
        if session:
            # Shutdown callbacks run concurrently with the session closing; close it
            # ourselves first so the final turns and usage are included.
            with contextlib.suppress(Exception):
                await session.aclose()
            record.metrics = metrics_from(session)
        await finish_call(
            record=record,
            state=state,
            transcript=transcript_from(session.history) if session else [],
            owner=settings.owner_name,
            scenario=scenario or Scenario(req.scenario, "", "", ()),
            summariser=OpenRouterSummariser(settings.summary_model, settings.openrouter_api_key),
            records=FileCallRecords(settings.calls_dir),
            clock=clock,
        )
        logger.info("call %s finished: %s", call_id, record.outcome.value)

    ctx.add_shutdown_callback(on_shutdown)

    # Watchdog runs from the start, so slow setup, ringing or speech can't overrun the deadline.
    async def watchdog() -> None:
        await asyncio.sleep(max(0.0, deadline - time.time() - WRAP_UP_SECONDS))
        if not record.answered:
            record.failure = record.failure or "deadline"
        elif session:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    session.say(
                        "Sorry, I need to wrap up now. Goodbye.", allow_interruptions=False
                    ),
                    timeout=WRAP_UP_SECONDS,
                )
        ctx.shutdown(reason="max call duration")

    timer = asyncio.create_task(watchdog())

    async def cancel_watchdog() -> None:
        timer.cancel()

    ctx.add_shutdown_callback(cancel_watchdog)

    try:
        profile = load_profile(settings.profiles_file, req.profile)
        scenario = load_scenario(settings.scenarios_dir, req.scenario, settings.owner_name)
    except Exception:
        logger.exception("call %s: bad profile or scenario", call_id)
        record.failure = "config_error"
        ctx.shutdown(reason="config error")
        return
    record.models = profile.models()
    start_call_trace(
        call_id,
        {
            "scenario": scenario.name,
            "profile": profile.name,
            "contact_id": req.contact_id or "browser",
            **{f"model_{k}": v for k, v in record.models.items()},
        },
    )

    contacts = YamlContacts(settings.contacts_file)
    contact = None
    if req.contact_id:
        with contextlib.suppress(Exception):
            contact = contacts.get(req.contact_id)
    deps = ToolDeps(
        owner=settings.owner_name,
        calendar=(
            IcalCalendar(settings.google_calendar_ical_url, settings.tz)
            if settings.google_calendar_ical_url
            else NoCalendar()
        ),
        clock=clock,
        tz=settings.tz,
        hours=settings.hours,
        scenario=scenario,
        state=state,
    )
    session = build_session(profile, settings)

    is_phone = req.contact_id is not None
    audio_input = room_io.AudioInputOptions()
    if not is_phone:  # noise filter helps browser mics, hurts narrowband phone audio
        audio_input = room_io.AudioInputOptions(
            noise_cancellation=ai_coustics.audio_enhancement(
                model=ai_coustics.EnhancerModel.QUAIL_VF_S
            ),
        )
    try:
        await session.start(
            room=ctx.room,
            agent=build_agent(deps),
            room_options=room_io.RoomOptions(audio_input=audio_input),
            record=may_record_audio(profile.record_audio, contact),
        )
    except Exception as e:
        logger.warning("call %s: session start failed: %s", call_id, type(e).__name__)
        record.failure = "session_error"
        ctx.shutdown(reason="session error")
        return

    if req.contact_id is not None:
        trunk = SipTrunk(
            settings.sip_domain, settings.sip_username, settings.sip_password, settings.caller_id
        )

        async def dial_contact(callee: Contact, max_seconds: int) -> None:
            await dial(
                ctx.api,
                room=ctx.room.name,
                call_id=call_id,
                contact=callee,
                trunk=trunk,
                ringing_timeout_s=settings.ringing_timeout_seconds,
                max_call_duration_s=max_seconds,
            )

        failure = await connect_callee(
            contacts, req.contact_id, dial_contact, deadline - time.time()
        )
        if timer.done():  # the deadline passed while dialling; watchdog already shut down
            return
        if failure:
            record.failure = failure
            ctx.shutdown(reason=failure)
            return
    record.answered = True

    await session.generate_reply(instructions=scenario.opening)


def main() -> None:
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
