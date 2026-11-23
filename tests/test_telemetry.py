import os

import pytest
from azure.identity import ManagedIdentityCredential
from opentelemetry.trace import SpanKind
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from margin_copilot_shared import telemetry
from margin_copilot_shared.telemetry import configure_telemetry, instrument_app, span
from margin_copilot_shared.testing.telemetry import recorded_spans, texts_in

CS = "InstrumentationKey=00000000-0000-0000-0000-000000000000;IngestionEndpoint=https://example.invalid/"
ENV = {"APPLICATIONINSIGHTS_CONNECTION_STRING": CS, "AZURE_CLIENT_ID": "client-id"}


def hello_app():
    async def hello(request):
        return PlainTextResponse("hello")

    return Starlette(routes=[Route("/", hello, methods=["GET"])])


@pytest.fixture(autouse=True)
def fresh_process(monkeypatch):
    monkeypatch.setattr(telemetry, "_served", False)


def test_no_connection_string_means_no_telemetry():
    calls = []
    assert configure_telemetry("orchestrator", {}, configure=lambda **kw: calls.append(kw)) is False
    assert calls == []


def test_keyless_export_with_every_trace_kept(monkeypatch):
    monkeypatch.delenv("OTEL_LOGS_EXPORTER", raising=False)
    calls = []
    assert configure_telemetry("orchestrator", ENV, configure=lambda **kw: calls.append(kw)) is True
    (kw,) = calls
    assert kw["connection_string"] == CS and kw["sampling_ratio"] == 1.0
    assert isinstance(kw["credential"], ManagedIdentityCredential)
    assert kw["resource"].attributes["service.name"] == "orchestrator"
    assert os.environ["OTEL_LOGS_EXPORTER"] == "none"


def test_a_failed_setup_never_stops_the_service(caplog):
    def broken(**kw):
        raise ValueError("bad connection string")

    assert configure_telemetry("orchestrator", ENV, configure=broken) is False
    assert "ValueError" in caplog.text


def test_an_incoming_traceparent_continues_the_trace():
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    with recorded_spans() as spans:
        TestClient(instrument_app(hello_app())).get(
            "/", headers={"traceparent": f"00-{trace_id}-00f067aa0ba902b7-01"}
        )
    server = [s for s in spans if s.kind == SpanKind.SERVER]
    assert [format(s.context.trace_id, "032x") for s in server] == [trace_id]


def test_the_first_real_request_is_marked_cold_not_the_preflight():
    with recorded_spans() as spans:
        client = TestClient(instrument_app(hello_app()))
        client.options("/")
        client.get("/")
        client.get("/")
    marks = [s.attributes.get("margin.cold_start") for s in spans if s.kind == SpanKind.SERVER]
    assert marks == [None, True, None]


def test_a_span_records_labels():
    with recorded_spans() as spans, span("orchestrator.route", **{"margin.plan": "data-agent"}):
        pass
    assert [(s.name, s.attributes["margin.plan"]) for s in spans] == [
        ("orchestrator.route", "data-agent")
    ]


def test_texts_in_covers_names_and_attribute_values():
    with recorded_spans() as spans, span("orchestrator.agent", **{"margin.agent": "data-agent"}):
        pass
    assert "orchestrator.agent" in texts_in(spans) and "data-agent" in texts_in(spans)
