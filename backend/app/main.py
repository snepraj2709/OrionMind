from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.contract import assert_public_contract
from app.modules.health.routes import router as health_router
from app.modules.entries.repository import EntryRepository
from app.modules.entries.service import EntryService
from app.modules.entries.audio import (
    TRANSCRIPTION_TIMEOUT_SECONDS,
    OpenAITranscriber,
    UnavailableTranscriber,
)
from app.modules.profile.repository import ProfileRepository
from app.modules.profile.service import ProfileService
from app.modules.processing.provider import OpenAIExtractionProvider, UnavailableExtractionProvider
from app.modules.processing.repository import ProcessingRepository
from app.modules.processing.service import ProcessingService
from app.modules.past_imports.repository import PastImportRepository
from app.modules.past_imports.service import PastImportWorker
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


def _build_extraction_provider(settings: Settings):
    api_key = settings.OPENAI_API_KEY.get_secret_value().strip()
    if not api_key:
        return UnavailableExtractionProvider()
    return OpenAIExtractionProvider(
        build_openai_client(api_key),
        primary_model=settings.OPENAI_PRIMARY_EXTRACTION_MODEL,
        fallback_model=settings.OPENAI_FALLBACK_EXTRACTION_MODEL,
        connect_timeout=settings.OPENAI_CONNECT_TIMEOUT_SECONDS,
        response_timeout=settings.OPENAI_RESPONSE_TIMEOUT_SECONDS,
        total_timeout=settings.PROCESSING_TOTAL_TIMEOUT_SECONDS,
    )


def _build_content_cipher(settings: Settings):
    try:
        return AesGcmContentCipher.from_settings(settings)
    except Exception:
        if settings.ENVIRONMENT == "production":
            raise
        return UnavailableContentCipher()


def create_app(
    *,
    settings: Settings | None = None,
    database_sessions: DatabaseSessions | None = None,
    token_verifier=None,
    account_auth=None,
    extraction_provider=None,
    content_cipher=None,
    transcriber=None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(json_logs=resolved_settings.LOG_FORMAT == "json")
    sessions = database_sessions or build_database_sessions(resolved_settings)
    verifier = token_verifier or _build_token_verifier(resolved_settings)
    resolved_account_auth = account_auth or _build_account_auth(resolved_settings)
    resolved_extraction_provider = extraction_provider or _build_extraction_provider(
        resolved_settings
    )
    resolved_content_cipher = content_cipher or _build_content_cipher(resolved_settings)
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
            if sessions.worker is not None:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        _app.state.past_import_worker.recover_stale,
                        stale_seconds=resolved_settings.PAST_IMPORT_STALE_SECONDS,
                        uow=sessions.unit_of_work_factory,
                        statement_timeout_seconds=(
                            resolved_settings.STARTUP_READINESS_TIMEOUT_SECONDS
                        ),
                    ),
                    timeout=resolved_settings.STARTUP_READINESS_TIMEOUT_SECONDS,
                )
            yield
        finally:
            sessions.dispose()
            tracer_provider = getattr(_app.state, "tracer_provider", None)
            if tracer_provider is not None:
                tracer_provider.shutdown()

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
        reflection_threshold=resolved_settings.REFLECTION_REVIEW_THRESHOLD,
    )
    app.state.content_cipher = resolved_content_cipher
    app.state.entry_service = EntryService(
        repository=EntryRepository(),
        cipher=resolved_content_cipher,
        processing=app.state.processing_service,
    )
    app.state.transcriber = resolved_transcriber
    app.state.rate_limiter = ProcessRateLimiter(
        enabled=resolved_settings.RATE_LIMITING_ENABLED
    )
    app.state.past_import_worker = PastImportWorker(
        repository=PastImportRepository(),
        provider=resolved_extraction_provider,
        cipher=resolved_content_cipher,
        reflection_threshold=resolved_settings.REFLECTION_REVIEW_THRESHOLD,
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
