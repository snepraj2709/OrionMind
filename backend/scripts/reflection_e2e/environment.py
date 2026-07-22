from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.engine.base import Connection, Engine
from sqlalchemy.exc import ArgumentError

from app.modules.reflection_engine.preflight import (
    ModelAccessTarget,
    check_reflection_model_access,
)
from app.shared.config.settings import Settings
from app.shared.database.session import build_database_sessions
from app.shared.integrations.openai import build_openai_client
from scripts.reflection_e2e.reporting import MODEL_ROLES
from scripts.reflection_e2e.types import LiveRunError, SampleEntry


def load_sample_entries(path: Path) -> tuple[list[SampleEntry], str]:
    try:
        raw = path.read_bytes()
        decoded = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveRunError("INVALID_DATASET", "The sample dataset is invalid.") from exc
    if not isinstance(decoded, list) or not decoded:
        raise LiveRunError("INVALID_DATASET", "The sample dataset must be a list.")
    entries: list[SampleEntry] = []
    seen_dates: set[date] = set()
    for item in decoded:
        if not isinstance(item, dict) or set(item) != {"entry_date", "content"}:
            raise LiveRunError("INVALID_DATASET", "A sample entry has an invalid shape.")
        raw_date = item["entry_date"]
        content_parts = item["content"]
        if not isinstance(raw_date, str) or not isinstance(content_parts, list):
            raise LiveRunError("INVALID_DATASET", "A sample entry has invalid values.")
        if not content_parts or any(
            not isinstance(part, str) or not part.strip() for part in content_parts
        ):
            raise LiveRunError("INVALID_DATASET", "A sample entry has blank content.")
        try:
            parsed_date = datetime.strptime(raw_date, "%d %B %Y").date()
        except ValueError as exc:
            raise LiveRunError(
                "INVALID_DATASET", "A sample entry date is invalid."
            ) from exc
        if parsed_date in seen_dates:
            raise LiveRunError("INVALID_DATASET", "Sample entry dates must be unique.")
        seen_dates.add(parsed_date)
        entries.append(
            SampleEntry(entry_date=parsed_date, content="\n\n".join(content_parts))
        )
    entries.sort(key=lambda item: item.entry_date)
    return entries, hashlib.sha256(raw).hexdigest()


def load_environment(
    frontend_path: Path, backend_path: Path
) -> tuple[dict[str, str], dict[str, str]]:
    frontend = _string_env(frontend_path)
    backend = _string_env(backend_path)
    for name in ("SUPABASE_TEST_EMAIL", "SUPABASE_TEST_PASSWORD"):
        if not frontend.get(name) or not backend.get(name):
            raise LiveRunError(
                "TEST_CREDENTIALS_MISSING",
                "Supabase test credentials are missing from an environment file.",
            )
        if frontend[name] != backend[name]:
            raise LiveRunError(
                "TEST_CREDENTIALS_MISMATCH",
                "The frontend and backend test credentials do not match.",
            )
    public_pairs = (
        ("NEXT_PUBLIC_SUPABASE_URL", "SUPABASE_URL"),
        ("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "SUPABASE_PUBLISHABLE_KEY"),
    )
    for frontend_name, backend_name in public_pairs:
        if not frontend.get(frontend_name) or not backend.get(backend_name):
            raise LiveRunError(
                "SUPABASE_CONFIG_MISSING",
                "Supabase public configuration is incomplete.",
            )
        if frontend[frontend_name] != backend[backend_name]:
            raise LiveRunError(
                "SUPABASE_CONFIG_MISMATCH",
                "The frontend and backend Supabase projects do not match.",
            )
    if not backend.get("OPENAI_API_KEY"):
        raise LiveRunError("OPENAI_KEY_MISSING", "The OpenAI API key is unavailable.")
    return frontend, backend


def _string_env(path: Path) -> dict[str, str]:
    try:
        values = dotenv_values(path)
    except OSError as exc:
        raise LiveRunError(
            "ENVIRONMENT_FILE_UNAVAILABLE", "An environment file is unavailable."
        ) from exc
    return {
        key: str(value).strip()
        for key, value in values.items()
        if isinstance(key, str) and value is not None
    }


def _validated_database_url(
    value: str,
    *,
    missing_code: str,
    invalid_code: str,
    label: str,
) -> URL:
    if not value.strip():
        raise LiveRunError(missing_code, f"The dedicated {label} database URL is unavailable.")
    try:
        parsed = make_url(value)
    except ArgumentError as exc:
        raise LiveRunError(
            invalid_code,
            f"The {label} database URL is invalid.",
        ) from exc
    if (
        parsed.drivername != "postgresql+psycopg"
        or not parsed.username
        or not parsed.host
        or not parsed.database
    ):
        raise LiveRunError(
            invalid_code,
            f"The {label} database URL must use PostgreSQL with the Psycopg 3 driver.",
        )
    return parsed


def build_settings(backend_env: Path, user_id: UUID) -> Settings:
    overrides: dict[str, Any] = {
        "REFLECTION_ENGINE_ENABLED": True,
        "REFLECTION_SCHEDULER_ENABLED": True,
        "REFLECTION_API_ENABLED": True,
        "REFLECTION_ROLLOUT_MODE": "publish",
        "REFLECTION_ROLLOUT_USER_IDS": str(user_id),
        "RATE_LIMITING_ENABLED": True,
        "OTEL_ENABLED": False,
        "STARTUP_READINESS_TIMEOUT_SECONDS": 60,
    }
    settings_factory = cast(Callable[..., Settings], Settings)
    settings = settings_factory(
        _env_file=backend_env,
        **overrides,
    )
    app_database_url = settings.APP_DATABASE_URL.get_secret_value()
    worker_database_url = settings.WORKER_DATABASE_URL.get_secret_value()
    app_parsed = _validated_database_url(
        app_database_url,
        missing_code="APP_DATABASE_CONFIG_MISSING",
        invalid_code="APP_DATABASE_CONFIG_INVALID",
        label="application",
    )
    worker_parsed = _validated_database_url(
        worker_database_url,
        missing_code="WORKER_DATABASE_CONFIG_MISSING",
        invalid_code="WORKER_DATABASE_CONFIG_INVALID",
        label="worker",
    )
    if (
        worker_database_url == app_database_url
        or worker_parsed.username == app_parsed.username
    ):
        raise LiveRunError(
            "WORKER_DATABASE_NOT_DISTINCT",
            "The worker and application database URLs must use distinct logins.",
        )
    configured = {
        "entry_analysis": settings.OPENAI_ENTRY_ANALYSIS_MODEL,
        "embedding": settings.OPENAI_SIGNAL_EMBEDDING_MODEL,
        "synthesis": settings.OPENAI_REFLECTION_SYNTHESIS_MODEL,
        "critic": settings.OPENAI_REFLECTION_CRITIC_MODEL,
    }
    if configured != MODEL_ROLES:
        raise LiveRunError(
            "MODEL_CONFIGURATION_MISMATCH",
            "The configured Reflection Engine model IDs are not the required GPT-5.6 roles.",
        )
    return settings


def build_observer_engine(
    backend: dict[str, str],
    *,
    engine_factory: Callable[..., Engine] = create_engine,
) -> Engine:
    value = backend.get("ADMIN_APP_DATABASE_URL", "").strip()
    if not value:
        raise LiveRunError(
            "OBSERVER_DATABASE_CONFIG_MISSING",
            "ADMIN_APP_DATABASE_URL is required for read-only live-test observations.",
        )
    try:
        parsed = make_url(value)
    except ArgumentError as exc:
        raise LiveRunError(
            "OBSERVER_DATABASE_CONFIG_INVALID",
            "ADMIN_APP_DATABASE_URL is invalid.",
        ) from exc
    if parsed.drivername in {"postgres", "postgresql"}:
        parsed = parsed.set(drivername="postgresql+psycopg")
    if (
        parsed.drivername != "postgresql+psycopg"
        or not parsed.username
        or not parsed.host
        or not parsed.database
    ):
        raise LiveRunError(
            "OBSERVER_DATABASE_CONFIG_INVALID",
            "ADMIN_APP_DATABASE_URL must be a PostgreSQL URL usable by Psycopg 3.",
        )
    return engine_factory(
        parsed,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 60},
    )


@contextmanager
def read_only_connection(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as connection, connection.begin():
        connection.execute(text("SET TRANSACTION READ ONLY"))
        yield connection


def verify_observer_database(engine: Engine, user_id: UUID) -> None:
    try:
        with read_only_connection(engine) as connection:
            count = connection.scalar(
                text(
                    "SELECT count(*) FROM public.processing_jobs "
                    "WHERE user_id = :user_id"
                ),
                {"user_id": user_id},
            )
            if not isinstance(count, int) or count < 0:
                raise RuntimeError("observer database count is invalid")
    except Exception as exc:
        raise LiveRunError(
            "OBSERVER_DATABASE_UNAVAILABLE",
            "The read-only live-test observer cannot inspect Reflection metadata.",
        ) from exc

def sign_in(frontend: dict[str, str], backend: dict[str, str]) -> tuple[str, UUID]:
    from supabase import create_client

    client = create_client(
        backend["SUPABASE_URL"], backend["SUPABASE_PUBLISHABLE_KEY"]
    )
    try:
        result = client.auth.sign_in_with_password(
            {
                "email": frontend["SUPABASE_TEST_EMAIL"],
                "password": frontend["SUPABASE_TEST_PASSWORD"],
            }
        )
        session = getattr(result, "session", None)
        user = getattr(result, "user", None)
        access_token = getattr(session, "access_token", None)
        user_id = getattr(user, "id", None)
        if not isinstance(access_token, str) or not access_token or not user_id:
            raise ValueError("session unavailable")
        return access_token, UUID(str(user_id))
    except Exception as exc:
        raise LiveRunError(
            "SUPABASE_SIGN_IN_FAILED", "The Supabase test account could not sign in."
        ) from exc


def verify_worker_database(
    settings: Settings,
    *,
    sessions_builder: Callable[[Settings], Any] = build_database_sessions,
) -> None:
    sessions = None
    try:
        sessions = sessions_builder(settings)
        engine = sessions.worker_engine
        if engine is None:
            raise RuntimeError("worker database is unavailable")
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL ROLE orion_worker"))
            active_role = connection.scalar(
                text("SELECT pg_catalog.current_setting('role', true)")
            )
            if active_role != "orion_worker":
                raise RuntimeError("worker role was not activated")
    except Exception as exc:
        raise LiveRunError(
            "WORKER_DATABASE_ROLE_UNAVAILABLE",
            "The worker database login cannot assume the orion_worker role.",
        ) from exc
    finally:
        if sessions is not None:
            sessions.dispose()


def verify_application_database(
    settings: Settings,
    user_id: UUID,
    *,
    sessions_builder: Callable[[Settings], Any] = build_database_sessions,
) -> None:
    sessions = None
    try:
        sessions = sessions_builder(settings)
        with sessions.unit_of_work_factory.for_user(user_id) as work:
            count = work.session.execute(
                text(
                    "SELECT count(*) FROM public.entries "
                    "WHERE user_id = :user_id"
                ),
                {"user_id": user_id},
            ).scalar_one()
            if not isinstance(count, int) or count < 0:
                raise RuntimeError("application database count is invalid")
    except Exception as exc:
        raise LiveRunError(
            "APP_DATABASE_ROLE_UNAVAILABLE",
            "The application database login cannot assume the authenticated role.",
        ) from exc
    finally:
        if sessions is not None:
            sessions.dispose()


def run_model_preflight(settings: Settings) -> None:
    targets = tuple(
        ModelAccessTarget(role, model) for role, model in MODEL_ROLES.items()
    )
    try:
        check_reflection_model_access(
            build_openai_client(settings.OPENAI_API_KEY.get_secret_value()), targets
        )
    except Exception as exc:
        raise LiveRunError(
            "MODEL_ACCESS_FAILED", "One or more configured models are unavailable."
        ) from exc
