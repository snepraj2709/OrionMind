from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
import yaml
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from starlette.requests import Request

from app.contract import PUBLIC_OPERATIONS, assert_public_contract
from app.main import create_app
from app.openapi_contract import CONTRACT_PATH
from app.shared.config import Settings
from app.shared.database.session import DatabaseSessions
from app.shared.http.rate_limits import ProcessRateLimiter, RULES, request_class
from scripts.run_processing_worker import parse_args as parse_worker_args


USER_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


class Verifier:
    def verify_access_token(self, token: str) -> str:
        if token == "invalid":
            raise RuntimeError("private auth failure")
        return str(USER_ID)


def settings(**changes) -> Settings:
    values = {
        "ENVIRONMENT": "test",
        "ENABLE_API_DOCS": False,
        "CORS_ALLOW_ORIGINS": "https://app.example.test",
        "LOG_FORMAT": "text",
        "RATE_LIMITING_ENABLED": True,
        "REFLECTION_ENGINE_ENABLED": False,
        "REFLECTION_SCHEDULER_ENABLED": False,
        "REFLECTION_API_ENABLED": False,
        "REFLECTION_ROLLOUT_MODE": "off",
        "REFLECTION_ROLLOUT_USER_IDS": "",
    }
    values.update(changes)
    return Settings.model_validate(values)


def empty_sessions() -> DatabaseSessions:
    return DatabaseSessions(None, None, None, None)


def operation_inventory(document: dict) -> frozenset[tuple[str, str]]:
    methods = {"get", "post", "put", "patch", "delete"}
    return frozenset(
        (method.upper(), path)
        for path, path_item in document["paths"].items()
        for method in path_item
        if method in methods
    )


def resolve_pointer(document: dict, reference: str):
    assert reference.startswith("#/")
    value = document
    for part in reference[2:].split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    return value


def all_references(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref":
                yield item
            else:
                yield from all_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from all_references(item)


def test_packaged_openapi_is_exact_runtime_contract_with_no_dangling_references() -> None:
    artifact = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert operation_inventory(artifact) == PUBLIC_OPERATIONS
    assert set(artifact["paths"]) == {
        "/health",
        "/api/v1/profile",
        "/api/v1/account",
        "/api/v1/entries",
        "/api/v1/entry/draft",
        "/api/v1/entry",
        "/api/v1/past-entries",
        "/api/v1/entries/voice",
        "/api/v1/entries/{entry_id}",
        "/api/v1/entries/{entry_id}/retry",
        "/api/v1/reflections",
        "/api/v1/reflections/{snapshot_id}/insights/{insight_id}/feedback",
    }
    references = tuple(all_references(artifact))
    assert references
    assert all(resolve_pointer(artifact, reference) is not None for reference in references)

    app = create_app(
        settings=settings(ENABLE_API_DOCS=True),
        database_sessions=empty_sessions(),
        token_verifier=Verifier(),
    )
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json() == artifact
    assert app.openapi() == artifact


def test_route_drift_assertion_rejects_any_unreviewed_public_operation() -> None:
    app = create_app(
        settings=settings(RATE_LIMITING_ENABLED=False),
        database_sessions=empty_sessions(),
        token_verifier=Verifier(),
    )
    router = APIRouter()

    @router.get("/api/v1/unreviewed")
    def unreviewed():
        return {"unexpected": True}

    app.include_router(router)
    with pytest.raises(RuntimeError, match="public route contract drift"):
        assert_public_contract(app)


@pytest.mark.parametrize("rule", sorted(RULES))
def test_every_endpoint_class_has_integer_retry_after_at_its_limit(rule: str) -> None:
    limiter = ProcessRateLimiter()
    first = RULES[rule][0]
    for _ in range(first.requests):
        assert limiter.check(rule, "scope", now=100.0) is None
    retry_after = limiter.check(rule, "scope", now=100.1)
    assert isinstance(retry_after, int)
    assert retry_after == first.seconds


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", "/health", "health"),
        ("GET", "/api/v1/profile", "read"),
        ("PATCH", "/api/v1/profile", "profile_write"),
        ("DELETE", "/api/v1/account", "account_delete"),
        ("GET", "/api/v1/entries", "read"),
        ("GET", "/api/v1/entry/draft", "read"),
        ("PUT", "/api/v1/entry/draft", "draft_write"),
        ("DELETE", "/api/v1/entry/draft", "draft_write"),
        ("POST", "/api/v1/entry", "text_create"),
        ("POST", "/api/v1/past-entries", "past_entry_create"),
        ("POST", "/api/v1/entries/voice", "voice_create"),
        ("GET", "/api/v1/entries/entry-id", "read"),
        ("POST", "/api/v1/entries/entry-id/retry", "entry_retry"),
        ("GET", "/api/v1/reflections", "read"),
        (
            "PUT",
            "/api/v1/reflections/snapshot-id/insights/insight-id/feedback",
            "reflection_write",
        ),
    ],
)
def test_exact_operation_rate_classification(method: str, path: str, expected: str) -> None:
    request = Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "scheme": "http",
            "server": ("test", 80),
        }
    )
    request.state.auth_context = SimpleNamespace(user_id=USER_ID)
    assert request_class(request) == (expected, str(USER_ID))


def test_rate_limit_runs_after_auth_and_before_voice_body_parsing() -> None:
    app = create_app(
        settings=settings(), database_sessions=empty_sessions(), token_verifier=Verifier()
    )
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/entries/voice",
            headers={"Authorization": "Bearer valid"},
            content=b"private body is not multipart",
        )
        limited = client.post(
            "/api/v1/entries/voice",
            headers={"Authorization": "Bearer valid"},
            content=b"must not be parsed",
        )
        unauthenticated = client.post(
            "/api/v1/entries/voice",
            headers={"Authorization": "Bearer invalid"},
            content=b"must not be parsed",
        )
    assert first.status_code == 422
    assert limited.status_code == 429
    assert limited.json()["error_code"] == "RATE_LIMITED"
    assert limited.headers["retry-after"].isdigit()
    assert unauthenticated.status_code == 401


def test_health_rate_limit_preserves_opaque_liveness_contract() -> None:
    app = create_app(
        settings=settings(), database_sessions=empty_sessions(), token_verifier=Verifier()
    )
    with TestClient(app) as client:
        responses = [client.get("/health") for _ in range(61)]
    assert all(response.json() == {"status": "ok"} for response in responses[:60])
    assert responses[-1].status_code == 429
    assert responses[-1].headers["retry-after"].isdigit()
    assert "database" not in responses[0].text


def test_bounded_startup_readiness_runs_without_exposing_dependency_details() -> None:
    class Connection:
        def __init__(self, engine):
            self.engine = engine

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _parameters=None):
            if str(statement) == "SELECT 1":
                self.engine.checked += 1
            else:
                assert "statement_timeout" in str(statement)

    class Engine:
        checked = 0
        disposed = False

        def connect(self):
            return Connection(self)

        def dispose(self):
            self.disposed = True

    engine = Engine()
    sessions = DatabaseSessions(engine, None, None, None)  # type: ignore[arg-type]
    app = create_app(
        settings=settings(RATE_LIMITING_ENABLED=False),
        database_sessions=sessions,
        token_verifier=Verifier(),
    )
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
    assert engine.checked == 1
    assert engine.disposed is True


def test_startup_readiness_timeout_is_bounded() -> None:
    class SlowConnection:
        def __enter__(self):
            time.sleep(0.1)
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _statement):
            return None

    class SlowEngine:
        def connect(self):
            return SlowConnection()

        def dispose(self):
            return None

    app = create_app(
        settings=settings(
            RATE_LIMITING_ENABLED=False,
            STARTUP_READINESS_TIMEOUT_SECONDS=0.01,
        ),
        database_sessions=DatabaseSessions(SlowEngine(), None, None, None),  # type: ignore[arg-type]
        token_verifier=Verifier(),
    )
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        with TestClient(app):
            pass
    assert time.monotonic() - started < 0.5


def test_production_cannot_disable_limits_or_scale_in_process_limiter() -> None:
    key_map = '{"key":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}'
    production_values = {
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

    with pytest.raises(ValidationError, match="rate limiting must be enabled"):
        Settings.model_validate(
            {
                "ENVIRONMENT": "production",
                **production_values,
                "RATE_LIMITING_ENABLED": False,
            }
        )
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "ENVIRONMENT": "production",
                **production_values,
                "WEB_CONCURRENCY": 2,
            }
        )


def test_openapi_artifact_is_packaged_under_the_repository() -> None:
    assert CONTRACT_PATH == Path(__file__).resolve().parents[1] / "docs/contracts/profile-entry-v1.openapi.json"
    assert CONTRACT_PATH.is_file()


def test_json_yaml_and_runtime_reflection_contracts_are_equivalent() -> None:
    artifact = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    yaml_path = CONTRACT_PATH.with_suffix(".yaml")
    assert yaml.safe_load(yaml_path.read_text(encoding="utf-8")) == artifact
    reflection_paths = {
        path: value
        for path, value in artifact["paths"].items()
        if path.startswith("/api/v1/reflections")
    }
    assert set(reflection_paths) == {
        "/api/v1/reflections",
        "/api/v1/reflections/{snapshot_id}/insights/{insight_id}/feedback",
    }
    assert reflection_paths["/api/v1/reflections"]["get"]["parameters"][0][
        "schema"
    ] == {"$ref": "#/components/schemas/ReflectionRange"}
    assert artifact["components"]["schemas"]["ReflectionRange"]["enum"] == [
        "7d",
        "30d",
        "all",
    ]


def test_shared_processing_worker_is_the_only_operational_entrypoint() -> None:
    root = Path(__file__).resolve().parents[1]
    retired_worker = "run_" + "past_import" + "_worker.py"
    assert (root / "scripts/run_processing_worker.py").is_file()
    assert not (root / f"scripts/{retired_worker}").exists()
    for path in (root / "README.md", root / "docs/DEPLOYMENT.md"):
        content = path.read_text(encoding="utf-8")
        assert "run_processing_worker.py" in content
        assert retired_worker not in content
    configured = settings()
    assert configured.PROCESSING_JOB_POLL_SECONDS == 1
    assert configured.PROCESSING_JOB_HEARTBEAT_SECONDS == 30
    assert configured.PROCESSING_JOB_STALE_SECONDS == 300
    assert configured.PROCESSING_JOB_RECOVERY_INTERVAL_SECONDS == 60

    app = create_app(
        settings=configured,
        database_sessions=empty_sessions(),
        token_verifier=Verifier(),
    )
    assert app.state.reflections_service._enabled is False
    assert app.state.job_service._processing is app.state.processing_service
    assert app.state.processing_worker._service is app.state.job_service
    assert ("POST", "/api/v1/entry") in PUBLIC_OPERATIONS


def test_reflection_release_flags_default_off_and_require_the_engine() -> None:
    configured = settings()
    assert configured.REFLECTION_ENGINE_ENABLED is False
    assert configured.REFLECTION_SCHEDULER_ENABLED is False
    assert configured.REFLECTION_API_ENABLED is False
    assert configured.REFLECTION_ROLLOUT_MODE == "off"
    assert configured.reflection_rollout_user_ids() == frozenset()

    with pytest.raises(
        ValidationError, match="reflection scheduler requires the reflection engine"
    ):
        settings(REFLECTION_SCHEDULER_ENABLED=True)

    with pytest.raises(
        ValidationError, match="reflection API requires the reflection engine"
    ):
        settings(REFLECTION_API_ENABLED=True)

    with pytest.raises(
        ValidationError, match="reflection scheduler requires an active rollout mode"
    ):
        settings(
            REFLECTION_ENGINE_ENABLED=True,
            REFLECTION_SCHEDULER_ENABLED=True,
        )

    with pytest.raises(
        ValidationError, match="active reflection rollout requires a non-empty cohort"
    ):
        settings(
            REFLECTION_ENGINE_ENABLED=True,
            REFLECTION_ROLLOUT_MODE="shadow",
        )

    enabled = settings(
        REFLECTION_ENGINE_ENABLED=True,
        REFLECTION_SCHEDULER_ENABLED=True,
        REFLECTION_API_ENABLED=True,
        REFLECTION_ROLLOUT_MODE="publish",
        REFLECTION_ROLLOUT_USER_IDS=str(USER_ID),
    )
    assert enabled.REFLECTION_SCHEDULER_ENABLED is True
    assert enabled.REFLECTION_API_ENABLED is True


def test_processing_worker_backfill_cli_is_persisted_and_resumable() -> None:
    planned = parse_worker_args(["--backfill-plan", "--backfill-batch-size", "25"])
    assert planned.backfill_plan is True
    assert planned.backfill_batch_size == 25
    run_id = UUID("bccccccc-cccc-4ccc-8ccc-cccccccccccc")
    for action in ("status", "batch", "pause", "resume"):
        parsed = parse_worker_args(
            [
                "--backfill-action",
                action,
                "--backfill-run-id",
                str(run_id),
            ]
        )
        assert parsed.backfill_action == action
        assert parsed.backfill_run_id == run_id
    with pytest.raises(SystemExit):
        parse_worker_args(["--backfill-action", "batch"])
    with pytest.raises(SystemExit):
        parse_worker_args(["--backfill-batch", "25"])
