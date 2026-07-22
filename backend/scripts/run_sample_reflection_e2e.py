from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import socket
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time as wall_time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.modules.reflection_engine.preflight import (
    ModelAccessTarget,
    check_reflection_model_access,
)
from app.modules.reflections.schemas import ReflectionResponse
from app.shared.config.settings import Settings
from app.shared.database.session import build_database_sessions
from app.shared.integrations.openai import build_openai_client


PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"
PRICE_PER_MILLION_USD: dict[str, dict[str, tuple[Decimal, ...]]] = {
    "default": {
        "gpt-5.6-luna": tuple(map(Decimal, ("1", "0.1", "1.25", "6"))),
        "gpt-5.6-terra": tuple(
            map(Decimal, ("2.5", "0.25", "3.125", "15"))
        ),
        "gpt-5.6-sol": tuple(map(Decimal, ("5", "0.5", "6.25", "30"))),
    },
    "flex": {
        "gpt-5.6-luna": tuple(map(Decimal, ("0.5", "0.05", "0.625", "3"))),
        "gpt-5.6-terra": tuple(
            map(Decimal, ("1.25", "0.125", "1.5625", "7.5"))
        ),
        "gpt-5.6-sol": tuple(map(Decimal, ("2.5", "0.25", "3.125", "15"))),
    },
    "priority": {
        "gpt-5.6-luna": tuple(map(Decimal, ("2", "0.2", "2.5", "12"))),
        "gpt-5.6-terra": tuple(map(Decimal, ("5", "0.5", "6.25", "30"))),
        "gpt-5.6-sol": tuple(map(Decimal, ("10", "1", "12.5", "60"))),
    },
}
MODEL_ROLES = {
    "entry_analysis": "gpt-5.6-luna",
    "synthesis": "gpt-5.6-terra",
    "critic": "gpt-5.6-sol",
}
COUNT_TABLES = (
    "entries",
    "past_entry_imports",
    "entry_analyses",
    "entry_signals",
    "user_pii_vaults",
    "processing_jobs",
    "pattern_candidates",
    "pattern_candidate_evidence",
    "reflection_snapshots",
    "reflection_snapshot_insights",
    "reflection_snapshot_evidence",
    "reflection_feedback",
)


class LiveRunError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SampleEntry:
    entry_date: date
    content: str


class SafeEventCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        event = getattr(record, "orion_event", None)
        fields = getattr(record, "orion_fields", None)
        if isinstance(event, str) and isinstance(fields, dict):
            self.events.append({"event": event, **fields})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the real authenticated 30-entry Reflection Engine E2E suite."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frontend-env", type=Path, required=True)
    parser.add_argument("--backend-env", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=14_400)
    parser.add_argument("--import-interval-seconds", type=float, default=0.55)
    parser.add_argument("--prior-diagnostic-attempts", type=int, default=0)
    parser.add_argument("--prior-diagnostic-unpriced-attempts", type=int, default=0)
    parser.add_argument("--prior-diagnostic-known-cost-usd", type=Decimal, default=Decimal(0))
    return parser.parse_args(argv)


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
    settings = Settings(
        _env_file=backend_env,
        **overrides,
    )
    if not settings.WORKER_DATABASE_URL.get_secret_value().strip():
        raise LiveRunError(
            "WORKER_DATABASE_CONFIG_MISSING",
            "The dedicated worker database URL is unavailable.",
        )
    if (
        settings.WORKER_DATABASE_URL.get_secret_value()
        == settings.APP_DATABASE_URL.get_secret_value()
    ):
        raise LiveRunError(
            "WORKER_DATABASE_NOT_DISTINCT",
            "The worker and application database URLs must use distinct logins.",
        )
    configured = {
        "entry_analysis": settings.OPENAI_ENTRY_ANALYSIS_MODEL,
        "synthesis": settings.OPENAI_REFLECTION_SYNTHESIS_MODEL,
        "critic": settings.OPENAI_REFLECTION_CRITIC_MODEL,
    }
    if configured != MODEL_ROLES:
        raise LiveRunError(
            "MODEL_CONFIGURATION_MISMATCH",
            "The configured Reflection Engine model IDs are not the required GPT-5.6 roles.",
        )
    return settings


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


def verify_worker_database(settings: Settings) -> None:
    sessions = build_database_sessions(settings)
    engine = sessions.worker_engine
    if engine is None:
        sessions.dispose()
        raise LiveRunError(
            "WORKER_DATABASE_CONFIG_MISSING",
            "The dedicated worker database URL is unavailable.",
        )
    try:
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


def request_json(
    client: TestClient,
    method: str,
    path: str,
    *,
    token: str,
    expected_status: int,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.request(
        method,
        path,
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    if response.status_code != expected_status:
        try:
            body = response.json()
            code = str(body.get("error", {}).get("code", "HTTP_FAILURE"))
        except (ValueError, AttributeError):
            code = "HTTP_FAILURE"
        raise LiveRunError(
            code if code.isupper() else "HTTP_FAILURE",
            f"{method} {path} returned HTTP {response.status_code}.",
        )
    value = response.json()
    if not isinstance(value, dict):
        raise LiveRunError("INVALID_API_RESPONSE", "An API response is invalid.")
    return value


def inspect_existing_entries(
    client: TestClient, token: str, _expected: list[SampleEntry]
) -> set[date]:
    page = request_json(
        client,
        "GET",
        "/api/v1/entries?page=1&page_size=100",
        token=token,
        expected_status=200,
    )
    items = page.get("items")
    total = page.get("total")
    if not isinstance(items, list) or not isinstance(total, int) or total != len(items):
        raise LiveRunError("INVALID_API_RESPONSE", "The entries page is invalid.")
    if total:
        raise LiveRunError(
            "TEST_USER_CONTAMINATED",
            "The test user contains existing entries; no data was overwritten.",
        )
    return set()


def active_queue_owners(application: Any, user_id: UUID) -> tuple[int, int]:
    engine = application.state.database_sessions.application_engine
    if engine is None:
        raise LiveRunError("DATABASE_CONFIG_MISSING", "Operator database is unavailable.")
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT "
                "count(*) FILTER (WHERE user_id = :user_id) AS owned, "
                "count(*) FILTER (WHERE user_id <> :user_id) AS foreign "
                "FROM public.processing_jobs "
                "WHERE status IN ('pending', 'running')"
            ),
            {"user_id": user_id},
        ).mappings().one()
    return int(row["owned"]), int(row["foreign"])


def submit_missing_entries(
    client: TestClient,
    token: str,
    entries: list[SampleEntry],
    existing_dates: set[date],
    *,
    interval_seconds: float,
) -> list[dict[str, Any]]:
    submitted: list[dict[str, Any]] = []
    last_submission = 0.0
    for entry in entries:
        if entry.entry_date in existing_dates:
            continue
        remaining = interval_seconds - (time.monotonic() - last_submission)
        if remaining > 0:
            time.sleep(remaining)
        accepted = request_json(
            client,
            "POST",
            "/api/v1/past-entries",
            token=token,
            expected_status=202,
            payload={
                "entry_date": entry.entry_date.isoformat(),
                "content": entry.content,
            },
        )
        last_submission = time.monotonic()
        submitted.append(
            {
                "entryDate": entry.entry_date.isoformat(),
                "entryId": str(accepted["entry_id"]),
                "endpoint": "POST /api/v1/past-entries",
                "httpStatus": 202,
                "processingStatus": accepted["processing_status"],
                "statusUrl": accepted["status_url"],
            }
        )
        _progress("imports", submitted=len(submitted), total=len(entries))
    return submitted


def job_status_counts(application: Any, user_id: UUID, job_type: str) -> Counter[str]:
    engine = application.state.database_sessions.application_engine
    if engine is None:
        raise LiveRunError("DATABASE_CONFIG_MISSING", "Operator database is unavailable.")
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT status, count(*) AS count FROM public.processing_jobs "
                "WHERE user_id = :user_id AND job_type = :job_type GROUP BY status"
            ),
            {"user_id": user_id, "job_type": job_type},
        ).mappings().all()
    return Counter({str(row["status"]): int(row["count"]) for row in rows})


def drain_jobs(
    application: Any,
    user_id: UUID,
    job_type: str,
    *,
    deadline: float,
) -> Counter[str]:
    worker = application.state.processing_worker
    uow = application.state.database_sessions.unit_of_work_factory
    worker_id = f"sample-e2e-{socket.gethostname()[:30]}-{os.getpid()}"
    last_reported: tuple[tuple[str, int], ...] | None = None
    while time.monotonic() < deadline:
        _owned_active, foreign_active = active_queue_owners(application, user_id)
        if foreign_active:
            raise LiveRunError(
                "SHARED_QUEUE_BUSY",
                "Another user's processing job appeared; the test will not claim it.",
            )
        statuses = job_status_counts(application, user_id, job_type)
        state = tuple(sorted(statuses.items()))
        if state != last_reported:
            _progress(job_type, **dict(state))
            last_reported = state
        if statuses["pending"] == 0 and statuses["running"] == 0:
            return statuses
        processed = worker.run_one(worker_id=worker_id, uow=uow)
        if not processed:
            time.sleep(1)
    raise LiveRunError("RUN_TIMEOUT", f"{job_type} did not finish before timeout.")


def schedule_synthesis(application: Any, user_id: UUID) -> int:
    uow = application.state.database_sessions.unit_of_work_factory
    engine = application.state.database_sessions.application_engine
    if engine is None:
        raise LiveRunError("DATABASE_CONFIG_MISSING", "Operator database is unavailable.")
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT p.timezone, s.last_schedule_local_date "
                "FROM public.user_profiles p "
                "LEFT JOIN public.reflection_user_state s ON s.user_id = p.user_id "
                "WHERE p.user_id = :user_id"
            ),
            {"user_id": user_id},
        ).mappings().one()
    timezone_name = str(row["timezone"])
    local_zone = ZoneInfo(timezone_name)
    local_date = datetime.now(local_zone).date()
    last_schedule = row["last_schedule_local_date"]
    if isinstance(last_schedule, date) and last_schedule >= local_date:
        local_date = last_schedule + timedelta(days=1)
    synthetic_local = datetime.combine(
        local_date, wall_time(hour=18, minute=5), tzinfo=local_zone
    )
    return application.state.job_service.schedule_reflections(
        uow=uow,
        now=synthetic_local.astimezone(UTC),
    )


def database_snapshot(application: Any, user_id: UUID) -> dict[str, Any]:
    engine = application.state.database_sessions.application_engine
    if engine is None:
        raise LiveRunError("DATABASE_CONFIG_MISSING", "Operator database is unavailable.")
    with engine.connect() as connection:
        tables = {
            table: int(
                connection.scalar(
                    text(f"SELECT count(*) FROM public.{table} WHERE user_id = :user_id"),
                    {"user_id": user_id},
                )
                or 0
            )
            for table in COUNT_TABLES
        }
        entries = _grouped_counts(
            connection,
            "SELECT processing_status AS key, count(*) AS count FROM public.entries "
            "WHERE user_id = :user_id GROUP BY processing_status",
            user_id,
        )
        analyses = _grouped_counts(
            connection,
            "SELECT eligibility AS key, count(*) AS count FROM public.entry_analyses "
            "WHERE user_id = :user_id GROUP BY eligibility",
            user_id,
        )
        analysis_models = _grouped_counts(
            connection,
            "SELECT model_id AS key, count(*) AS count FROM public.entry_analyses "
            "WHERE user_id = :user_id GROUP BY model_id",
            user_id,
        )
        signals = _grouped_counts(
            connection,
            "SELECT signal_type AS key, count(*) AS count FROM public.entry_signals "
            "WHERE user_id = :user_id GROUP BY signal_type",
            user_id,
        )
        jobs = _two_key_counts(
            connection,
            "SELECT job_type AS first, status AS second, count(*) AS count "
            "FROM public.processing_jobs WHERE user_id = :user_id "
            "GROUP BY job_type, status",
            user_id,
        )
        candidates = _two_key_counts(
            connection,
            "SELECT pattern_type AS first, status AS second, count(*) AS count "
            "FROM public.pattern_candidates WHERE user_id = :user_id "
            "GROUP BY pattern_type, status",
            user_id,
        )
        insights = _two_key_counts(
            connection,
            "SELECT pattern_type AS first, status AS second, count(*) AS count "
            "FROM public.reflection_snapshot_insights WHERE user_id = :user_id "
            "GROUP BY pattern_type, status",
            user_id,
        )
    return {
        "tableRowCounts": tables,
        "entryStatuses": entries,
        "analysisEligibility": analyses,
        "analysisModels": analysis_models,
        "signalTypes": signals,
        "jobStatuses": jobs,
        "candidateStatuses": candidates,
        "insightStatuses": insights,
    }


def entry_breakdown(
    application: Any,
    user_id: UUID,
    submissions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    engine = application.state.database_sessions.application_engine
    if engine is None:
        raise LiveRunError("DATABASE_CONFIG_MISSING", "Operator database is unavailable.")
    submitted_by_id = {str(item["entryId"]): item for item in submissions}
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT e.id, e.entry_date, e.input_type, e.processing_status, "
                "p.status AS import_status, j.status AS job_status, j.attempts, "
                "j.last_error_code, a.entry_kind, a.model_eligibility, "
                "a.eligibility, a.deterministic_features, a.semantic_scores, "
                "a.exclusion_reason_codes, a.reflective_word_count, a.model_id, "
                "a.prompt_version "
                "FROM public.entries e "
                "LEFT JOIN public.past_entry_imports p "
                "ON p.entry_id = e.id AND p.user_id = e.user_id "
                "LEFT JOIN public.processing_jobs j "
                "ON j.entry_id = e.id AND j.user_id = e.user_id "
                "AND j.job_type = 'entry_processing' "
                "LEFT JOIN public.entry_analyses a "
                "ON a.entry_id = e.id AND a.user_id = e.user_id "
                "WHERE e.user_id = :user_id ORDER BY e.entry_date, e.id"
            ),
            {"user_id": user_id},
        ).mappings().all()
        signal_rows = connection.execute(
            text(
                "SELECT entry_id, signal_type, count(*) AS count "
                "FROM public.entry_signals WHERE user_id = :user_id "
                "GROUP BY entry_id, signal_type ORDER BY entry_id, signal_type"
            ),
            {"user_id": user_id},
        ).mappings().all()
    signal_counts: dict[str, dict[str, int]] = {}
    for row in signal_rows:
        signal_counts.setdefault(str(row["entry_id"]), {})[
            str(row["signal_type"])
        ] = int(row["count"])
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        entry_id = str(row["id"])
        submission = submitted_by_id.get(entry_id)
        if submission is None:
            raise LiveRunError(
                "ENTRY_BREAKDOWN_MISMATCH",
                "A persisted entry does not match the submitted dataset.",
            )
        by_type = signal_counts.get(entry_id, {})
        result.append(
            {
                "index": index,
                "entryDate": row["entry_date"].isoformat(),
                "entryId": entry_id,
                "submission": submission,
                "storage": {
                    "inputType": row["input_type"],
                    "entryStatus": row["processing_status"],
                    "importStatus": row["import_status"],
                },
                "worker": {
                    "jobStatus": row["job_status"],
                    "attempts": int(row["attempts"] or 0),
                    "errorCode": row["last_error_code"],
                },
                "quality": {
                    "deterministicFeatures": row["deterministic_features"],
                    "entryKind": row["entry_kind"],
                    "modelEligibility": row["model_eligibility"],
                    "finalEligibility": row["eligibility"],
                    "semanticScores": row["semantic_scores"],
                    "exclusionReasonCodes": list(
                        row["exclusion_reason_codes"] or []
                    ),
                    "reflectiveWordCount": int(row["reflective_word_count"] or 0),
                },
                "analysis": {
                    "model": row["model_id"],
                    "promptVersion": row["prompt_version"],
                },
                "signals": {
                    "count": sum(by_type.values()),
                    "byType": by_type,
                },
            }
        )
    return result


def pipeline_event_report(events: list[dict[str, Any]]) -> dict[str, Any]:
    proposal_discards = Counter(
        str(event.get("reason_code", "UNKNOWN"))
        for event in events
        if event.get("event") == "reflection_proposal_discarded"
    )
    candidate_outcomes = Counter(
        (str(event.get("pattern_type", "unknown")), str(event.get("outcome", "unknown")))
        for event in events
        if event.get("event") == "reflection_candidate_observed"
    )
    entry_outcomes = Counter(
        (str(event.get("status", "unknown")), str(event.get("entry_kind", "unknown")))
        for event in events
        if event.get("event") == "entry_analysis_materialized"
    )
    return {
        "entryAnalysisOutcomes": {
            f"{status}:{kind}": count
            for (status, kind), count in sorted(entry_outcomes.items())
        },
        "candidateOutcomes": {
            f"{pattern_type}:{outcome}": count
            for (pattern_type, outcome), count in sorted(candidate_outcomes.items())
        },
        "proposalDiscardReasons": dict(sorted(proposal_discards.items())),
    }


def available_insight_count(response: dict[str, Any]) -> int:
    data = response.get("data")
    if not isinstance(data, dict):
        return 0
    return sum(
        1
        for key in ("hiddenDriver", "recurringLoop", "innerTensions")
        if isinstance(data.get(key), dict) and data[key].get("status") == "available"
    )


def _grouped_counts(session: Any, sql: str, user_id: UUID) -> dict[str, int]:
    rows = session.execute(text(sql), {"user_id": user_id}).mappings()
    return {str(row["key"]): int(row["count"]) for row in rows}


def _two_key_counts(session: Any, sql: str, user_id: UUID) -> dict[str, int]:
    rows = session.execute(text(sql), {"user_id": user_id}).mappings()
    return {
        f"{row['first']}:{row['second']}": int(row["count"]) for row in rows
    }


def model_usage_report(events: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = [
        event
        for event in events
        if event.get("event") in {"entry_analysis_attempt", "reflection_model_attempt"}
    ]
    calls: list[dict[str, Any]] = []
    by_role: dict[str, list[dict[str, Any]]] = {
        role: [] for role in MODEL_ROLES
    }
    for ordinal, event in enumerate(attempts, start=1):
        role = str(event["model_role"])
        measured = {
            "ordinal": ordinal,
            "role": role,
            "model": str(event["model_id"]),
            "promptVersion": str(event["prompt_version"]),
            "status": str(event["status"]),
            "retryClass": str(event["retry_class"]),
            "serviceTier": str(event["service_tier"]),
            "durationMs": int(event["duration_ms"]),
            "inputTokens": int(event["input_tokens"]),
            "cachedInputTokens": int(event["cached_input_tokens"]),
            "cacheWriteInputTokens": int(event["cache_write_input_tokens"]),
            "outputTokens": int(event["output_tokens"]),
            "reasoningOutputTokens": int(event["reasoning_output_tokens"]),
        }
        measured["estimatedCostUsd"] = estimate_call_cost(measured)
        calls.append(measured)
        by_role.setdefault(role, []).append(measured)
    roles = []
    pricing_complete = all(call["estimatedCostUsd"] is not None for call in calls)
    for role, model in MODEL_ROLES.items():
        selected = by_role.get(role, [])
        durations = [int(call["durationMs"]) for call in selected]
        roles.append(
            {
                "role": role,
                "model": model,
                "usedAt": {
                    "entry_analysis": "entry_processing",
                    "synthesis": "reflection_synthesis",
                    "critic": "conditional_candidate_review",
                }[role],
                "routingRule": (
                    "abs(score-threshold) <= 0.05 or contradiction >= 0.20"
                    if role == "critic"
                    else None
                ),
                "eligibleCandidates": len(selected) if role == "critic" else None,
                "calls": len(selected),
                "successfulCalls": sum(call["status"] == "success" for call in selected),
                "inputTokens": sum(int(call["inputTokens"]) for call in selected),
                "cachedInputTokens": sum(
                    int(call["cachedInputTokens"]) for call in selected
                ),
                "cacheWriteInputTokens": sum(
                    int(call["cacheWriteInputTokens"]) for call in selected
                ),
                "outputTokens": sum(int(call["outputTokens"]) for call in selected),
                "reasoningOutputTokens": sum(
                    int(call["reasoningOutputTokens"]) for call in selected
                ),
                "modelWallTimeMs": sum(durations),
                "latencyMs": latency_summary(durations),
                "estimatedCostUsd": (
                    _money(
                        sum(
                            (
                                Decimal(str(call["estimatedCostUsd"]))
                                for call in selected
                                if call["estimatedCostUsd"] is not None
                            ),
                            start=Decimal(0),
                        )
                    )
                    if all(
                        call["estimatedCostUsd"] is not None for call in selected
                    )
                    else None
                ),
                "outcome": "not_invoked" if not selected else "measured",
            }
        )
    total = sum(
        (
            Decimal(str(call["estimatedCostUsd"]))
            for call in calls
            if call["estimatedCostUsd"] is not None
        ),
        start=Decimal(0),
    )
    return {
        "pricing": {
            "currency": "USD",
            "unit": "per_1m_tokens",
            "source": PRICING_SOURCE,
            "retrievedAt": datetime.now(UTC).isoformat(),
            "note": (
                "Estimate from response usage; the OpenAI billing dashboard is authoritative. "
                "Regional data-residency uplift is not included."
            ),
        },
        "roles": roles,
        "calls": calls,
        "pricingComplete": pricing_complete,
        "estimatedTotalCostUsd": _money(total) if pricing_complete else None,
    }


def estimate_call_cost(call: dict[str, Any]) -> float | None:
    tier = str(call["serviceTier"])
    if tier == "standard":
        tier = "default"
    model = str(call["model"])
    rates = PRICE_PER_MILLION_USD.get(tier, {}).get(model)
    if rates is None:
        return None
    input_tokens = int(call["inputTokens"])
    cached = int(call["cachedInputTokens"])
    cache_write = int(call["cacheWriteInputTokens"])
    output = int(call["outputTokens"])
    uncached = max(0, input_tokens - cached - cache_write)
    input_rate, cached_rate, cache_write_rate, output_rate = rates
    cost = (
        Decimal(uncached) * input_rate
        + Decimal(cached) * cached_rate
        + Decimal(cache_write) * cache_write_rate
        + Decimal(output) * output_rate
    ) / Decimal(1_000_000)
    return _money(cost)


def latency_summary(values: list[int]) -> dict[str, int] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "average": round(sum(ordered) / len(ordered)),
        "p50": _percentile(ordered, 0.50),
        "p95": _percentile(ordered, 0.95),
        "max": ordered[-1],
    }


def _percentile(ordered: list[int], percentile: float) -> int:
    index = max(0, math.ceil(len(ordered) * percentile) - 1)
    return ordered[index]


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    encoded = json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=True) + "\n"
    temporary.write_text(encoded, encoding="utf-8")
    os.replace(temporary, path)


def _progress(stage: str, **values: Any) -> None:
    print(json.dumps({"stage": stage, **values}, separators=(",", ":")), flush=True)


def run(
    args: argparse.Namespace,
    *,
    collector: SafeEventCollector | None = None,
) -> dict[str, Any]:
    overall_started = time.monotonic()
    started_at = datetime.now(UTC)
    stage_seconds: dict[str, float] = {}
    checks: list[dict[str, Any]] = []
    entries, dataset_hash = load_sample_entries(args.input)
    if len(entries) != 30:
        raise LiveRunError("INVALID_DATASET", "The live suite requires exactly 30 entries.")
    frontend, backend = load_environment(args.frontend_env, args.backend_env)
    checks.extend(
        (
            {"name": "dataset_valid", "status": "passed", "actual": len(entries)},
            {"name": "credential_parity", "status": "passed"},
            {"name": "supabase_project_parity", "status": "passed"},
        )
    )

    stage_started = time.monotonic()
    token, user_id = sign_in(frontend, backend)
    stage_seconds["supabaseAuthentication"] = time.monotonic() - stage_started
    checks.append({"name": "supabase_authentication", "status": "passed"})
    settings = build_settings(args.backend_env, user_id)

    stage_started = time.monotonic()
    verify_worker_database(settings)
    stage_seconds["workerDatabasePreflight"] = time.monotonic() - stage_started
    checks.append({"name": "worker_database_role", "status": "passed"})

    stage_started = time.monotonic()
    run_model_preflight(settings)
    stage_seconds["modelAccessPreflight"] = time.monotonic() - stage_started
    checks.append({"name": "model_access_preflight", "status": "passed"})

    application = create_app(settings=settings)
    collector = collector or SafeEventCollector()
    logging.getLogger().addHandler(collector)
    deadline = overall_started + args.timeout_seconds
    try:
        with TestClient(application, raise_server_exceptions=True) as client:
            stage_started = time.monotonic()
            existing_dates = inspect_existing_entries(client, token, entries)
            owned_active, foreign_active = active_queue_owners(application, user_id)
            if foreign_active:
                raise LiveRunError(
                    "SHARED_QUEUE_BUSY",
                    "Another user's processing jobs are active; the test will not claim them.",
                )
            before_database = database_snapshot(application, user_id)
            nonempty_tables = {
                table: count
                for table, count in before_database["tableRowCounts"].items()
                if count
            }
            if existing_dates or owned_active or nonempty_tables:
                raise LiveRunError(
                    "TEST_USER_CONTAMINATED",
                    "The test user is not empty; no existing data will be overwritten.",
                )
            stage_seconds["isolationPreflight"] = time.monotonic() - stage_started
            checks.append(
                {
                    "name": "test_user_isolation",
                    "status": "passed",
                    "existingEntries": len(existing_dates),
                    "ownedActiveJobs": owned_active,
                    "foreignActiveJobs": foreign_active,
                    "nonemptyUserTables": nonempty_tables,
                }
            )

            stage_started = time.monotonic()
            submissions = submit_missing_entries(
                client,
                token,
                entries,
                existing_dates,
                interval_seconds=args.import_interval_seconds,
            )
            stage_seconds["historicalEntrySubmission"] = (
                time.monotonic() - stage_started
            )
            checks.append(
                {
                    "name": "historical_entries_submitted",
                    "status": "passed",
                    "new": len(submissions),
                    "reused": len(existing_dates),
                    "total": len(entries),
                }
            )

            stage_started = time.monotonic()
            entry_jobs = drain_jobs(
                application, user_id, "entry_processing", deadline=deadline
            )
            stage_seconds["entryProcessing"] = time.monotonic() - stage_started
            if entry_jobs["failed"] or entry_jobs["completed"] != len(entries):
                raise LiveRunError(
                    "ENTRY_PROCESSING_FAILED",
                    "One or more entry-processing jobs did not complete.",
                )
            checks.append(
                {
                    "name": "entry_processing_jobs",
                    "status": "passed",
                    "completed": entry_jobs["completed"],
                    "failed": entry_jobs["failed"],
                }
            )

            stage_started = time.monotonic()
            enqueued = schedule_synthesis(application, user_id)
            stage_seconds["reflectionScheduling"] = time.monotonic() - stage_started
            synthesis_before = job_status_counts(
                application, user_id, "reflection_synthesis"
            )
            if enqueued not in {0, 1} or sum(synthesis_before.values()) != 1:
                raise LiveRunError(
                    "SYNTHESIS_NOT_SCHEDULED",
                    "Exactly one reflection synthesis job was not available.",
                )
            checks.append(
                {
                    "name": "reflection_synthesis_scheduled",
                    "status": "passed",
                    "newlyEnqueued": enqueued,
                    "totalJobs": sum(synthesis_before.values()),
                }
            )

            stage_started = time.monotonic()
            synthesis_jobs = drain_jobs(
                application, user_id, "reflection_synthesis", deadline=deadline
            )
            stage_seconds["reflectionSynthesis"] = time.monotonic() - stage_started
            if synthesis_jobs["failed"] or synthesis_jobs["completed"] != 1:
                raise LiveRunError(
                    "REFLECTION_SYNTHESIS_FAILED",
                    "The reflection synthesis job did not complete.",
                )
            checks.append(
                {
                    "name": "reflection_synthesis_job",
                    "status": "passed",
                    "completed": synthesis_jobs["completed"],
                    "failed": synthesis_jobs["failed"],
                }
            )

            stage_started = time.monotonic()
            raw_reflection = request_json(
                client,
                "GET",
                "/api/v1/reflections?range=all",
                token=token,
                expected_status=200,
            )
            ReflectionResponse.model_validate(raw_reflection)
            stage_seconds["reflectionGet"] = time.monotonic() - stage_started
            if (
                raw_reflection.get("reflectionState") != "available"
                or raw_reflection.get("processingState") != "idle"
            ):
                raise LiveRunError(
                    "REFLECTION_NOT_AVAILABLE",
                    "The final reflection aggregate is not available and idle.",
                )
            checks.append(
                {
                    "name": "reflection_get",
                    "status": "passed",
                    "httpStatus": 200,
                    "reflectionState": raw_reflection["reflectionState"],
                    "processingState": raw_reflection["processingState"],
                }
            )
            database = database_snapshot(application, user_id)
            entries_report = entry_breakdown(
                application, user_id, submissions
            )
    finally:
        logging.getLogger().removeHandler(collector)
        token = ""

    usage = model_usage_report(collector.events)
    pipeline_events = pipeline_event_report(collector.events)
    usage["diagnosticsBeforeCanonicalRun"] = {
        "attempts": args.prior_diagnostic_attempts,
        "unpricedAttempts": args.prior_diagnostic_unpriced_attempts,
        "knownEstimatedCostUsd": _money(args.prior_diagnostic_known_cost_usd),
        "includedInCanonicalTotal": False,
        "note": (
            "Earlier schema diagnostics are reported separately; attempts without "
            "response usage may still appear on the authoritative OpenAI bill."
        ),
    }
    luna = next(item for item in usage["roles"] if item["role"] == "entry_analysis")
    terra = next(item for item in usage["roles"] if item["role"] == "synthesis")
    sol = next(item for item in usage["roles"] if item["role"] == "critic")
    if database["analysisModels"].get(MODEL_ROLES["entry_analysis"], 0) != 30:
        raise LiveRunError(
            "LUNA_DATABASE_COUNT_MISMATCH",
            "All 30 stored entry analyses were not produced by Luna.",
        )
    if luna["calls"] < 30 or luna["successfulCalls"] != 30:
        raise LiveRunError(
            "LUNA_CALL_COUNT_MISMATCH",
            "Luna did not produce exactly 30 successful entry analyses.",
        )
    if terra["calls"] < 1 or terra["successfulCalls"] != 1:
        raise LiveRunError(
            "TERRA_CALL_COUNT_MISMATCH",
            "Terra did not produce exactly one successful synthesis.",
        )
    available_insights = available_insight_count(raw_reflection)
    if available_insights == 0:
        raise LiveRunError(
            "REFLECTION_OUTPUT_EMPTY",
            "The reflective dataset produced no available insight sections.",
        )
    checks.extend(
        (
            {
                "name": "luna_model_routing",
                "status": "passed",
                "calls": luna["calls"],
            },
            {
                "name": "terra_model_routing",
                "status": "passed",
                "calls": terra["calls"],
            },
            {
                "name": "sol_conditional_routing",
                "status": "passed",
                "calls": sol["calls"],
                "outcome": sol["outcome"],
            },
            {
                "name": "reflection_has_available_insight",
                "status": "passed",
                "availableSections": available_insights,
            },
        )
    )
    completed_at = datetime.now(UTC)
    stage_seconds["total"] = time.monotonic() - overall_started
    return {
        "schemaVersion": 1,
        "status": "passed",
        "run": {
            "dataset": str(args.input),
            "datasetSha256": dataset_hash,
            "entryCount": len(entries),
            "wordCount": sum(len(entry.content.split()) for entry in entries),
            "characterCount": sum(len(entry.content) for entry in entries),
            "firstEntryDate": entries[0].entry_date.isoformat(),
            "lastEntryDate": entries[-1].entry_date.isoformat(),
            "startedAt": started_at.isoformat(),
            "completedAt": completed_at.isoformat(),
            "rolloutMode": "publish",
            "transport": "FastAPI TestClient over the real ASGI application",
            "database": "real Supabase PostgreSQL",
            "providers": "real OpenAI Responses API",
            "workerDatabaseConnection": "dedicated",
            "testUserHash": hashlib.sha256(str(user_id).encode()).hexdigest(),
        },
        "timingSeconds": {
            name: round(value, 3) for name, value in stage_seconds.items()
        },
        "modelUsage": usage,
        "pipelineEvents": pipeline_events,
        "databaseEffects": database,
        "entryBreakdown": entries_report,
        "reflectionGetResponse": raw_reflection,
        "checks": checks,
        "errors": [],
        "operationalNuances": [
            "All entry writes used authenticated POST /api/v1/past-entries.",
            "The production rate limiter remained enabled and submissions were paced.",
            "Entry content was encrypted at rest and locally PII-redacted before model use.",
            "OpenAI provider storage and SDK retries remained disabled.",
            "Application queue retries, heartbeats, ownership checks, scoring, and evidence validation remained active.",
            "Reflection synthesis was scheduled through the production scheduler with a controlled post-18:00 timestamp.",
            "The final result came from authenticated GET /api/v1/reflections?range=all.",
            "The in-process ASGI transport excludes browser and external HTTP-server latency while preserving real authentication, database, queue, and provider boundaries.",
            "Total wall time includes the 30-entry rate-limit pacing; modelWallTimeMs isolates measured provider attempts.",
            "Estimated AI cost excludes Supabase, hosting, network, observability, and any regional OpenAI data-residency uplift.",
            "Reasoning tokens are reported as a subset of output tokens and are costed through the output-token total.",
            "The model access preflight retrieves metadata and does not create billable Responses.",
            "Sol is intentionally absent when no synthesized candidate meets the deterministic critic-routing rule.",
            "The suite does not clean up its persisted database effects after completion.",
        ],
    }


def failure_report(
    args: argparse.Namespace,
    *,
    started_at: datetime,
    error: LiveRunError,
    elapsed_seconds: float,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "status": "failed",
        "run": {
            "dataset": str(args.input),
            "startedAt": started_at.isoformat(),
            "completedAt": datetime.now(UTC).isoformat(),
        },
        "timingSeconds": {"total": round(elapsed_seconds, 3)},
        "modelUsage": model_usage_report(events or []),
        "pipelineEvents": pipeline_event_report(events or []),
        "databaseEffects": None,
        "entryBreakdown": None,
        "reflectionGetResponse": None,
        "checks": [],
        "errors": [{"code": error.code, "message": error.safe_message}],
    }


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    started_at = datetime.now(UTC)
    started = time.monotonic()
    collector = SafeEventCollector()
    try:
        result = run(args, collector=collector)
    except LiveRunError as exc:
        result = failure_report(
            args,
            started_at=started_at,
            error=exc,
            elapsed_seconds=time.monotonic() - started,
            events=collector.events,
        )
        atomic_write_json(args.output, result)
        raise SystemExit(f"{exc.code}: {exc.safe_message}") from None
    except Exception:
        error = LiveRunError(
            "UNEXPECTED_FAILURE", "The live Reflection Engine test failed unexpectedly."
        )
        result = failure_report(
            args,
            started_at=started_at,
            error=error,
            elapsed_seconds=time.monotonic() - started,
            events=collector.events,
        )
        atomic_write_json(args.output, result)
        raise SystemExit(f"{error.code}: {error.safe_message}") from None
    atomic_write_json(args.output, result)
    _progress(
        "complete",
        output=str(args.output),
        estimatedCostUsd=result["modelUsage"]["estimatedTotalCostUsd"],
        totalSeconds=result["timingSeconds"]["total"],
    )


if __name__ == "__main__":
    main()
