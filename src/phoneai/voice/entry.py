"""Composition root for the voice agent worker (LiveKit AgentServer)."""

from phoneai.runtime import bootstrap

bootstrap()

import asyncio  # noqa: E402
import logging  # noqa: E402
from datetime import datetime  # noqa: E402

from livekit import agents  # noqa: E402
from livekit.agents import AgentServer, room_io  # noqa: E402
from livekit.plugins import ai_coustics  # noqa: E402

from phoneai.adapters.calendar_ical import IcalCalendar, NoCalendar  # noqa: E402
from phoneai.adapters.contacts_yaml import YamlContacts  # noqa: E402
from phoneai.adapters.records_files import FileCallRecords  # noqa: E402
from phoneai.adapters.summariser_openrouter import OpenRouterSummariser  # noqa: E402
from phoneai.adapters.telephony_livekit import (  # noqa: E402
    AGENT_NAME,
    CallFailed,
    CallRequest,
    SipTrunk,
    dial,
)
from phoneai.calls import finish_call  # noqa: E402
from phoneai.config import Settings, load_profile, load_scenario  # noqa: E402
from phoneai.domain import CallRecord, CallState, WorkingHours  # noqa: E402
from phoneai.tools import ToolDeps  # noqa: E402
from phoneai.voice.agent import build_agent, transcript_from  # noqa: E402
from phoneai.voice.session import build_session  # noqa: E402

logger = logging.getLogger("phoneai")

DEFAULT_SCENARIO = "book_gym_session"
DEFAULT_PROFILE = "uk_default"
WRAP_UP_SECONDS = 15  # graceful goodbye before SIP's hard max_call_duration cap


class SystemClock:
    def __init__(self, settings: Settings) -> None:
        self._tz = settings.tz

    def now(self) -> datetime:
        return datetime.now(self._tz)


server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: agents.JobContext) -> None:
    loop = asyncio.get_running_loop()
    settings = Settings()
    deadline = loop.time() + settings.max_call_seconds  # end-to-end, from dispatch
    clock = SystemClock(settings)
    req = CallRequest.from_metadata(ctx.job.metadata, DEFAULT_SCENARIO, DEFAULT_PROFILE)
    call_id = req.call_id or ctx.job.id

    profile = load_profile(settings.profiles_file, req.profile)
    scenario = load_scenario(settings.scenarios_dir, req.scenario, settings.owner_name)
    calendar = (
        IcalCalendar(settings.google_calendar_ical_url, settings.tz)
        if settings.google_calendar_ical_url
        else NoCalendar()
    )
    state = CallState()
    deps = ToolDeps(
        owner=settings.owner_name,
        calendar=calendar,
        clock=clock,
        tz=settings.tz,
        hours=WorkingHours(),
        scenario=scenario,
        state=state,
    )
    session = build_session(profile, settings)
    record = CallRecord(
        call_id=call_id,
        contact_id=req.contact_id,
        scenario=scenario.name,
        profile=profile.name,
        started_at=clock.now(),
        models=profile.models(),
    )
    failed = False

    async def on_shutdown() -> None:
        await finish_call(
            record=record,
            state=state,
            transcript=transcript_from(session.history),
            failed=failed,
            owner=settings.owner_name,
            scenario=scenario,
            summariser=OpenRouterSummariser(settings.summary_model, settings.openrouter_api_key),
            records=FileCallRecords(settings.calls_dir),
            clock=clock,
        )
        logger.info("call %s finished: %s", call_id, record.outcome.value)

    ctx.add_shutdown_callback(on_shutdown)

    is_phone = req.contact_id is not None
    audio_input = room_io.AudioInputOptions()
    if not is_phone:  # noise filter helps browser mics, hurts narrowband phone audio
        audio_input = room_io.AudioInputOptions(
            noise_cancellation=ai_coustics.audio_enhancement(
                model=ai_coustics.EnhancerModel.QUAIL_VF_S
            ),
        )
    await session.start(
        room=ctx.room,
        agent=build_agent(deps),
        room_options=room_io.RoomOptions(audio_input=audio_input),
        record=profile.record_audio,
    )

    if is_phone:
        assert req.contact_id is not None
        contact = YamlContacts(settings.contacts_file).get(req.contact_id)
        try:
            await dial(
                ctx.api,
                room=ctx.room.name,
                call_id=call_id,
                phone=contact.phone,
                trunk=SipTrunk(
                    settings.sip_domain,
                    settings.sip_username,
                    settings.sip_password,
                    settings.caller_id,
                ),
                ringing_timeout_s=settings.ringing_timeout_seconds,
                max_call_duration_s=max(30, int(deadline - loop.time())),
            )
        except CallFailed:
            failed = True
            ctx.shutdown(reason="call failed")
            return
    record.answered = True

    await session.generate_reply(instructions=scenario.opening)

    async def wrap_up_at_deadline() -> None:
        await asyncio.sleep(max(0.0, deadline - loop.time() - WRAP_UP_SECONDS))
        await session.say("Sorry, I need to wrap up now. Goodbye.", allow_interruptions=False)
        ctx.shutdown(reason="max call duration")

    timer = asyncio.create_task(wrap_up_at_deadline())

    async def cancel_timer() -> None:
        timer.cancel()

    ctx.add_shutdown_callback(cancel_timer)


def main() -> None:
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
