"""Builds a LiveKit AgentSession from a voice profile."""

from __future__ import annotations

from typing import Any

from google.genai import types
from livekit.agents import NOT_GIVEN, AgentSession, TurnHandlingOptions, inference
from livekit.plugins import google, openai  # plugins must load on the main thread

from phoneai.config import Profile, Settings


def build_llm(profile: Profile, settings: Settings, *, fallback: bool = True) -> openai.LLM:
    """OpenRouter LLM for a profile. Evals pass fallback=False so results are attributable
    to the named model."""
    extra: dict[str, Any] = {}
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


def stt_keyterms(model: str, keyterms: tuple[str, ...]) -> Any:
    """Provider-specific keyterm option for LiveKit Inference STT."""
    if not keyterms:
        return NOT_GIVEN
    if model.startswith("deepgram/"):
        return {"keyterm": list(keyterms)}
    if model.startswith("assemblyai/"):
        return {"keyterms_prompt": list(keyterms)}
    return NOT_GIVEN


def build_session(
    profile: Profile, settings: Settings, keyterms: tuple[str, ...] = ()
) -> AgentSession:
    if profile.is_realtime:
        # Speech-to-speech: the model does its own listening, turn-taking and speaking.
        options: dict[str, Any] = {}
        if profile.realtime_thinking:
            options["thinking_config"] = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel(profile.realtime_thinking)
            )
        activity: dict[str, Any] = {}
        if profile.realtime_end_sensitivity:
            activity["end_of_speech_sensitivity"] = types.EndSensitivity(
                f"END_SENSITIVITY_{profile.realtime_end_sensitivity}"
            )
        if profile.realtime_start_sensitivity:
            activity["start_of_speech_sensitivity"] = types.StartSensitivity(
                f"START_SENSITIVITY_{profile.realtime_start_sensitivity}"
            )
        if profile.realtime_silence_ms is not None:
            activity["silence_duration_ms"] = profile.realtime_silence_ms
        if activity:
            options["realtime_input_config"] = types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(**activity)
            )
        turn_handling: dict[str, Any] = {}
        if profile.min_interruption_seconds is not None:
            turn_handling["turn_handling"] = TurnHandlingOptions(
                interruption={"min_duration": profile.min_interruption_seconds}
            )
        return AgentSession(
            llm=google.realtime.RealtimeModel(
                model=profile.realtime_model or "",
                voice=profile.realtime_voice,
                api_key=settings.gemini_api_key,
                language="en-GB",
                **options,
            ),
            **turn_handling,
        )
    return AgentSession(
        stt=inference.STT(
            model=profile.stt_model,
            language=profile.stt_language,
            # Keyterm prompting: brand and place names it would otherwise mishear.
            extra_kwargs=stt_keyterms(profile.stt_model, keyterms),
        ),
        llm=build_llm(profile, settings),
        tts=inference.TTS(
            model=profile.tts_model, voice=profile.tts_voice, language=profile.tts_language
        ),
        expressive=profile.expressive,
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
            # Phone STT finals can arrive late; wait a little before replying.
            endpointing={
                "min_delay": profile.min_endpointing_delay,
                "max_delay": profile.max_endpointing_delay,
            },
            # Keep talking through "mm-hmm" style backchannels.
            interruption={"mode": "adaptive"},
            # Start drafting the reply while the end of the turn is still being confirmed.
            preemptive_generation={"enabled": True},
        ),
    )
