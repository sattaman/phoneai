"""LangSmith tracing for voice calls, via the official LiveKit integration.

`configure_livekit()` turns LiveKit's OpenTelemetry spans into one LangSmith trace per
call; `set_thread_id(call_id)` groups them into a thread. We insert our own exporter
between the integration and LangSmith to:

- redact phone numbers from every string attribute and event (they can be spoken on a
  call and end up in prompts, transcripts and tool arguments), and
- stamp per-call metadata (scenario, profile, models, contact id) on every span,
  keyed by the call's thread id.

Nothing leaves the process until it has passed through `RedactingExporter`.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from typing import Any

from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

from phoneai.domain import redact_phone_numbers

logger = logging.getLogger(__name__)

THREAD_KEY = "langsmith.metadata.thread_id"
_call_metadata: dict[str, dict[str, str]] = {}


def register_call(call_id: str, metadata: dict[str, str]) -> None:
    """Metadata to stamp on every span of this call's trace."""
    _call_metadata[call_id] = metadata


def _redact_value(value: Any, redact: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list | tuple) and value and isinstance(value[0], str):
        return tuple(redact(v) for v in value)
    return value


def clean_span(
    span: ReadableSpan,
    redact: Callable[[str], str] = redact_phone_numbers,
    metadata_for: Callable[[str], dict[str, str]] = lambda t: _call_metadata.get(t, {}),
) -> ReadableSpan:
    """Copy of `span` with redacted attributes/events and per-call metadata added."""
    attrs = {k: _redact_value(v, redact) for k, v in (span.attributes or {}).items()}
    thread_id = attrs.get(THREAD_KEY)
    if isinstance(thread_id, str):
        attrs.update({f"langsmith.metadata.{k}": v for k, v in metadata_for(thread_id).items()})
    events = [
        Event(
            e.name,
            {k: _redact_value(v, redact) for k, v in (e.attributes or {}).items()},
            e.timestamp,
        )
        for e in span.events
    ]
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=attrs,
        events=events,
        links=span.links,
        kind=span.kind,
        instrumentation_scope=span.instrumentation_scope,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
    )


class RedactingExporter(SpanExporter):
    def __init__(self, inner: Any) -> None:  # any SpanExporter-like (LangSmith's OtelExporter)
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([clean_span(s) for s in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def tracing_enabled() -> bool:
    return os.getenv("LANGSMITH_TRACING", "").lower() == "true" and bool(
        os.getenv("LANGSMITH_API_KEY")
    )


def setup_tracing(downstream_exporter: SpanExporter | None = None) -> Any | None:
    """Enable LangSmith tracing for LiveKit sessions. Call before creating AgentServer.

    Returns the LangSmith span processor, or None when tracing is off.
    """
    if downstream_exporter is None and not tracing_enabled():
        return None
    from langsmith.integrations.livekit import configure_livekit

    exporter: Any = downstream_exporter
    if exporter is None:
        from langsmith.integrations.otel.processor import OtelExporter

        exporter = OtelExporter()  # LangSmith OTLP endpoint, from LANGSMITH_* env
    processor = configure_livekit(
        downstream_processor=BatchSpanProcessor(RedactingExporter(exporter)),
        metadata={"app": "phoneai", "ls_modality": "audio"},
    )
    logger.info("LangSmith tracing enabled (project %s)", os.getenv("LANGSMITH_PROJECT"))
    return processor


def start_call_trace(call_id: str, metadata: dict[str, str]) -> None:
    """Group this call's spans into one LangSmith thread and attach its metadata.

    Must be called inside the call's own task (the thread id is a ContextVar).
    """
    if not tracing_enabled():
        return
    from langsmith.integrations.livekit import set_thread_id

    register_call(call_id, metadata)
    set_thread_id(call_id)
