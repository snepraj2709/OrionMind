from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.shared.config.settings import Settings
from app.shared.database.session import DatabaseSessions


def configure_tracing(
    app: FastAPI, *, settings: Settings, sessions: DatabaseSessions
) -> TracerProvider | None:
    if not settings.OTEL_ENABLED:
        return None
    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT.get_secret_value(),
                insecure=False,
            )
        )
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    engines = [
        engine
        for engine in (sessions.application_engine, sessions.worker_engine)
        if engine is not None
    ]
    if engines:
        SQLAlchemyInstrumentor().instrument(engines=engines, tracer_provider=provider)
    return provider
