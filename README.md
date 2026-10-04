# phoneai

An AI phone assistant that makes outbound calls on your behalf: it holds a natural
British-English conversation, uses tools (calendar availability, recording what was agreed,
taking messages), and writes up each call.

Built on [LiveKit Agents](https://docs.livekit.io/agents/) with a ports-and-adapters core,
so tools and providers can be swapped and the logic is tested offline.

> Status: work in progress.

## How it works

```
phoneai call friend ──dispatch──▶ LiveKit agent worker ──SIP──▶ Twilio ──▶ phone
                                     │
             STT (Deepgram) → LLM (OpenRouter) → TTS (Deepgram Aura-2, British voice)
                                     │ tools
             check_availability · record_arrangement · save_note · end_call
                                     │
                       calls/<id>.json + .md   (summary via LangChain)
```

- **Tools are framework-free** (`src/phoneai/tools/`) and adapted to LiveKit in one place.
  Scenarios (`scenarios/*.yaml`) list which tools a call may use.
- **Outcomes come from tool state, not model claims.** `record_arrangement` checks the
  calendar itself and records `agreed` or `provisional`, so the agent can't invent availability.
- **Privacy:** phone numbers live only in a local, gitignored `contacts.local.yaml`.
  Dispatch metadata, participant identities and call records use contact ids; numbers
  spoken on a call are redacted from records, summaries and traces.
- **Observability:** each call is one LangSmith thread (via the official
  `langsmith[livekit]` integration): STT/LLM/TTS spans, tool calls, token usage and latency,
  plus the post-call summary run, tagged with scenario, profile and models. Spans pass
  through a redacting exporter before leaving the process. Call records also store
  p50/p95 turn latency and token counts.

## Quick start

```sh
make install                                  # uv sync + pre-commit hooks
cp .env.example .env                          # LiveKit, OpenRouter, Twilio SIP keys
cp contacts.example.yaml contacts.local.yaml  # who the agent may call
make test                                     # offline tests, free

uv run phoneai agent dev                      # terminal 1: agent worker
uv run phoneai call friend --scenario book_gym_session   # terminal 2
uv run phoneai calls                          # list call outcomes
```

## Layout

```
src/phoneai/
  domain.py     core types and pure rules (free slots, outcomes, instructions)
  ports.py      interfaces: Calendar, Contacts, CallRecords, Summariser, Clock
  tools/        agent tools (plain async functions)
  adapters/     iCal calendar, YAML contacts, file records, OpenRouter summariser, LiveKit SIP, fakes
  voice/        LiveKit agent, session factory, tool adapter, worker entrypoint
  calls.py      finish a call: outcome, summary, persistence
  cli.py        phoneai agent | call | calls
```

## License

MIT
