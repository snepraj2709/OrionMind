from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from opentelemetry.sdk.metrics import MeterProvider
from sqlalchemy import text

from app.modules.entries.audio import (
    TRANSCRIPTION_TIMEOUT_SECONDS,
    OpenAITranscriber,
    Transcriber,
    UnavailableTranscriber,
)
from app.modules.entries.repository import EntryRepository
from app.modules.entries.service import EntryService
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.service import JobService
from app.modules.jobs.worker import ProcessingWorker
from app.modules.past_imports.repository import PastImportRepository
from app.modules.past_imports.service import PastImportService
from app.modules.processing.embeddings import (
    OpenAISignalEmbeddingProvider,
    UnavailableSignalEmbeddingProvider,
)
from app.modules.processing.provider import (
    OpenAIEntryAnalysisProvider,
    UnavailableEntryAnalysisProvider,
)
from app.modules.processing.redaction import (
    PiiRedactor,
    initialize_offline_privacy_runtime,
)
from app.modules.processing.repository import ProcessingRepository
from app.modules.processing.service import ProcessingService
from app.modules.processing.types import EntryAnalysisProvider, SignalEmbeddingProvider
from app.modules.profile.repository import ProfileRepository
from app.modules.profile.service import ProfileService
from app.modules.profile.types import AccountAuthGateway
from app.modules.reflection_engine.provider import (
    OpenAIReflectionProvider,
    UnavailableReflectionProvider,
)
from app.modules.reflection_engine.repository import ReflectionEngineRepository
from app.modules.reflection_engine.service import ReflectionEngineService
from app.modules.reflection_engine.types import ReflectionProvider
from app.modules.reflections.repository import ReflectionsRepository
from app.modules.reflections.service import ReflectionsService
from app.modules.review.repository import ReviewRepository
from app.modules.review.service import ReviewService
from app.shared.auth.service import AuthenticationService, TokenVerifier
from app.shared.config.settings import Settings
from app.shared.database.session import DatabaseSessions, build_database_sessions
from app.shared.http.rate_limits import ProcessRateLimiter
from app.shared.integrations.openai import build_openai_client
from app.shared.integrations.supabase_auth import (
    SupabaseAccountAuthGateway,
    SupabaseTokenVerifier,
    UnavailableAccountAuthGateway,
    UnavailableTokenVerifier,
)
from app.shared.observability.logging import configure_logging
from app.shared.observability.reflection import (
    ReflectionTelemetry,
    configure_reflection_telemetry,
)
from app.shared.security.encryption import (
    AesGcmContentCipher,
    ContentCipher,
    UnavailableContentCipher,
)


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    settings: Settings
    reflection_telemetry: ReflectionTelemetry
    meter_provider: MeterProvider | None
    database_sessions: DatabaseSessions
    authentication_service: AuthenticationService
    profile_service: ProfileService
    processing_service: ProcessingService
    reflection_engine_service: ReflectionEngineService
    reflections_service: ReflectionsService
    review_service: ReviewService
    content_cipher: ContentCipher
    entry_service: EntryService
    transcriber: Transcriber
    rate_limiter: ProcessRateLimiter
    job_service: JobService
    processing_worker: ProcessingWorker


def _build_token_verifier(settings: Settings) -> TokenVerifier:
    if not settings.SUPABASE_URL.strip() or not settings.SUPABASE_PUBLISHABLE_KEY.get_secret_value():
        return UnavailableTokenVerifier()
    from supabase import create_client

    client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_PUBLISHABLE_KEY.get_secret_value(),
    )
    return SupabaseTokenVerifier(client)


def _build_account_auth(settings: Settings) -> AccountAuthGateway:
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


def _build_extraction_provider(
    settings: Settings,
    telemetry: ReflectionTelemetry,
) -> EntryAnalysisProvider:
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
    settings: Settings,
    telemetry: ReflectionTelemetry,
) -> SignalEmbeddingProvider:
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


def _build_content_cipher(settings: Settings) -> ContentCipher:
    try:
        return AesGcmContentCipher.from_settings(settings)
    except Exception:
        if settings.ENVIRONMENT == "production":
            raise
        return UnavailableContentCipher()


def _build_reflection_provider(
    settings: Settings,
    telemetry: ReflectionTelemetry,
) -> ReflectionProvider:
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


def compose_application_services(
    *,
    settings: Settings,
    database_sessions: DatabaseSessions | None = None,
    token_verifier: TokenVerifier | None = None,
    account_auth: AccountAuthGateway | None = None,
    extraction_provider: EntryAnalysisProvider | None = None,
    embedding_provider: SignalEmbeddingProvider | None = None,
    reflection_provider: ReflectionProvider | None = None,
    content_cipher: ContentCipher | None = None,
    pii_redactor: PiiRedactor | None = None,
    transcriber: Transcriber | None = None,
) -> ApplicationServices:
    configure_logging(json_logs=settings.LOG_FORMAT == "json")
    reflection_telemetry, meter_provider = configure_reflection_telemetry(settings)
    sessions = database_sessions or build_database_sessions(settings)
    verifier = token_verifier or _build_token_verifier(settings)
    resolved_account_auth = account_auth or _build_account_auth(settings)
    resolved_extraction_provider = extraction_provider or _build_extraction_provider(
        settings, reflection_telemetry
    )
    resolved_embedding_provider = embedding_provider or _build_signal_embedding_provider(
        settings, reflection_telemetry
    )
    resolved_reflection_provider = reflection_provider or _build_reflection_provider(
        settings, reflection_telemetry
    )
    resolved_content_cipher = content_cipher or _build_content_cipher(settings)
    if pii_redactor is None:
        initialize_offline_privacy_runtime()
        resolved_pii_redactor = PiiRedactor.from_local_model(
            cipher=resolved_content_cipher
        )
    else:
        resolved_pii_redactor = pii_redactor
    resolved_transcriber = transcriber
    if resolved_transcriber is None:
        api_key = settings.OPENAI_API_KEY.get_secret_value().strip()
        resolved_transcriber = (
            OpenAITranscriber(
                build_openai_client(api_key),
                timeout=TRANSCRIPTION_TIMEOUT_SECONDS,
            )
            if api_key
            else UnavailableTranscriber()
        )

    processing_service = ProcessingService(
        repository=ProcessingRepository(),
        provider=resolved_extraction_provider,
        cipher=resolved_content_cipher,
        redactor=resolved_pii_redactor,
        model_id=settings.OPENAI_ENTRY_ANALYSIS_MODEL,
        reflection_threshold=settings.REFLECTION_REVIEW_THRESHOLD,
        embedding_provider=resolved_embedding_provider,
        embedding_model_id=settings.OPENAI_SIGNAL_EMBEDDING_MODEL,
        telemetry=reflection_telemetry,
    )
    reflection_engine_service = ReflectionEngineService(
        repository=ReflectionEngineRepository(),
        provider=resolved_reflection_provider,
        cipher=resolved_content_cipher,
        basis_days=settings.REFLECTION_BASIS_DAYS,
        embedding_model_id=settings.OPENAI_SIGNAL_EMBEDDING_MODEL,
        synthesis_model_id=settings.OPENAI_REFLECTION_SYNTHESIS_MODEL,
        telemetry=reflection_telemetry,
    )
    job_service = JobService(
        repository=JobRepository(),
        processing=processing_service,
        reflection=reflection_engine_service,
        cipher=resolved_content_cipher,
        reflection_engine_enabled=settings.REFLECTION_ENGINE_ENABLED,
        reflection_scheduler_enabled=settings.REFLECTION_SCHEDULER_ENABLED,
        reflection_rollout_mode=settings.REFLECTION_ROLLOUT_MODE,
        reflection_rollout_user_ids=settings.reflection_rollout_user_ids(),
        backfill_max_queue_depth=settings.PROCESSING_BACKFILL_MAX_QUEUE_DEPTH,
        backfill_max_oldest_pending_seconds=(
            settings.PROCESSING_BACKFILL_MAX_OLDEST_PENDING_SECONDS
        ),
        heartbeat_interval_seconds=settings.PROCESSING_JOB_HEARTBEAT_SECONDS,
        telemetry=reflection_telemetry,
    )
    reflections_repository = ReflectionsRepository()
    review_service = ReviewService(
        repository=ReviewRepository(cipher=resolved_content_cipher),
        recalculation_repository=reflections_repository,
        enabled=settings.REFLECTION_API_ENABLED,
        allowed_user_ids=settings.reflection_rollout_user_ids(),
        telemetry=reflection_telemetry,
    )
    reflections_service = ReflectionsService(
        repository=reflections_repository,
        review_service=review_service,
        cipher=resolved_content_cipher,
        basis_days=settings.REFLECTION_BASIS_DAYS,
        enabled=settings.REFLECTION_API_ENABLED,
        recalculation_enabled=(
            settings.REFLECTION_ENGINE_ENABLED
            and settings.REFLECTION_ROLLOUT_MODE == "publish"
        ),
        allowed_user_ids=settings.reflection_rollout_user_ids(),
        telemetry=reflection_telemetry,
    )
    return ApplicationServices(
        settings=settings,
        reflection_telemetry=reflection_telemetry,
        meter_provider=meter_provider,
        database_sessions=sessions,
        authentication_service=AuthenticationService(
            verifier=verifier,
            unit_of_work_factory=sessions.unit_of_work_factory,
        ),
        profile_service=ProfileService(
            repository=ProfileRepository(),
            account_auth=resolved_account_auth,
        ),
        processing_service=processing_service,
        reflection_engine_service=reflection_engine_service,
        reflections_service=reflections_service,
        review_service=review_service,
        content_cipher=resolved_content_cipher,
        entry_service=EntryService(
            repository=EntryRepository(),
            past_imports=PastImportService(repository=PastImportRepository()),
            cipher=resolved_content_cipher,
        ),
        transcriber=resolved_transcriber,
        rate_limiter=ProcessRateLimiter(enabled=settings.RATE_LIMITING_ENABLED),
        job_service=job_service,
        processing_worker=ProcessingWorker(
            service=job_service,
            poll_seconds=settings.PROCESSING_JOB_POLL_SECONDS,
            stale_seconds=settings.PROCESSING_JOB_STALE_SECONDS,
            recovery_interval_seconds=settings.PROCESSING_JOB_RECOVERY_INTERVAL_SECONDS,
            scheduler_interval_seconds=settings.REFLECTION_SCHEDULER_POLL_SECONDS,
        ),
    )


def register_application_state(app: FastAPI, services: ApplicationServices) -> None:
    app.state.settings = services.settings
    app.state.reflection_telemetry = services.reflection_telemetry
    app.state.meter_provider = services.meter_provider
    app.state.database_sessions = services.database_sessions
    app.state.authentication_service = services.authentication_service
    app.state.profile_service = services.profile_service
    app.state.processing_service = services.processing_service
    app.state.reflection_engine_service = services.reflection_engine_service
    app.state.reflections_service = services.reflections_service
    app.state.review_service = services.review_service
    app.state.content_cipher = services.content_cipher
    app.state.entry_service = services.entry_service
    app.state.transcriber = services.transcriber
    app.state.rate_limiter = services.rate_limiter
    app.state.job_service = services.job_service
    app.state.processing_worker = services.processing_worker


def check_database_readiness(
    settings: Settings,
    sessions: DatabaseSessions,
) -> None:
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
                            round(settings.STARTUP_READINESS_TIMEOUT_SECONDS * 1_000)
                        )
                    },
                )
                connection.execute(text("SELECT 1"))


def build_lifespan(
    *,
    settings: Settings,
    sessions: DatabaseSessions,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(check_database_readiness, settings, sessions),
                timeout=settings.STARTUP_READINESS_TIMEOUT_SECONDS,
            )
            yield
        finally:
            sessions.dispose()
            tracer_provider = getattr(app.state, "tracer_provider", None)
            if tracer_provider is not None:
                tracer_provider.shutdown()
            meter_provider = getattr(app.state, "meter_provider", None)
            if meter_provider is not None:
                meter_provider.shutdown()

    return lifespan
