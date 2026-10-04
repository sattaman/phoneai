"""Builds a LiveKit AgentSession from a voice profile."""

from __future__ import annotations

from livekit.agents import AgentSession, TurnHandlingOptions, inference
from livekit.plugins import openai

from phoneai.config import Profile, Settings


def build_llm(profile: Profile, settings: Settings, *, fallback: bool = True) -> openai.LLM:
    """OpenRouter LLM for a profile. Evals pass fallback=False so results are attributable
    to the named model."""
    extra: dict = {}
    if profile.llm_reasoning_effort:
        extra["reasoning_effort"] = profile.llm_reasoning_effort
    return openai.LLM.with_openrouter(
        model=profile.llm_model,
        fallback_models=[profile.llm_fallback] if fallback else None,
        api_key=settings.openrouter_api_key,
        app_name="phoneai",
        temperature=0.4,
        **extra,
    )


def build_session(profile: Profile, settings: Settings) -> AgentSession:
    return AgentSession(
        stt=inference.STT(model=profile.stt_model, language=profile.stt_language),
        llm=build_llm(profile, settings),
        tts=inference.TTS(
            model=profile.tts_model, voice=profile.tts_voice, language=profile.tts_language
        ),
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
            # Phone STT finals can arrive late; wait a little before replying.
            endpointing={
                "min_delay": profile.min_endpointing_delay,
                "max_delay": profile.max_endpointing_delay,
            },
            # Keep talking through "mm-hmm" style backchannels.
            interruption={"mode": "adaptive"},
        ),
    )
