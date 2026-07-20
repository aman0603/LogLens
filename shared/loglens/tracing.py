"""OpenTelemetry tracing setup shared across services.

Initializes a tracer provider with an OTLP exporter (configured via env). When
the exporter is unavailable, tracing degrades gracefully (no-op) so services
still start. Provides helpers to instrument HTTP servers and to create spans
around Kafka produce/consume and DB calls.
"""

import os
from typing import Optional, Any

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    _HAVE_OTEL = True
except ImportError:  # pragma: no cover - optional dependency
    _HAVE_OTEL = False
    trace = None


def init_tracing(service_name: str) -> Optional[Any]:
    if not _HAVE_OTEL:
        return None
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    provider = TracerProvider()
    if endpoint:
        try:
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        except Exception:
            pass
    trace.set_tracer_provider(provider)
    try:
        RequestsInstrumentor().instrument()
    except Exception:
        pass
    return provider


def instrument_app(app, service_name: str):
    if not _HAVE_OTEL:
        return
    try:
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass


def get_tracer(service_name: str):
    if not _HAVE_OTEL:
        import contextlib

        @contextlib.contextmanager
        def _noop(name):
            yield None

        return _noop
    return trace.get_tracer(service_name)


def current_trace_id() -> Optional[str]:
    if not _HAVE_OTEL:
        return None
    ctx = trace.get_current_span().get_span_context()
    if ctx and ctx.trace_id:
        return format(ctx.trace_id, "016x")
    return None
