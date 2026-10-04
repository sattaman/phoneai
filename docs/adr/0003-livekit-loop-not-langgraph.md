# 3. LiveKit runs the conversation; LangChain only where it helps; no LangGraph (yet)

**Status:** accepted · 2026-10-04

## Context
LiveKit offers `LLMAdapter` to make a LangGraph graph the agent's "brain". We evaluated it
against the LiveKit-native loop.

## Decision
Keep LiveKit's native STT → LLM → TTS loop with LiveKit function tools. Use LangChain
(`langchain-openrouter` with structured output) for the post-call summary, where typed
output and automatic LangSmith tracing are useful.

## Why not LLMAdapter now
- It ignores LiveKit function tools, so `EndCallTool` and our tool adapter would not work;
  tools would have to move inside the graph.
- With the default stream mode it speaks tokens from **every** chat-model node, so
  internal routing or classification output would be voiced.
- It reports no token usage, which our metrics and cost comparison rely on.
- Extra graph steps add latency to every spoken turn.

## Consequences
LangGraph is reserved for a future experiment (an alternative brain compared on the same
evals) or for genuinely long-running workflows such as waiting days for the owner's reply.
