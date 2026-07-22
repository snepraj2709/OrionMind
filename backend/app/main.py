from __future__ import annotations

from fastapi import FastAPI

from app import bootstrap as application_bootstrap
from app.contract import assert_public_contract
from app.modules.entries.audio import Transcriber
from app.modules.health.routes import router as health_router
from app.modules.processing.redaction import PiiRedactor
from app.modules.processing.types import EntryAnalysisProvider, SignalEmbeddingProvider
from app.modules.profile.types import AccountAuthGateway
from app.modules.reflection_engine.types import ReflectionProvider
from app.openapi_contract import install_local_openapi
from app.router import router as api_router
from app.shared.auth.service import TokenVerifier
from app.shared.config.settings import Settings, get_settings
from app.shared.database.session import DatabaseSessions
from app.shared.exceptions.handlers import install_error_handlers
from app.shared.http.middleware import install_http_middleware
from app.shared.observability.tracing import configure_tracing
from app.shared.security.encryption import ContentCipher


_build_content_cipher = application_bootstrap._build_content_cipher
_build_signal_embedding_provider = application_bootstrap._build_signal_embedding_provider


def create_app(
    *,
    settings: Settings | None = None,
    database_sessions: DatabaseSessions | None = None,
    token_verifier: TokenVerifier | None = None,
    account_auth: AccountAuthGateway | None = None,
    extraction_provider: EntryAnalysisProvider | None = None,
    embedding_provider: SignalEmbeddingProvider | None = None,
    reflection_provider: ReflectionProvider | None = None,
    content_cipher: ContentCipher | None = None,
    pii_redactor: PiiRedactor | None = None,
    transcriber: Transcriber | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    services = application_bootstrap.compose_application_services(
        settings=resolved_settings,
        database_sessions=database_sessions,
        token_verifier=token_verifier,
        account_auth=account_auth,
        extraction_provider=extraction_provider,
        embedding_provider=embedding_provider,
        reflection_provider=reflection_provider,
        content_cipher=content_cipher,
        pii_redactor=pii_redactor,
        transcriber=transcriber,
    )
    docs_enabled = (
        resolved_settings.ENVIRONMENT != "production"
        and resolved_settings.ENABLE_API_DOCS
    )
    app = FastAPI(
        title="Orion profile and entry API",
        version="1.5.0-profile-entry-trim",
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=application_bootstrap.build_lifespan(
            settings=resolved_settings,
            sessions=services.database_sessions,
        ),
    )
    application_bootstrap.register_application_state(app, services)

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
        app,
        settings=resolved_settings,
        sessions=services.database_sessions,
    )
    return app
