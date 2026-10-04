# 1. Ports and adapters, kept minimal

**Status:** accepted · 2026-10-04

## Context
The proof of concept was one file mixing LiveKit, Twilio, an iCal feed and OpenRouter.
Nothing could be tested without placing a real phone call, and swapping a provider meant
editing call-handling code.

## Decision
A framework-free core (`domain.py`, `tools/`, `calls.py`) depends only on small
`typing.Protocol` ports (`ports.py`): `Calendar`, `Contacts`, `CallRecords`, `Summariser`,
`Clock`. Adapters implement them (iCal, YAML, JSON files, LangChain/OpenRouter), and
in-memory fakes implement them for tests. Only the composition roots (`voice/entry.py`,
`cli.py`) know concrete adapters. No DI framework.

Ports are added when a capability needs one, not speculatively: there is no `Messaging`
port until a messaging tool exists.

## Consequences
- 70+ offline tests run in about two seconds, with no keys or network.
- Agent behaviour tests run the **real** tools against a fake calendar, so they need no
  tool mocking.
- A Google Calendar API or SQLite adapter can replace iCal or files without touching tools.
