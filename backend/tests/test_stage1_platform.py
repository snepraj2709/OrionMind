from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from uuid import UUID

import pytest
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from app.main import create_app
from app.shared.auth import AuthContext, get_auth_context
from app.shared.config import Settings
from app.shared.database.session import DatabaseSessions
from app.shared.database.unit_of_work import SqlAlchemyUnitOfWork
from app.shared.exceptions.domain import DomainError
from app.shared.http.protected_route import ProtectedAPIRoute


USER_ID = "11111111-1111-4111-8111-111111111111"


class ValidVerifier:
    def __init__(self, user_id: str = USER_ID) -> None:
        self.user_id = user_id
        self.tokens: list[str] = []

    def verify_access_token(self, access_token: str) -> str:
        self.tokens.append(access_token)
        if access_token in {"invalid", "expired"}:
            raise RuntimeError("provider detail must stay private")
        return self.user_id


def settings(**changes) -> Settings:
    values = {
        "ENVIRONMENT": "test",
        "ENABLE_API_DOCS": False,
        "CORS_ALLOW_ORIGINS": "https://app.example.test",
        "REQUEST_TIMEOUT_SECONDS": 1,
        "MAX_REQUEST_BODY_BYTES": 1024,
        "LOG_FORMAT": "text",
    }
    values.update(changes)
    return Settings.model_validate(values)


def empty_sessions() -> DatabaseSessions:
    return DatabaseSessions(None, None, None, None)


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


def app_with_test_routes(*, verifier=None, app_settings=None):
    app = create_app(
        settings=app_settings or settings(),
        database_sessions=empty_sessions(),
        token_verifier=verifier or ValidVerifier(),
    )
    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(get_auth_context)],
        route_class=ProtectedAPIRoute,
    )

    @router.post("/probe")
    async def probe(payload: Payload, auth: AuthContext = Depends(get_auth_context)):
        return {"value": payload.value, "user_id": str(auth.user_id)}

    @router.delete("/probe")
    async def delete_probe():
        return {"deleted": True}

    @router.post("/upload")
    async def upload_probe(audio: UploadFile = File(...)):
        return {"size": len(await audio.read())}

    @router.post("/entries/voice")
    async def voice_limit_probe(request: Request):
        return {"size": len(await request.body())}

    @router.get("/retry")
    async def retry_probe():
        raise DomainError(
            status_code=503,
            error_code="SERVICE_UNAVAILABLE",
            message="The service is temporarily unavailable.",
            headers={"Retry-After": "17"},
        )

    @router.get("/slow")
    async def slow_probe():
        await asyncio.sleep(0.2)
        return {"ok": True}

    @router.get("/explode")
    async def explode_probe():
        raise RuntimeError("secret provider payload")

    app.include_router(router)
    return app


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error_code", "message", "details", "request_id"}
    assert body["error_code"] == code
    assert body["request_id"].startswith("req-")
    assert response.headers["x-request-id"] == body["request_id"]
    return body


def test_health_is_exact_and_only_registered_operation_at_stage_one() -> None:
    app = create_app(
        settings=settings(), database_sessions=empty_sessions(), token_verifier=ValidVerifier()
    )
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    operations = [
        (method, route.path)
        for route in app.routes
        for method in sorted(route.methods or ())
        if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    ]
    assert operations == [("GET", "/health")]


@pytest.mark.parametrize(
    "path",
    ["/", "/docs", "/redoc", "/openapi.json", "/api/health", "/api/auth/login"],
)
def test_production_does_not_publish_root_docs_schema_or_legacy_routes(path: str) -> None:
    app = create_app(
        settings=settings(ENVIRONMENT="production", **production_values()),
        database_sessions=empty_sessions(),
        token_verifier=ValidVerifier(),
    )
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 404
    assert_error(response, 404, "NOT_FOUND")


def test_local_docs_include_supabase_bearer_scheme() -> None:
    app = app_with_test_routes(app_settings=settings(ENABLE_API_DOCS=True))
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["bearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "Supabase JWT",
        "description": "Supabase access token; never a service-role key.",
    }


@pytest.mark.parametrize(
    ("authorization", "verifier"),
    [
        (None, ValidVerifier()),
        ("Basic abc", ValidVerifier()),
        ("Bearer", ValidVerifier()),
        ("Bearer invalid", ValidVerifier()),
        ("Bearer expired", ValidVerifier()),
        ("Bearer good", ValidVerifier("not-a-uuid")),
    ],
)
def test_missing_malformed_invalid_expired_and_non_uuid_bearers_are_canonical(
    authorization, verifier
) -> None:
    app = app_with_test_routes(verifier=verifier)
    headers = {"Authorization": authorization} if authorization else {}
    with TestClient(app) as client:
        response = client.post("/api/v1/probe", headers=headers, json={"value": "safe"})
    body = assert_error(response, 401, "UNAUTHORIZED")
    assert body["message"] == "Authentication is required."
    assert "provider" not in response.text


def test_verified_uuid_is_the_only_auth_context_identity() -> None:
    app = app_with_test_routes()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/probe",
            headers={"Authorization": "Bearer good"},
            json={"value": "accepted"},
        )
    assert response.status_code == 200
    assert response.json() == {"value": "accepted", "user_id": USER_ID}


def test_authentication_precedes_malformed_json_and_multipart_parsing() -> None:
    app = app_with_test_routes()
    with TestClient(app) as client:
        json_response = client.post(
            "/api/v1/probe",
            content=b'{"value":',
            headers={"Content-Type": "application/json"},
        )
        multipart_response = client.post(
            "/api/v1/upload",
            content=b"not-a-multipart-body",
            headers={"Content-Type": "multipart/form-data; boundary=broken"},
        )
    assert_error(json_response, 401, "UNAUTHORIZED")
    assert_error(multipart_response, 401, "UNAUTHORIZED")


def test_validation_and_unexpected_errors_are_sanitized() -> None:
    app = app_with_test_routes()
    with TestClient(app, raise_server_exceptions=False) as client:
        validation = client.post(
            "/api/v1/probe",
            headers={"Authorization": "Bearer good"},
            json={"extra": "forbidden"},
        )
        unexpected = client.get(
            "/api/v1/explode", headers={"Authorization": "Bearer good"}
        )
    validation_body = assert_error(validation, 422, "VALIDATION_ERROR")
    assert "input" not in validation_body["details"]["fields"][0]
    assert_error(unexpected, 500, "INTERNAL_ERROR")
    assert "secret provider payload" not in unexpected.text


def test_retry_after_header_is_preserved() -> None:
    app = app_with_test_routes()
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/retry", headers={"Authorization": "Bearer good"}
        )
    assert_error(response, 503, "SERVICE_UNAVAILABLE")
    assert response.headers["retry-after"] == "17"


def test_cors_allows_delete_preflight_and_rejects_unknown_origins_safely() -> None:
    app = app_with_test_routes()
    with TestClient(app) as client:
        allowed = client.options(
            "/api/v1/probe",
            headers={
                "Origin": "https://app.example.test",
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        rejected = client.options(
            "/api/v1/probe",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "DELETE",
            },
        )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://app.example.test"
    assert "DELETE" in allowed.headers["access-control-allow-methods"]
    assert_error(rejected, 403, "CORS_ORIGIN_DENIED")
    assert "access-control-allow-origin" not in rejected.headers


def test_body_limit_and_timeout_are_canonical() -> None:
    app = app_with_test_routes(
        app_settings=settings(MAX_REQUEST_BODY_BYTES=1024, REQUEST_TIMEOUT_SECONDS=0.05)
    )
    with TestClient(app) as client:
        oversized = client.post(
            "/api/v1/probe",
            headers={"Authorization": "Bearer good"},
            content=b"x" * 1025,
        )
        timed_out = client.get(
            "/api/v1/slow", headers={"Authorization": "Bearer good"}
        )
        voice_owned_limit = client.post(
            "/api/v1/entries/voice",
            headers={"Authorization": "Bearer good"},
            content=b"x" * 2048,
        )
    assert_error(oversized, 413, "PAYLOAD_TOO_LARGE")
    assert_error(timed_out, 503, "REQUEST_TIMEOUT")
    assert timed_out.headers["retry-after"] == "1"
    assert voice_owned_limit.status_code == 200
    assert voice_owned_limit.json() == {"size": 2048}


def production_values() -> dict:
    key_map = '{"key":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}'
    return {
        "ENABLE_API_DOCS": False,
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": SecretStr("publishable"),
        "SUPABASE_SECRET_KEY": SecretStr("secret"),
        "APP_DATABASE_URL": SecretStr("postgresql+psycopg://app:x@db/app"),
        "WORKER_DATABASE_URL": SecretStr("postgresql+psycopg://worker:x@db/app"),
        "OPENAI_API_KEY": SecretStr("openai"),
        "ENTRY_ENCRYPTION_ACTIVE_KEY_ID": "key",
        "ENTRY_ENCRYPTION_KEYS": SecretStr(key_map),
        "ENTRY_FINGERPRINT_ACTIVE_KEY_ID": "key",
        "ENTRY_FINGERPRINT_KEYS": SecretStr(key_map),
        "CORS_ALLOW_ORIGINS": "https://app.example.test",
        "LOG_FORMAT": "json",
        "REFLECTION_REVIEW_THRESHOLD": 0.80,
    }


def test_production_settings_fail_closed_and_secrets_are_masked() -> None:
    with pytest.raises(ValidationError, match="missing or invalid production settings"):
        Settings.model_validate({"ENVIRONMENT": "production"})
    with pytest.raises(ValidationError, match="API docs must be disabled"):
        Settings.model_validate(
            {"ENVIRONMENT": "production", **production_values(), "ENABLE_API_DOCS": True}
        )
    with pytest.raises(ValidationError, match="HTTPS origins"):
        Settings.model_validate(
            {
                "ENVIRONMENT": "production",
                **production_values(),
                "CORS_ALLOW_ORIGINS": "http://app.example.test",
            }
        )
    with pytest.raises(ValidationError, match="SUPABASE_URL must be HTTPS"):
        Settings.model_validate(
            {
                "ENVIRONMENT": "production",
                **production_values(),
                "SUPABASE_URL": "http://project.supabase.co",
            }
        )
    with pytest.raises(ValidationError, match=r"postgresql\+psycopg"):
        Settings.model_validate(
            {
                "ENVIRONMENT": "production",
                **production_values(),
                "APP_DATABASE_URL": SecretStr("postgresql://app:x@db/app"),
            }
        )
    with pytest.raises(ValidationError, match="distinct roles"):
        shared_database_url = SecretStr("postgresql+psycopg://app:x@db/app")
        Settings.model_validate(
            {
                "ENVIRONMENT": "production",
                **production_values(),
                "APP_DATABASE_URL": shared_database_url,
                "WORKER_DATABASE_URL": shared_database_url,
            }
        )
    with pytest.raises(ValidationError, match="missing or invalid production settings"):
        Settings.model_validate(
            {
                "ENVIRONMENT": "production",
                **production_values(),
                "ENTRY_ENCRYPTION_KEYS": SecretStr('{"key":"not-base64"}'),
            }
        )
    configured = Settings.model_validate({"ENVIRONMENT": "production", **production_values()})
    rendered = repr(configured)
    assert "postgresql+psycopg" not in rendered
    assert "openai" not in rendered
    assert "secret" not in rendered


@dataclass
class FakeTransaction:
    exits: list[type[BaseException] | None]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, _exc, _traceback):
        self.exits.append(exc_type)
        return False


class FakeSession:
    def __init__(self) -> None:
        self.executions: list[tuple[str, object]] = []
        self.exits: list[type[BaseException] | None] = []
        self.closed = False

    def begin(self):
        return FakeTransaction(self.exits)

    def execute(self, statement, parameters=None):
        self.executions.append((str(statement), parameters))

    def close(self):
        self.closed = True


def test_user_uow_installs_transaction_local_claims_and_commits_or_rolls_back() -> None:
    committed = FakeSession()
    with SqlAlchemyUnitOfWork(lambda: committed, user_id=UUID(USER_ID)):
        pass
    assert committed.exits == [None]
    assert committed.closed
    assert committed.executions[0][0] == "SET LOCAL ROLE authenticated"
    assert "set_config('request.jwt.claims'" in committed.executions[1][0]
    assert USER_ID in committed.executions[1][1]["claims"]

    rolled_back = FakeSession()
    with pytest.raises(RuntimeError, match="rollback"):
        with SqlAlchemyUnitOfWork(lambda: rolled_back, user_id=UUID(USER_ID)):
            raise RuntimeError("rollback")
    assert rolled_back.exits == [RuntimeError]
    assert rolled_back.closed


def test_worker_uow_uses_restricted_role() -> None:
    worker = FakeSession()
    with SqlAlchemyUnitOfWork(lambda: worker, worker=True):
        pass
    assert worker.executions == [("SET LOCAL ROLE orion_worker", None)]


def test_request_logs_do_not_emit_bearer_or_payload() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    http_logger = logging.getLogger("orion.http")
    http_logger.addHandler(handler)
    try:
        app = app_with_test_routes()
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/probe",
                headers={"Authorization": "Bearer extremely-secret-token"},
                json={"value": "private-journal-text"},
            )
        assert response.status_code == 200
    finally:
        http_logger.removeHandler(handler)
    captured = stream.getvalue()
    assert "extremely-secret-token" not in captured
    assert "private-journal-text" not in captured


def test_unexpected_exception_text_is_not_logged() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    error_logger = logging.getLogger("orion.errors")
    error_logger.addHandler(handler)
    try:
        app = app_with_test_routes()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/api/v1/explode", headers={"Authorization": "Bearer good"}
            )
        assert response.status_code == 500
    finally:
        error_logger.removeHandler(handler)
    assert "secret provider payload" not in stream.getvalue()
