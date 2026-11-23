"""Spans recorded in memory, for tests that check what telemetry carries and what it never does."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

_exporter = InMemorySpanExporter()


@contextmanager
def recorded_spans() -> Iterator[list[ReadableSpan]]:
    """The list fills when the block ends. The provider is global and set once per process."""
    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(_exporter))
        trace.set_tracer_provider(provider)
    _exporter.clear()
    spans: list[ReadableSpan] = []
    try:
        yield spans
    finally:
        spans.extend(_exporter.get_finished_spans())


def texts_in(spans: Sequence[ReadableSpan]) -> str:
    parts = []
    for recorded in spans:
        parts += [recorded.name, recorded.status.description or ""]
        parts += [str(value) for value in (recorded.attributes or {}).values()]
        for event in recorded.events:
            parts += [event.name, *(str(value) for value in (event.attributes or {}).values())]
    return "\n".join(parts)
