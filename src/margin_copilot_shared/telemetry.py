"""Tracing for every service (D-043): OpenTelemetry to Application Insights, keyless, carrying
counts, durations and labels but never content. Without a connection string nothing is exported."""

import logging
import os
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import Any

from azure.identity import ManagedIdentityCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import Span
from starlette.types import ASGIApp

log = logging.getLogger(__name__)
_served = False  # this process has served a request: later ones aren't cold starts


def configure_telemetry(
    service: str,
    env: Mapping[str, str],
    configure: Callable[..., None] = configure_azure_monitor,
) -> bool:
    connection_string = env.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not connection_string:
        return False
    try:
        os.environ["OTEL_LOGS_EXPORTER"] = "none"  # container logs reach the workspace already
        configure(
            connection_string=connection_string,
            credential=ManagedIdentityCredential(client_id=env["AZURE_CLIENT_ID"]),
            resource=Resource.create({"service.name": service}),
            sampling_ratio=1.0,  # every eval case's trace must exist for its cost
        )
    except Exception as error:  # an untraced service beats one that won't start
        log.warning("telemetry not set up: %s", type(error).__name__)
        return False
    return True


def _mark_cold_start(span: Span, scope: dict[str, Any]) -> None:
    """After scale-from-zero a browser's preflight comes first; the request after it is slow."""
    global _served
    if _served or scope.get("type") != "http" or scope.get("method") == "OPTIONS":
        return
    _served = True
    span.set_attribute("margin.cold_start", True)


def instrument_app(app: ASGIApp) -> ASGIApp:
    return OpenTelemetryMiddleware(
        app, exclude_spans=["receive", "send"], server_request_hook=_mark_cold_start
    )


def span(name: str, **attributes: str | int | float | bool) -> AbstractContextManager[Span]:
    return trace.get_tracer("margin_copilot").start_as_current_span(name, attributes=attributes)
