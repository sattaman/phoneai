from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.trace import SpanContext, TraceFlags

from phoneai.observability import THREAD_KEY, RedactingExporter, clean_span, register_call


def span(attrs, events=()) -> ReadableSpan:
    ctx = SpanContext(trace_id=1, span_id=2, is_remote=False, trace_flags=TraceFlags(1))
    return ReadableSpan(name="llm_request", context=ctx, attributes=attrs, events=list(events))


def test_clean_span_redacts_numbers_in_attributes_lists_and_events():
    s = clean_span(
        span(
            {
                "gen_ai.prompt": "my number is 07700 900123",
                "lk.tools": ["call +44 7700 900123", "save_note"],
                "gen_ai.usage.input_tokens": 120,
            },
            [Event("user_input", {"text": "ring 07700 900123"})],
        )
    )
    attrs = dict(s.attributes or {})
    assert attrs["gen_ai.prompt"] == "my number is [number]"
    assert attrs["lk.tools"] == ("call [number]", "save_note")
    assert attrs["gen_ai.usage.input_tokens"] == 120
    assert dict(s.events[0].attributes or {})["text"] == "ring [number]"


def test_clean_span_stamps_per_call_metadata_by_thread_id():
    register_call("call-42", {"scenario": "book_gym_session", "contact_id": "friend"})
    attrs = dict(clean_span(span({THREAD_KEY: "call-42"})).attributes or {})
    assert attrs["langsmith.metadata.scenario"] == "book_gym_session"
    assert attrs["langsmith.metadata.contact_id"] == "friend"
    other = dict(clean_span(span({THREAD_KEY: "unknown"})).attributes or {})
    assert "langsmith.metadata.scenario" not in other


def test_redacting_exporter_cleans_before_forwarding():
    sent = []

    class Inner:
        def export(self, spans):
            sent.extend(spans)
            return SpanExportResult.SUCCESS

    RedactingExporter(Inner()).export([span({"x": "07700 900123"})])
    assert dict(sent[0].attributes)["x"] == "[number]"
