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
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import Any

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Link

from phoneai.domain import redact_phone_numbers

logger = logging.getLogger(__name__)

THREAD_KEY = "langsmith.metadata.thread_id"
_MAX_CALLS = 256  # spans export in batches after a call ends, so keep recent calls around
_call_metadata: OrderedDict[str, dict[str, str]] = OrderedDict()


def register_call(call_id: str, metadata: dict[str, str]) -> None:
    """Metadata to stamp on every span of this call's trace (bounded, per process)."""
    _call_metadata[call_id] = metadata
    _call_metadata.move_to_end(call_id)
    while len(_call_metadata) > _MAX_CALLS:
        _call_metadata.popitem(last=False)


def redact_tree(value: Any) -> Any:
    """Redact phone numbers in every string of a nested dict/list structure."""
    if isinstance(value, str):
        return redact_phone_numbers(value)
    if isinstance(value, dict):
        return {k: redact_tree(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(redact_tree(v) for v in value)
    return value


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
    """Copy of `span` with per-call metadata added, then every string attribute, event,
    link and resource attribute redacted."""

    def clean(attributes: Any) -> dict[str, Any]:
        return {k: _redact_value(v, redact) for k, v in (attributes or {}).items()}

    attrs = dict(span.attributes or {})
    thread_id = attrs.get(THREAD_KEY)
    if isinstance(thread_id, str):
        attrs.update({f"langsmith.metadata.{k}": v for k, v in metadata_for(thread_id).items()})
    attrs = clean(attrs)
    events = [Event(e.name, clean(e.attributes), e.timestamp) for e in span.events]
    links = [Link(link.context, clean(link.attributes)) for link in span.links]
    resource = Resource(clean(span.resource.attributes), span.resource.schema_url)
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=resource,
        attributes=attrs,
        events=events,
        links=links,
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
    # Audio can't be redacted, so it is never attached to traces unless explicitly enabled.
    audio = os.getenv("PHONEAI_TRACE_AUDIO", "").lower() == "true"
    processor = configure_livekit(
        downstream_processor=BatchSpanProcessor(RedactingExporter(exporter)),
        metadata={"app": "phoneai", "ls_modality": "audio"},
        recording_mode="session_report" if audio else "none",
    )
    logger.info("LangSmith tracing enabled (project %s)", os.getenv("LANGSMITH_PROJECT"))
    return processor


def masked_langchain_callbacks() -> list[Any]:
    """Callbacks for LangChain runs (e.g. the summary): a LangSmith tracer whose client
    redacts inputs, outputs and metadata. Passing our own tracer stops LangChain adding
    its default, unmasked one. Empty when tracing is off."""
    if not tracing_enabled():
        return []
    from langchain_core.tracers import LangChainTracer
    from langsmith import Client

    client = Client(anonymizer=redact_tree)
    return [LangChainTracer(client=client, project_name=os.getenv("LANGSMITH_PROJECT"))]


def start_call_trace(call_id: str, metadata: dict[str, str]) -> None:
    """Group this call's spans into one LangSmith thread and attach its metadata.

    Must be called inside the call's own task (the thread id is a ContextVar).
    """
    if not tracing_enabled():
        return
    from langsmith.integrations.livekit import set_thread_id

    register_call(call_id, metadata)
    set_thread_id(call_id)
