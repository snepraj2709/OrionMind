from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.contract import assert_public_contract
from app.modules.health.routes import router as health_router
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.service import JobService
from app.modules.jobs.worker import ProcessingWorker
from app.modules.entries.repository import EntryRepository
from app.modules.entries.service import EntryService
from app.modules.entries.audio import (
    TRANSCRIPTION_TIMEOUT_SECONDS,
    OpenAITranscriber,
    UnavailableTranscriber,
)
from app.modules.profile.repository import ProfileRepository
from app.modules.profile.service import ProfileService
from app.modules.processing.provider import (
    OpenAIEntryAnalysisProvider,
    UnavailableEntryAnalysisProvider,
)
from app.modules.processing.embeddings import (
    OpenAISignalEmbeddingProvider,
    UnavailableSignalEmbeddingProvider,
)
from app.modules.processing.redaction import (
    PiiRedactor,
    initialize_offline_privacy_runtime,
)
from app.modules.processing.repository import ProcessingRepository
from app.modules.processing.service import ProcessingService
from app.modules.reflection_engine.provider import (
    OpenAIReflectionProvider,
    UnavailableReflectionProvider,
)
from app.modules.reflection_engine.repository import ReflectionEngineRepository
from app.modules.reflection_engine.service import ReflectionEngineService
from app.modules.reflections.repository import ReflectionsRepository
from app.modules.reflections.service import ReflectionsService
from app.modules.past_imports.repository import PastImportRepository
from app.modules.past_imports.service import PastImportService
from app.openapi_contract import install_local_openapi
from app.router import router as api_router
from app.shared.auth.service import AuthenticationService
from app.shared.config.settings import Settings, get_settings
from app.shared.database.session import DatabaseSessions, build_database_sessions
from app.shared.exceptions.handlers import install_error_handlers
from app.shared.http.middleware import install_http_middleware
from app.shared.http.rate_limits import ProcessRateLimiter
from app.shared.integrations.supabase_auth import (
    SupabaseAccountAuthGateway,
    SupabaseTokenVerifier,
    UnavailableAccountAuthGateway,
    UnavailableTokenVerifier,
)
from app.shared.integrations.openai import build_openai_client
from app.shared.observability.logging import configure_logging
from app.shared.observability.reflection import (
    ReflectionTelemetry,
    configure_reflection_telemetry,
)
from app.shared.observability.tracing import configure_tracing
from app.shared.security.encryption import AesGcmContentCipher, UnavailableContentCipher


def _build_token_verifier(settings: Settings):
    if not settings.SUPABASE_URL.strip() or not settings.SUPABASE_PUBLISHABLE_KEY.get_secret_value():
        return UnavailableTokenVerifier()
    from supabase import create_client

    client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_PUBLISHABLE_KEY.get_secret_value(),
    )
    return SupabaseTokenVerifier(client)


def _build_account_auth(settings: Settings):
    if (
        not settings.SUPABASE_URL.strip()
        or not settings.SUPABASE_PUBLISHABLE_KEY.get_secret_value()
        or not settings.SUPABASE_SECRET_KEY.get_secret_value()
    ):
        return UnavailableAccountAuthGateway()
    from supabase import create_client

    verification_client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_PUBLISHABLE_KEY.get_secret_value(),
    )
    administration_client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SECRET_KEY.get_secret_value(),
    )
    return SupabaseAccountAuthGateway(verification_client, administration_client)


def _build_extraction_provider(settings: Settings, telemetry: ReflectionTelemetry):
    api_key = settings.OPENAI_API_KEY.get_secret_value().strip()
    if not api_key:
        return UnavailableEntryAnalysisProvider()
    return OpenAIEntryAnalysisProvider(
        build_openai_client(api_key),
        model=settings.OPENAI_ENTRY_ANALYSIS_MODEL,
        connect_timeout=settings.OPENAI_CONNECT_TIMEOUT_SECONDS,
        response_timeout=settings.OPENAI_RESPONSE_TIMEOUT_SECONDS,
        total_timeout=settings.PROCESSING_TOTAL_TIMEOUT_SECONDS,
        telemetry=telemetry,
    )


def _build_signal_embedding_provider(
    settings: Settings, telemetry: ReflectionTelemetry
):
    api_key = settings.OPENAI_API_KEY.get_secret_value().strip()
    if not api_key:
        return UnavailableSignalEmbeddingProvider()
    return OpenAISignalEmbeddingProvider(
        build_openai_client(api_key),
        model=settings.OPENAI_SIGNAL_EMBEDDING_MODEL,
        connect_timeout=settings.OPENAI_CONNECT_TIMEOUT_SECONDS,
        response_timeout=settings.OPENAI_RESPONSE_TIMEOUT_SECONDS,
        total_timeout=settings.PROCESSING_TOTAL_TIMEOUT_SECONDS,
        telemetry=telemetry,
    )


def _build_content_cipher(settings: Settings):
    try:
        return AesGcmContentCipher.from_settings(settings)
    except Exception:
        if settings.ENVIRONMENT == "production":
            raise
        return UnavailableContentCipher()


def _build_reflection_provider(settings: Settings, telemetry: ReflectionTelemetry):
    api_key = settings.OPENAI_API_KEY.get_secret_value().strip()
    if not api_key:
        return UnavailableReflectionProvider()
    return OpenAIReflectionProvider(
        build_openai_client(api_key),
        synthesis_model=settings.OPENAI_REFLECTION_SYNTHESIS_MODEL,
        critic_model=settings.OPENAI_REFLECTION_CRITIC_MODEL,
        connect_timeout=settings.OPENAI_CONNECT_TIMEOUT_SECONDS,
        response_timeout=settings.OPENAI_RESPONSE_TIMEOUT_SECONDS,
        total_timeout=settings.PROCESSING_TOTAL_TIMEOUT_SECONDS,
        telemetry=telemetry,
    )


def create_app(
    *,
    settings: Settings | None = None,
    database_sessions: DatabaseSessions | None = None,
    token_verifier=None,
    account_auth=None,
    extraction_provider=None,
    embedding_provider=None,
    reflection_provider=None,
    content_cipher=None,
    pii_redactor=None,
    transcriber=None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(json_logs=resolved_settings.LOG_FORMAT == "json")
    reflection_telemetry, meter_provider = configure_reflection_telemetry(
        resolved_settings
    )
    sessions = database_sessions or build_database_sessions(resolved_settings)
    verifier = token_verifier or _build_token_verifier(resolved_settings)
    resolved_account_auth = account_auth or _build_account_auth(resolved_settings)
    resolved_extraction_provider = extraction_provider or _build_extraction_provider(
        resolved_settings, reflection_telemetry
    )
    resolved_embedding_provider = embedding_provider or _build_signal_embedding_provider(
        resolved_settings, reflection_telemetry
    )
    resolved_reflection_provider = reflection_provider or _build_reflection_provider(
        resolved_settings, reflection_telemetry
    )
    resolved_content_cipher = content_cipher or _build_content_cipher(resolved_settings)
    if pii_redactor is None:
        initialize_offline_privacy_runtime()
        resolved_pii_redactor = PiiRedactor.from_local_model(
            cipher=resolved_content_cipher
        )
    else:
        resolved_pii_redactor = pii_redactor
    resolved_transcriber = transcriber
    if resolved_transcriber is None:
        api_key = resolved_settings.OPENAI_API_KEY.get_secret_value().strip()
        resolved_transcriber = (
            OpenAITranscriber(
                build_openai_client(api_key),
                timeout=TRANSCRIPTION_TIMEOUT_SECONDS,
            )
            if api_key
            else UnavailableTranscriber()
        )

    def check_database_readiness() -> None:
        for engine in (sessions.application_engine, sessions.worker_engine):
            if engine is not None:
                with engine.connect() as connection:
                    connection.execute(
                        text(
                            "SELECT pg_catalog.set_config("
                            "'statement_timeout', :timeout, true)"
                        ),
                        {
                            "timeout": str(
                                round(
                                    resolved_settings.STARTUP_READINESS_TIMEOUT_SECONDS
                                    * 1_000
                                )
                            )
                        },
                    )
                    connection.execute(text("SELECT 1"))

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(check_database_readiness),
                timeout=resolved_settings.STARTUP_READINESS_TIMEOUT_SECONDS,
            )
            yield
        finally:
            sessions.dispose()
            tracer_provider = getattr(_app.state, "tracer_provider", None)
            if tracer_provider is not None:
                tracer_provider.shutdown()
            current_meter_provider = getattr(_app.state, "meter_provider", None)
            if current_meter_provider is not None:
                current_meter_provider.shutdown()

    docs_enabled = (
        resolved_settings.ENVIRONMENT != "production" and resolved_settings.ENABLE_API_DOCS
    )
    app = FastAPI(
        title="Orion profile and entry API",
        version="1.5.0-profile-entry-trim",
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.reflection_telemetry = reflection_telemetry
    app.state.meter_provider = meter_provider
    app.state.database_sessions = sessions
    app.state.authentication_service = AuthenticationService(
        verifier=verifier,
        unit_of_work_factory=sessions.unit_of_work_factory,
    )
    app.state.profile_service = ProfileService(
        repository=ProfileRepository(),
        account_auth=resolved_account_auth,
    )
    app.state.processing_service = ProcessingService(
        repository=ProcessingRepository(),
        provider=resolved_extraction_provider,
        cipher=resolved_content_cipher,
        redactor=resolved_pii_redactor,
        model_id=resolved_settings.OPENAI_ENTRY_ANALYSIS_MODEL,
        reflection_threshold=resolved_settings.REFLECTION_REVIEW_THRESHOLD,
        embedding_provider=resolved_embedding_provider,
        embedding_model_id=resolved_settings.OPENAI_SIGNAL_EMBEDDING_MODEL,
        telemetry=reflection_telemetry,
    )
    app.state.reflection_engine_service = ReflectionEngineService(
        repository=ReflectionEngineRepository(),
        provider=resolved_reflection_provider,
        cipher=resolved_content_cipher,
        basis_days=resolved_settings.REFLECTION_BASIS_DAYS,
        telemetry=reflection_telemetry,
    )
    app.state.reflections_service = ReflectionsService(
        repository=ReflectionsRepository(),
        cipher=resolved_content_cipher,
        basis_days=resolved_settings.REFLECTION_BASIS_DAYS,
        enabled=resolved_settings.REFLECTION_API_ENABLED,
        allowed_user_ids=resolved_settings.reflection_rollout_user_ids(),
        telemetry=reflection_telemetry,
    )
    app.state.content_cipher = resolved_content_cipher
    app.state.entry_service = EntryService(
        repository=EntryRepository(),
        past_imports=PastImportService(repository=PastImportRepository()),
        cipher=resolved_content_cipher,
    )
    app.state.transcriber = resolved_transcriber
    app.state.rate_limiter = ProcessRateLimiter(
        enabled=resolved_settings.RATE_LIMITING_ENABLED
    )
    app.state.job_service = JobService(
        repository=JobRepository(),
        processing=app.state.processing_service,
        reflection=app.state.reflection_engine_service,
        cipher=resolved_content_cipher,
        reflection_engine_enabled=resolved_settings.REFLECTION_ENGINE_ENABLED,
        reflection_scheduler_enabled=resolved_settings.REFLECTION_SCHEDULER_ENABLED,
        reflection_rollout_mode=resolved_settings.REFLECTION_ROLLOUT_MODE,
        reflection_rollout_user_ids=resolved_settings.reflection_rollout_user_ids(),
        backfill_max_queue_depth=(
            resolved_settings.PROCESSING_BACKFILL_MAX_QUEUE_DEPTH
        ),
        backfill_max_oldest_pending_seconds=(
            resolved_settings.PROCESSING_BACKFILL_MAX_OLDEST_PENDING_SECONDS
        ),
        heartbeat_interval_seconds=(
            resolved_settings.PROCESSING_JOB_HEARTBEAT_SECONDS
        ),
        telemetry=reflection_telemetry,
    )
    app.state.processing_worker = ProcessingWorker(
        service=app.state.job_service,
        poll_seconds=resolved_settings.PROCESSING_JOB_POLL_SECONDS,
        stale_seconds=resolved_settings.PROCESSING_JOB_STALE_SECONDS,
        recovery_interval_seconds=(
            resolved_settings.PROCESSING_JOB_RECOVERY_INTERVAL_SECONDS
        ),
        scheduler_interval_seconds=(
            resolved_settings.REFLECTION_SCHEDULER_POLL_SECONDS
        ),
    )

    install_error_handlers(app)
    app.include_router(api_router)
    app.include_router(health_router)
    assert_public_contract(app)
    install_http_middleware(
        app,
        allow_origins=resolved_settings.cors_origins(),
        body_limit=resolved_settings.MAX_REQUEST_BODY_BYTES,
        request_timeout=resolved_settings.REQUEST_TIMEOUT_SECONDS,
    )
    install_local_openapi(app)
    app.state.tracer_provider = configure_tracing(
        app, settings=resolved_settings, sessions=sessions
    )
    return app
