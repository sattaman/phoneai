"""The scripted opening line: rendered while the phone rings, played the instant it's answered.

Speech-to-speech models are slow and unreliable at speaking first with no caller audio
(seen on calls: 10-20s before the first word). Pre-rendering the opening in the same
voice (Gemini TTS shares Gemini Live's prebuilt voices) removes that wait and guarantees
the AI disclosure is said exactly.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from livekit import rtc
from livekit.plugins import google

from phoneai.config import Profile, Settings

logger = logging.getLogger(__name__)

OPENING_TTS_MODEL = "gemini-3.8-flash-lite-tts"


async def prerender_opening(
    profile: Profile, settings: Settings, text: str
) -> list[rtc.AudioFrame] | None:
    """Render `text` in the realtime profile's voice. None if not applicable or it fails."""
    if not (profile.is_realtime and settings.gemini_api_key and text):
        return None
    tts = google.beta.GeminiTTS(
        model=OPENING_TTS_MODEL,
        voice_name=profile.realtime_voice,
        api_key=settings.gemini_api_key,
        instructions=profile.voice_style or None,
    )
    try:
        frames: list[rtc.AudioFrame] = []
        async with tts.synthesize(text) as stream:
            async for ev in stream:
                frames.append(ev.frame)
        return frames or None
    except Exception as e:
        logger.warning("opening pre-render failed: %s", type(e).__name__)
        return None
    finally:
        await tts.aclose()


async def frames_stream(frames: list[rtc.AudioFrame]) -> AsyncIterator[rtc.AudioFrame]:
    for frame in frames:
        yield frame
        await asyncio.sleep(0)
