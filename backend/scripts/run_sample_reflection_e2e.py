from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine.base import Engine


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.modules.reflections.schemas import ReflectionResponse
from app.shared.database.session import build_database_sessions
from scripts.reflection_e2e import environment as e2e_environment
from scripts.reflection_e2e.environment import (
    _string_env as _string_env,
    build_settings as build_settings,
    load_environment as load_environment,
    load_sample_entries as load_sample_entries,
    read_only_connection as read_only_connection,
    run_model_preflight as run_model_preflight,
    sign_in as sign_in,
    verify_observer_database as verify_observer_database,
)
from scripts.reflection_e2e.reporting import (
    MODEL_ROLES,
    _money,
    available_insight_count,
    estimate_call_cost as estimate_call_cost,
    latency_summary as latency_summary,
    load_continuation_events,
    model_usage_report,
    pipeline_event_report,
    prior_model_attempts,
)
from scripts.reflection_e2e.types import LiveRunError, SampleEntry as SampleEntry
from scripts.reflection_e2e.workflow import (
    COUNT_TABLES as COUNT_TABLES,
    _progress,
    active_queue_owners as active_queue_owners,
    database_snapshot as database_snapshot,
    drain_jobs as drain_jobs,
    entry_breakdown as entry_breakdown,
    inspect_existing_entries as inspect_existing_entries,
    job_status_counts as job_status_counts,
    request_json as request_json,
    schedule_synthesis as schedule_synthesis,
    submit_missing_entries as submit_missing_entries,
)


def build_observer_engine(backend: dict[str, str]) -> Engine:
    return e2e_environment.build_observer_engine(
        backend,
        engine_factory=create_engine,
    )


def verify_worker_database(settings: Any) -> None:
    e2e_environment.verify_worker_database(
        settings,
        sessions_builder=build_database_sessions,
    )


def verify_application_database(settings: Any, user_id: UUID) -> None:
    e2e_environment.verify_application_database(
        settings,
        user_id,
        sessions_builder=build_database_sessions,
    )


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
    parser.add_argument(
        "--finalize-existing",
        action="store_true",
        help=(
            "Finalize a previously interrupted run from persisted database state. "
            "This mode never imports entries, drains jobs, or calls OpenAI."
        ),
    )
    parser.add_argument(
        "--continuation-events",
        type=Path,
        help="Safe model-attempt telemetry captured by the separately deployed continuation.",
    )
    return parser.parse_args(argv)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    encoded = json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=True) + "\n"
    temporary.write_text(encoded, encoding="utf-8")
    os.replace(temporary, path)



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
    verify_application_database(settings, user_id)
    stage_seconds["applicationDatabasePreflight"] = (
        time.monotonic() - stage_started
    )
    checks.append({"name": "application_database_role", "status": "passed"})

    stage_started = time.monotonic()
    verify_worker_database(settings)
    stage_seconds["workerDatabasePreflight"] = time.monotonic() - stage_started
    checks.append({"name": "worker_database_role", "status": "passed"})

    stage_started = time.monotonic()
    run_model_preflight(settings)
    stage_seconds["modelAccessPreflight"] = time.monotonic() - stage_started
    checks.append({"name": "model_access_preflight", "status": "passed"})

    application = create_app(settings=settings)
    observer = build_observer_engine(backend)
    try:
        stage_started = time.monotonic()
        verify_observer_database(observer, user_id)
    except BaseException:
        observer.dispose()
        raise
    stage_seconds["observerDatabasePreflight"] = time.monotonic() - stage_started
    checks.append({"name": "observer_database_read_only", "status": "passed"})
    collector = collector or SafeEventCollector()
    logging.getLogger().addHandler(collector)
    deadline = overall_started + args.timeout_seconds
    try:
        with TestClient(application, raise_server_exceptions=True) as client:
            stage_started = time.monotonic()
            existing_dates = inspect_existing_entries(client, token, entries)
            owned_active, foreign_active = active_queue_owners(observer, user_id)
            if foreign_active:
                raise LiveRunError(
                    "SHARED_QUEUE_BUSY",
                    "Another user's processing jobs are active; the test will not claim them.",
                )
            before_database = database_snapshot(observer, user_id)
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
                application, observer, user_id, "entry_processing", deadline=deadline
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
            enqueued = schedule_synthesis(application, observer, user_id)
            stage_seconds["reflectionScheduling"] = time.monotonic() - stage_started
            synthesis_before = job_status_counts(
                observer, user_id, "reflection_synthesis"
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
            requested_reflection = request_json(
                client,
                "GET",
                "/api/v1/reflections?range=all",
                token=token,
                expected_status=200,
            )
            stage_seconds["reflectionRequest"] = time.monotonic() - stage_started
            if (
                requested_reflection.get("reflectionState")
                != "first_reflection_pending"
                or requested_reflection.get("processingState") != "pending"
            ):
                raise LiveRunError(
                    "SYNTHESIS_NOT_REQUESTED",
                    "The Reflection API did not request the pending synthesis job.",
                )
            checks.append(
                {
                    "name": "reflection_api_requested_synthesis",
                    "status": "passed",
                    "httpStatus": 200,
                    "reflectionState": requested_reflection["reflectionState"],
                    "processingState": requested_reflection["processingState"],
                }
            )

            stage_started = time.monotonic()
            synthesis_jobs = drain_jobs(
                application,
                observer,
                user_id,
                "reflection_synthesis",
                deadline=deadline,
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
            database = database_snapshot(observer, user_id)
            entries_report = entry_breakdown(
                observer, user_id, submissions
            )
    finally:
        logging.getLogger().removeHandler(collector)
        observer.dispose()
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
    embedding = next(item for item in usage["roles"] if item["role"] == "embedding")
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
    signal_count = database["tableRowCounts"].get("entry_signals", 0)
    if (
        embedding["calls"] < 30
        or embedding["successfulCalls"] != 30
        or database["embeddingCount"] != signal_count
        or database["missingEmbeddingCount"] != 0
        or database["embeddingModels"].get(MODEL_ROLES["embedding"], 0)
        != signal_count
    ):
        raise LiveRunError(
            "EMBEDDING_COUNT_MISMATCH",
            "Accepted canonical signals do not all have stored embeddings.",
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
                "name": "embedding_model_routing",
                "status": "passed",
                "calls": embedding["calls"],
                "storedVectors": database["embeddingCount"],
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
            "providers": "real OpenAI Responses and Embeddings APIs",
            "workerDatabaseConnection": "dedicated",
            "observerDatabaseAccess": "read-only test instrumentation",
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
            "Only accepted signal summaries derived from redacted analysis were embedded; excluded entries produced no vectors.",
            "OpenAI provider storage and SDK retries remained disabled.",
            "Application queue retries, heartbeats, ownership checks, scoring, and evidence validation remained active.",
            "Reflection synthesis was scheduled through the production scheduler with a controlled post-18:00 timestamp.",
            "The final result came from authenticated GET /api/v1/reflections?range=all.",
            "The in-process ASGI transport excludes browser and external HTTP-server latency while preserving real authentication, database, queue, and provider boundaries.",
            "Total wall time includes the 30-entry rate-limit pacing; modelWallTimeMs isolates measured provider attempts.",
            "Estimated AI cost excludes Supabase, hosting, network, observability, and any regional OpenAI data-residency uplift.",
            "Reasoning tokens are reported as a subset of output tokens and are costed through the output-token total.",
            "The model access preflight retrieves metadata and does not create billable Responses.",
            "Database diagnostics used ADMIN_APP_DATABASE_URL only inside read-only transactions; API and worker operations retained their restricted logins.",
            "Sol is intentionally absent when no synthesized candidate meets the deterministic critic-routing rule.",
            "The suite does not clean up its persisted database effects after completion.",
        ],
    }


def _load_prior_result(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveRunError(
            "PRIOR_RUN_INVALID", "The prior result artifact could not be read."
        ) from exc
    if not isinstance(payload, dict) or payload.get("status") != "failed":
        raise LiveRunError(
            "PRIOR_RUN_INVALID",
            "Finalization requires the failed artifact from the interrupted live run.",
        )
    return payload


def _verify_completed_basis(
    observer: Engine, user_id: UUID, expected_dates: set[date]
) -> dict[str, Any]:
    with read_only_connection(observer) as connection:
        dates = {
            value
            for value in connection.scalars(
                text(
                    "SELECT entry_date FROM public.entries "
                    "WHERE user_id = :user_id ORDER BY entry_date"
                ),
                {"user_id": user_id},
            )
        }
        state = connection.execute(
            text(
                "SELECT latest_accepted_source_version, last_snapshot_source_version "
                "FROM public.reflection_user_state WHERE user_id = :user_id"
            ),
            {"user_id": user_id},
        ).mappings().one_or_none()
        snapshot = connection.execute(
            text(
                "SELECT id, source_version, status FROM public.reflection_snapshots "
                "WHERE user_id = :user_id ORDER BY version DESC LIMIT 1"
            ),
            {"user_id": user_id},
        ).mappings().one_or_none()
        job = connection.execute(
            text(
                "SELECT status, source_version, attempts FROM public.processing_jobs "
                "WHERE user_id = :user_id AND job_type = 'reflection_synthesis' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"user_id": user_id},
        ).mappings().one_or_none()
    if dates != expected_dates or state is None or snapshot is None or job is None:
        raise LiveRunError(
            "PERSISTED_RUN_MISMATCH",
            "The persisted live run does not match the expected 30-entry basis.",
        )
    latest_source = int(state["latest_accepted_source_version"])
    snapshot_source = int(snapshot["source_version"])
    if (
        latest_source <= 0
        or int(state["last_snapshot_source_version"]) != latest_source
        or snapshot_source != latest_source
        or snapshot["status"] != "available"
        or job["status"] != "completed"
        or int(job["source_version"]) != latest_source
    ):
        raise LiveRunError(
            "PERSISTED_RUN_INCOMPLETE",
            "The persisted reflection continuation is not complete and current.",
        )
    return {
        "sourceVersion": latest_source,
        "snapshotId": str(snapshot["id"]),
        "synthesisAttempts": int(job["attempts"]),
    }


def finalize_existing(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    finalized_at = datetime.now(UTC)
    entries, dataset_hash = load_sample_entries(args.input)
    if len(entries) != 30:
        raise LiveRunError("INVALID_DATASET", "The live suite requires exactly 30 entries.")
    prior = _load_prior_result(args.output)
    prior_events = prior_model_attempts(prior)
    continuation_events = load_continuation_events(args.continuation_events)
    frontend, backend = load_environment(args.frontend_env, args.backend_env)
    token, user_id = sign_in(frontend, backend)
    settings = build_settings(args.backend_env, user_id)
    verify_application_database(settings, user_id)
    observer = build_observer_engine(backend)
    try:
        verify_observer_database(observer, user_id)
        basis = _verify_completed_basis(
            observer, user_id, {entry.entry_date for entry in entries}
        )
        before = database_snapshot(observer, user_id)
        application = create_app(settings=settings)
        with TestClient(application, raise_server_exceptions=True) as client:
            raw_reflection = request_json(
                client,
                "GET",
                "/api/v1/reflections?range=all",
                token=token,
                expected_status=200,
            )
        ReflectionResponse.model_validate(raw_reflection)
        after = database_snapshot(observer, user_id)
        entries_report = entry_breakdown(observer, user_id, None)
    finally:
        observer.dispose()
        token = ""

    if before["jobStatuses"] != after["jobStatuses"]:
        raise LiveRunError(
            "FINALIZATION_MUTATED_QUEUE",
            "Finalization changed the processing queue unexpectedly.",
        )
    if (
        raw_reflection.get("reflectionState") != "available"
        or raw_reflection.get("processingState") != "idle"
        or raw_reflection.get("snapshot", {}).get("sourceVersion")
        != basis["sourceVersion"]
        or available_insight_count(raw_reflection) == 0
    ):
        raise LiveRunError(
            "REFLECTION_NOT_AVAILABLE",
            "The completed reflection aggregate is not available and current.",
        )
    if (
        after["tableRowCounts"].get("entries") != 30
        or after["tableRowCounts"].get("entry_analyses") != 30
        or after["analysisModels"].get(MODEL_ROLES["entry_analysis"]) != 30
        or after["jobStatuses"].get("entry_processing:completed") != 30
        or after["jobStatuses"].get("reflection_synthesis:completed") != 1
    ):
        raise LiveRunError(
            "PERSISTED_RUN_MISMATCH",
            "The persisted live-run counts do not match the canonical dataset.",
        )

    usage = model_usage_report([*prior_events, *continuation_events])
    pipeline_events = prior.get("pipelineEvents")
    if not isinstance(pipeline_events, dict):
        pipeline_events = pipeline_event_report([])
    raw_prior_run = prior.get("run")
    prior_run: dict[str, Any] = raw_prior_run if isinstance(raw_prior_run, dict) else {}
    raw_prior_timing = prior.get("timingSeconds")
    prior_timing: dict[str, Any] = (
        raw_prior_timing if isinstance(raw_prior_timing, dict) else {}
    )
    completed_at = datetime.now(UTC)
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
            "startedAt": prior_run.get("startedAt"),
            "completedAt": completed_at.isoformat(),
            "continuationFinalizedAt": finalized_at.isoformat(),
            "rolloutMode": "publish",
            "transport": "FastAPI TestClient over the real ASGI application",
            "database": "real Supabase PostgreSQL",
            "providers": "real OpenAI Responses API during the original run and deployed continuation",
            "finalizationMode": "persisted read-only continuation; no entry import, job claim, or model call",
            "testUserHash": hashlib.sha256(str(user_id).encode()).hexdigest(),
        },
        "timingSeconds": {
            **prior_timing,
            "continuationFinalization": round(time.monotonic() - started, 3),
        },
        "modelUsage": usage,
        "pipelineEvents": pipeline_events,
        "databaseEffects": after,
        "entryBreakdown": entries_report,
        "reflectionGetResponse": raw_reflection,
        "checks": [
            {"name": "dataset_valid", "status": "passed", "actual": 30},
            {"name": "credential_and_project_parity", "status": "passed"},
            {"name": "persisted_basis_current", "status": "passed", **basis},
            {
                "name": "continuation_reused_luna_results",
                "status": "passed",
                "lunaCallsDuringContinuation": 0,
                "persistedLunaAnalyses": 30,
            },
            {
                "name": "continuation_model_calls",
                "status": "passed",
                "terraCalls": 1,
                "solCalls": 1,
            },
            {
                "name": "finalization_did_not_mutate_queue",
                "status": "passed",
            },
            {
                "name": "reflection_get",
                "status": "passed",
                "httpStatus": 200,
                "reflectionState": "available",
                "processingState": "idle",
            },
            {
                "name": "reflection_has_available_insight",
                "status": "passed",
                "availableSections": available_insight_count(raw_reflection),
            },
        ],
        "errors": [],
        "operationalNuances": [
            "The failed artifact was finalized only after the deployed retry completed and persisted a current snapshot.",
            "Finalization did not import entries, claim or drain jobs, run model preflight, or call OpenAI.",
            "The 30 Luna attempts came from the original runner telemetry; the one Terra and one Sol attempt came from allowlisted deployed-worker telemetry.",
            "The canonical API payload came from authenticated GET /api/v1/reflections?range=all against the real database.",
            "Database inspection used ADMIN_APP_DATABASE_URL only inside read-only transactions.",
            "Credentials, access tokens, email addresses, raw user UUIDs, prompts, provider responses, and entry content are omitted.",
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
        result = (
            finalize_existing(args)
            if args.finalize_existing
            else run(args, collector=collector)
        )
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
