from __future__ import annotations

import json
import os
import socket
import time
from collections import Counter
from datetime import UTC, date, datetime, time as wall_time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine.base import Engine

from scripts.reflection_e2e.environment import read_only_connection
from scripts.reflection_e2e.reporting import _grouped_counts, _two_key_counts
from scripts.reflection_e2e.types import LiveRunError, SampleEntry


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


def _progress(stage: str, **values: Any) -> None:
    print(json.dumps({"stage": stage, **values}, separators=(",", ":")), flush=True)


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


def active_queue_owners(observer: Engine, user_id: UUID) -> tuple[int, int]:
    with read_only_connection(observer) as connection:
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


def job_status_counts(observer: Engine, user_id: UUID, job_type: str) -> Counter[str]:
    with read_only_connection(observer) as connection:
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
    observer: Engine,
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
        _owned_active, foreign_active = active_queue_owners(observer, user_id)
        if foreign_active:
            raise LiveRunError(
                "SHARED_QUEUE_BUSY",
                "Another user's processing job appeared; the test will not claim it.",
            )
        statuses = job_status_counts(observer, user_id, job_type)
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


def schedule_synthesis(application: Any, observer: Engine, user_id: UUID) -> int:
    uow = application.state.database_sessions.unit_of_work_factory
    with read_only_connection(observer) as connection:
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


def database_snapshot(observer: Engine, user_id: UUID) -> dict[str, Any]:
    with read_only_connection(observer) as connection:
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
        embedding_count = int(
            connection.scalar(
                text(
                    "SELECT count(*) FROM public.entry_signals "
                    "WHERE user_id = :user_id AND embedding IS NOT NULL"
                ),
                {"user_id": user_id},
            )
            or 0
        )
        missing_embedding_count = int(
            connection.scalar(
                text(
                    "SELECT count(*) FROM public.entry_signals "
                    "WHERE user_id = :user_id AND embedding IS NULL"
                ),
                {"user_id": user_id},
            )
            or 0
        )
        embedding_models = _grouped_counts(
            connection,
            "SELECT embedding_model AS key, count(*) AS count "
            "FROM public.entry_signals WHERE user_id = :user_id "
            "AND embedding IS NOT NULL GROUP BY embedding_model",
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
        "embeddingCount": embedding_count,
        "missingEmbeddingCount": missing_embedding_count,
        "embeddingModels": embedding_models,
        "jobStatuses": jobs,
        "candidateStatuses": candidates,
        "insightStatuses": insights,
    }


def entry_breakdown(
    observer: Engine,
    user_id: UUID,
    submissions: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    submitted_by_id = (
        {str(item["entryId"]): item for item in submissions}
        if submissions is not None
        else None
    )
    with read_only_connection(observer) as connection:
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
        submission = (
            submitted_by_id.get(entry_id) if submitted_by_id is not None else None
        )
        if submitted_by_id is not None and submission is None:
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
                "submission": submission
                or {
                    "evidence": "persisted_database_state",
                    "note": "The original authenticated import completed before finalization.",
                },
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
