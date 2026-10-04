# 2. Tools first; outcomes come from tool state, not model claims

**Status:** accepted · 2026-10-04

## Context
On a real call the model told the callee "Tom is busy on Sundays" although no calendar was
connected, and on another it never asked which gym. Prompt instructions alone did not
prevent either.

## Decision
- Capabilities are tools: plain async functions in `src/phoneai/tools/`, built from
  `ToolDeps` and adapted to LiveKit in one place (`voice/tool_adapter.py`). Scenarios list
  the tools a call may use; unknown tool names fail fast.
- `record_arrangement` owns the decision: it checks the calendar itself and records
  `agreed` (owner free), `provisional` (calendar unknown) or nothing (busy, outside
  available hours, vague place, in the past), and tells the agent exactly what to say.
- The call outcome (`agreed | provisional | incomplete | no_answer | failed`) is computed
  from recorded state by a pure function. The LLM-written summary never sets it.

## Consequences
- Both real-call failures are now regression tests that run against a real model
  (`pytest -m llm`).
- New capabilities (calendar writes, messaging) are new tools plus a scenario entry; the
  agent class does not change.
