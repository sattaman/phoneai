# 4. Privacy by design for a public repo that phones real people

**Status:** accepted · 2026-10-04

## Context
Calls reach real people who haven't agreed to their data being stored, traced or
published. The repository is public.

## Decision
- **Numbers stay local.** Phone numbers live only in a gitignored `contacts.local.yaml`.
  Dispatch metadata, SIP participant identities, logs and call records use a `contact_id`
  or `call_id`. SIP error text is never logged (it can contain the dialled number).
- **Redaction.** Anything that looks like a phone number (9+ digits) is replaced with
  `[number]` in transcripts, notes, arrangement places and summaries before they are
  stored or summarised.
- **Traces.** LiveKit spans pass through a redacting OpenTelemetry exporter before going
  to LangSmith; the LangChain summary run uses a LangSmith client with a redacting
  anonymizer. Both paths were verified against LangSmith with a spoken number.
- **Audio.** Recording is off by default, allowed only on calls to the owner, and never
  attached to traces unless `PHONEAI_TRACE_AUDIO=true` (audio can't be redacted).
- **Repo.** gitleaks runs in pre-commit and CI; a pre-commit hook blocks personal files;
  committed scenarios, contacts and eval cases are synthetic (Ofcom drama-range numbers).

## Consequences
- Names and conversation content still reach LangSmith (redaction targets numbers only).
  Scenario briefs are owner-written config and are traced, so they should not contain
  third parties' personal details.
- The agent always says up front that it's an AI calling on the owner's behalf.
