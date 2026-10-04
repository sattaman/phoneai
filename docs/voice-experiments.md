# Voice experiments: what was tried on real calls, and why the defaults are what they are

All figures were measured on 2026-10-04 from a UK laptop (behind a corporate proxy), via
LiveKit Inference unless noted. They're single-session measurements, so treat them as
indicative, not as benchmarks.

## 1. Text-to-speech: time to first audio and feel

Same sentence for every voice; median of 3 runs.

| Voice | Accent | Time to first audio | Notes |
|---|---|---|---|
| **Cartesia Sonic-3.6, British female** | British | **0.35s** | Chosen by ear; fastest; supports expressive mode |
| Gradium Harper | US | 0.31s | |
| Inworld TTS-2 Olivia | British | 0.50s | Near the top of the Artificial Analysis TTS leaderboard |
| Inworld TTS-2 Ashley | US | 0.54s | Natural, but too American for this use |
| Gemini 3.8 Flash-Lite TTS, Zephyr + British style prompt | British | 0.76s | Rich, steerable delivery; text isn't streamed in, so it works one sentence at a time; Google free tier rate-limits quickly |
| Deepgram Aura-2 Pandora (original default) | British | 0.83s | Slowest to start and least natural; replaced |
| Gemini 3.1 Flash TTS (preview) | British via prompt | 1.07s | |

Takeaways:
- First-audio time adds directly to every reply. Moving from Deepgram to Cartesia saves
  about 0.5s per turn.
- Expressive mode (LiveKit) lets the LLM mark up emotion, pauses and laughs. It helps the
  light-hearted tone. Its tags are stripped from transcripts before storage.
- Of the voice samples, the British voices from most providers sounded stiffer than their
  American voices. The Cartesia British voice was the exception.

## 2. LLM for the voice loop

See [evals.md](evals.md). `gpt-4.1-mini` was the only model at 100% on both the
deterministic checks and the judges, with a 0.82s median time to first token. GPT-6 Luna
matches its quality at about a third of the cost, but only with `reasoning_effort=minimal`
(1.29s). At its default reasoning (2.55s) it's too slow for a phone turn.

## 3. Speech-to-speech (Gemini Live): three real calls

Speech-to-speech models listen, think and speak in one model, and lead the naturalness
benchmarks. Three calls with Gemini Live, analysed from LangSmith span timings:

| Call | Model | What happened |
|---|---|---|
| 1 | `gemini-3.8-live-extended-thinking` (thinking LOW) | 11s before the opening; 4–5s per reply; a 7s silence prompted "ya ya?", which interrupted the reply, so the first answer came about 12s after the caller finished |
| 2 | `gemini-3.1-flash-live-preview`, tighter turn detection | About 20s before the opening; my "ignore short sounds" setting merged six "hello?"s into one turn, so the reply came about 20s later (setting reverted) |
| 3 | 3.1 Flash Live + pre-rendered opening | Opening played 0.00s after answer, then the model server returned an internal error (1011) mid-call; the reconnected session never replied |

Findings:
- **Speaking first is the weak spot.** With no caller audio yet, the model took 10–20s to
  open (LiveKit logged "received server content but no active generation").
  Pre-rendering an opening line in the same prebuilt voice (Gemini TTS shares Gemini
  Live's voices) while the phone rings fixed this, but it means a fixed first sentence per
  scenario.
- **Silence compounds.** On a phone line, people fill gaps ("hello?"). With server-side
  turn detection, that becomes an interruption that restarts generation.
- **Benchmarks vs a phone line.** Artificial Analysis reports about 1.35s to first audio
  for 3.8 Extended Thinking. On 8kHz phone audio, replies took 4–5s.
- **Cost.** About 32k input tokens for a 90s call (context is re-billed every turn), so
  roughly 10p, 2–5× the cascade.

**Decision.** The cascade (Deepgram Nova-3 → gpt-4.1-mini → Cartesia, expressive) stays
the default. On calls it replies in about 1–1.5s, uses tools reliably, and costs less.
Speech-to-speech stays available as profiles (`uk_gemini_live`, `uk_gemini_flash_live`)
for re-testing as the models mature. GPT-Live-1 and Grok Voice are the next candidates.

## 4. Things that weren't the model

- **No warm worker process** added about 5s before dialling (`num_idle_processes=1`).
- **The deadline was measured from the request,** so a slow network used up a 2-minute
  call before dialling. It's now measured from call start, and stale requests are dropped.
- **A noise-cancellation filter** tuned for browser microphones hurt narrowband phone audio
  and blocked the event loop. It's now browser-only.
