# Model comparison: book_gym_session

Run 2026-10-04; 2 samples × 6 scripted conversations per model (`evals/cases.yaml`), except Claude Haiku 4.5 (10 of 12; the run was interrupted). **Checks** = deterministic assertions on what the tools recorded (status, time, place, notes, forbidden phrases). **Judges** = LiveKit `task_completion` + `tool_use` judges (google/gemini-2.5-flash). Cost is the agent LLM only at OpenRouter list prices, excluding STT/TTS, judges and the summary. Each model is also a LangSmith experiment in the `phoneai-gym-evals` dataset.

| Model | Samples | Checks pass | Judges pass | LLM TTFT p50 | Tokens in/out | Est. cost / conversation |
|---|---|---|---|---|---|---|
| `anthropic/claude-haiku-4.5` | 10 | 100% | 100% | 1.13s | 6,171 / 232 | $0.0073 |
| `google/gemini-2.5-flash` | 12 | 83% | 100% | 0.81s | 2,639 / 118 | $0.0011 |
| `google/gemini-2.5-flash-lite` | 12 | 83% | 96% | 0.61s | 2,619 / 199 | $0.0003 |
| `openai/gpt-4.1-mini` | 12 | 100% | 100% | 0.83s | 3,074 / 127 | $0.0014 |
| `openai/gpt-oss-120b` | 12 | 92% | 92% | 1.35s | 3,142 / 430 | $0.0002 |

**Check failures**

- `google/gemini-2.5-flash-lite` · joker_with_message #0: no note containing 'quid'
- `google/gemini-2.5-flash-lite` · joker_with_message #1: no note containing 'quid'
- `google/gemini-2.5-flash` · joker_with_message #0: no note containing 'quid'
- `google/gemini-2.5-flash` · joker_with_message #1: no note containing 'quid'
- `openai/gpt-oss-120b` · wont_commit_then_does #0: nothing recorded

## Findings

- **`openai/gpt-4.1-mini` is the default** (`profiles.yaml`): the only model that passed
  every check and every judge, with a 0.83s median time to first token and about $0.0014
  per conversation. `google/gemini-2.5-flash-lite` stays as the fallback.
- **The Gemini models never saved a joking message.** With "Tell Tom he still owes me
  twenty quid", both Flash and Flash-Lite played along but didn't call `save_note`. LLM
  judges passed these conversations; only the deterministic check caught it.
- **`gpt-oss-120b` is the cheapest** but the slowest to first token (1.35s, too slow for a
  natural phone turn), and once recorded nothing when the caller only committed on the
  second turn.
- **Claude Haiku 4.5 was also perfect,** but about 5× the cost and slower to first token,
  with more input tokens per call (longer tool and system prompts).

## Follow-up: GPT-6 Luna (reasoning model) and stricter checks

The checks were tightened after review: each case now also verifies the booked **date**,
every conversation starts with the production opening (which must disclose that it's an
AI), and fallback models are disabled so results belong to the named model.

| Model | Reasoning | Checks pass | Judges pass | LLM TTFT p50 | Est. cost / conversation |
|---|---|---|---|---|---|
| `openai/gpt-4.1-mini` | n/a | 100% | 100% | 0.82s | $0.0017 |
| `openai/gpt-6-luna` | minimal | 100% | 100% | 1.29s | $0.0005 |
| `openai/gpt-6-luna` | low | 100% | 92% | 1.35s | $0.0005 |
| `openai/gpt-6-luna` | default | 100% | 88% | 2.55s | $0.0006 |

The default-reasoning row ran before the stricter checks were added. Reasoning effort
matters most for latency: at its default Luna thinks before every reply, which is too slow
for a phone turn. At `minimal` it matches GPT-4.1-mini on quality at about a third of the
cost, but takes roughly 0.5s longer to start speaking. It's available as the `uk_luna`
profile; `uk_default` stays on GPT-4.1-mini for responsiveness.
