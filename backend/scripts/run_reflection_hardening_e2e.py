from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence
from urllib.parse import urlsplit
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine.base import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError
from supabase import create_client


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app  # noqa: E402
from app.modules.reflections.schemas import ReflectionResponse  # noqa: E402
from scripts.run_sample_reflection_e2e import (  # noqa: E402
    COUNT_TABLES,
    LiveRunError,
    SafeEventCollector,
    _string_env,
    active_queue_owners,
    atomic_write_json,
    build_observer_engine,
    build_settings,
    database_snapshot,
    drain_jobs,
    model_usage_report,
    read_only_connection,
    request_json,
    verify_application_database,
    verify_observer_database,
    verify_worker_database,
)


Phase = Literal["baseline", "excluded", "update"]
Expectation = Literal["accepted", "excluded", "api_rejected"]
REQUIRED_CASES = frozenset(
    {
        "blank",
        "hello-testing-mic",
        "exact-duplicate",
        "near-duplicate",
        "copied-informational",
        "task-only",
        "contradiction-one",
        "contradiction-two",
        "prompt-injection",
    }
)
FORBIDDEN_REPORT_KEYS = frozenset({"content", "prompt", "quote", "source_quote"})
POOLER_HOST = re.compile(r"^[a-z0-9.-]+\.pooler\.supabase\.com$")


@dataclass(frozen=True, slots=True)
class HardeningEntry:
    case_id: str
    phase: Phase
    entry_date: str
    content: str
    expected: Expectation


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the bounded authenticated Reflection Engine hardening E2E.",
        allow_abbrev=False,
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend-env", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument(
        "--database-session-pooler-host",
        help="Optional IPv4 Supavisor session host; credentials stay in memory.",
    )
    return parser.parse_args(argv)


def _pooler_database_overrides(env: dict[str, str], host: str | None) -> dict[str, str]:
    if host is None:
        return {}
    normalized_host = host.strip().casefold()
    if not POOLER_HOST.fullmatch(normalized_host):
        raise LiveRunError("INVALID_POOLER_HOST", "The session pooler host is invalid.")
    try:
        project_host = (urlsplit(env.get("SUPABASE_URL", "")).hostname or "").casefold()
    except ValueError as exc:
        raise LiveRunError(
            "INVALID_POOLER_HOST", "The Supabase project reference is invalid."
        ) from exc
    suffix = ".supabase.co"
    project_ref = project_host[: -len(suffix)] if project_host.endswith(suffix) else ""
    if not project_ref or not project_ref.isalnum():
        raise LiveRunError(
            "INVALID_POOLER_HOST", "The Supabase project reference is invalid."
        )
    overrides: dict[str, str] = {}
    for name in (
        "APP_DATABASE_URL",
        "WORKER_DATABASE_URL",
        "ADMIN_APP_DATABASE_URL",
        "ORION_MIGRATION_DATABASE_URL",
    ):
        value = env.get(name, "").strip()
        if not value:
            continue
        try:
            parsed = make_url(value)
        except ArgumentError as exc:
            raise LiveRunError(
                "INVALID_DATABASE_CONFIG",
                "A database URL cannot be routed through the session pooler.",
            ) from exc
        if not parsed.username or not parsed.host or not parsed.database:
            raise LiveRunError(
                "INVALID_DATABASE_CONFIG",
                "A database URL cannot be routed through the session pooler.",
            )
        username_suffix = f".{project_ref}"
        pooler_username = (
            parsed.username
            if parsed.username.endswith(username_suffix)
            else parsed.username + username_suffix
        )
        overrides[name] = parsed.set(
            drivername="postgresql+psycopg",
            host=normalized_host,
            port=5432,
            username=pooler_username,
        ).render_as_string(hide_password=False)
    return overrides


def _build_runtime_settings(
    backend_env: Path,
    user_id: UUID,
    database_overrides: dict[str, str],
):
    previous = {name: os.environ.get(name) for name in database_overrides}
    try:
        os.environ.update(database_overrides)
        return build_settings(backend_env, user_id)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def load_dataset(path: Path) -> tuple[HardeningEntry, ...]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveRunError(
            "INVALID_DATASET", "The hardening dataset is invalid."
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {"entries"}:
        raise LiveRunError("INVALID_DATASET", "The hardening dataset shape is invalid.")
    raw_entries = payload["entries"]
    if not isinstance(raw_entries, list) or not raw_entries:
        raise LiveRunError("INVALID_DATASET", "The hardening dataset is empty.")
    entries: list[HardeningEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict) or set(raw) != {
            "caseId",
            "phase",
            "entryDate",
            "content",
            "expected",
        }:
            raise LiveRunError(
                "INVALID_DATASET", "A hardening case has an invalid shape."
            )
        case_id = raw["caseId"]
        phase = raw["phase"]
        entry_date = raw["entryDate"]
        content = raw["content"]
        expected = raw["expected"]
        if (
            not isinstance(case_id, str)
            or not case_id
            or phase not in {"baseline", "excluded", "update"}
            or not isinstance(entry_date, str)
            or not isinstance(content, str)
            or expected not in {"accepted", "excluded", "api_rejected"}
        ):
            raise LiveRunError(
                "INVALID_DATASET", "A hardening case has invalid values."
            )
        entries.append(
            HardeningEntry(
                case_id=case_id,
                phase=phase,
                entry_date=entry_date,
                content=content,
                expected=expected,
            )
        )
    case_ids = [entry.case_id for entry in entries]
    if len(case_ids) != len(set(case_ids)) or not REQUIRED_CASES.issubset(case_ids):
        raise LiveRunError(
            "INVALID_DATASET", "Required hardening cases are missing or duplicated."
        )
    baseline = [entry for entry in entries if entry.phase == "baseline"]
    update = [entry for entry in entries if entry.phase == "update"]
    if (
        len(baseline) < 3
        or len({entry.entry_date for entry in baseline}) < 2
        or any(entry.expected != "accepted" for entry in baseline)
        or len(update) < 3
        or any(entry.expected != "accepted" for entry in update)
    ):
        raise LiveRunError("INVALID_DATASET", "Accepted phase boundaries are invalid.")
    blank = next(entry for entry in entries if entry.case_id == "blank")
    if blank.content.strip() or blank.expected != "api_rejected":
        raise LiveRunError(
            "INVALID_DATASET", "The blank API rejection case is invalid."
        )
    return tuple(entries)


def _entries_for(
    entries: Sequence[HardeningEntry], phase: Phase
) -> list[HardeningEntry]:
    return [entry for entry in entries if entry.phase == phase]


def _submit(
    client: TestClient,
    token: str,
    entries: Sequence[HardeningEntry],
) -> dict[str, UUID | None]:
    submitted: dict[str, UUID | None] = {}
    for entry in entries:
        response = client.post(
            "/api/v1/past-entries",
            headers={"Authorization": f"Bearer {token}"},
            json={"entry_date": entry.entry_date, "content": entry.content},
        )
        if entry.expected == "api_rejected":
            if response.status_code != 422:
                raise LiveRunError(
                    "API_REJECTION_MISMATCH", "A rejected hardening case was accepted."
                )
            submitted[entry.case_id] = None
            continue
        if response.status_code != 202:
            raise LiveRunError(
                "ENTRY_SUBMISSION_FAILED",
                "A hardening entry was not accepted by the API.",
            )
        body = response.json()
        submitted[entry.case_id] = UUID(str(body["entry_id"]))
    return submitted


def _entry_results(
    observer: Engine,
    user_id: UUID,
    entries: Sequence[HardeningEntry],
    submitted: dict[str, UUID | None],
) -> list[dict[str, Any]]:
    ids = [entry_id for entry_id in submitted.values() if entry_id is not None]
    if not ids:
        return [
            {
                "caseId": entry.case_id,
                "apiStatus": "rejected",
                "expected": entry.expected,
            }
            for entry in entries
        ]
    with read_only_connection(observer) as connection:
        rows = connection.execute(
            text(
                "SELECT e.id, a.eligibility, a.exclusion_reason_codes, "
                "a.reflective_word_count, count(s.id) AS signals, "
                "count(s.embedding) AS embeddings "
                "FROM public.entries e "
                "LEFT JOIN public.entry_analyses a "
                "ON a.entry_id = e.id AND a.user_id = e.user_id "
                "LEFT JOIN public.entry_signals s "
                "ON s.analysis_id = a.id AND s.user_id = a.user_id "
                "WHERE e.user_id = :user_id AND e.id = ANY(:entry_ids) "
                "GROUP BY e.id, a.eligibility, a.exclusion_reason_codes, "
                "a.reflective_word_count"
            ),
            {"user_id": user_id, "entry_ids": ids},
        ).mappings()
        by_id = {UUID(str(row["id"])): row for row in rows}
    result: list[dict[str, Any]] = []
    for entry in entries:
        entry_id = submitted[entry.case_id]
        if entry_id is None:
            result.append(
                {
                    "caseId": entry.case_id,
                    "apiStatus": "rejected",
                    "expected": entry.expected,
                }
            )
            continue
        row = by_id.get(entry_id)
        if row is None:
            raise LiveRunError(
                "ENTRY_RESULT_MISSING", "A hardening entry result is missing."
            )
        actual = str(row["eligibility"])
        if actual != entry.expected:
            raise LiveRunError(
                "ENTRY_EXPECTATION_MISMATCH",
                "A hardening entry outcome was unexpected.",
            )
        result.append(
            {
                "caseId": entry.case_id,
                "entryId": str(entry_id),
                "expected": entry.expected,
                "eligibility": actual,
                "exclusionReasonCodes": list(row["exclusion_reason_codes"] or []),
                "reflectiveWordCount": int(row["reflective_word_count"] or 0),
                "signalCount": int(row["signals"] or 0),
                "embeddingCount": int(row["embeddings"] or 0),
            }
        )
    return result


def _state(observer: Engine, user_id: UUID) -> dict[str, int]:
    with read_only_connection(observer) as connection:
        row = (
            connection.execute(
                text(
                    "SELECT latest_accepted_source_version, last_snapshot_source_version, "
                    "new_valid_entries, new_accepted_signals "
                    "FROM public.reflection_user_state WHERE user_id = :user_id"
                ),
                {"user_id": user_id},
            )
            .mappings()
            .one()
        )
    return {key: int(value or 0) for key, value in row.items()}


def _candidate_state(observer: Engine, user_id: UUID) -> list[dict[str, Any]]:
    with read_only_connection(observer) as connection:
        rows = connection.execute(
            text(
                "SELECT canonical_key, pattern_type, status, score, score_components, version "
                "FROM public.pattern_candidates WHERE user_id = :user_id "
                "ORDER BY pattern_type, canonical_key"
            ),
            {"user_id": user_id},
        ).mappings()
        return [
            {
                "canonicalKey": str(row["canonical_key"]),
                "patternType": str(row["pattern_type"]),
                "status": str(row["status"]),
                "score": float(row["score"]),
                "scoreComponents": dict(row["score_components"]),
                "version": int(row["version"]),
            }
            for row in rows
        ]


def _vector_observations(observer: Engine, user_id: UUID) -> dict[str, Any]:
    with read_only_connection(observer) as connection:
        row = (
            connection.execute(
                text(
                    "WITH pairs AS ("
                    " SELECT left_signal.id AS left_id, right_signal.id AS right_id, "
                    " left_signal.embedding <=> right_signal.embedding AS distance, "
                    " (left_signal.need_tags && right_signal.need_tags "
                    "  OR left_signal.themes && right_signal.themes) AS related "
                    " FROM public.entry_signals left_signal "
                    " JOIN public.entry_signals right_signal "
                    "   ON right_signal.user_id = left_signal.user_id "
                    "  AND right_signal.id > left_signal.id "
                    "  AND right_signal.entry_id <> left_signal.entry_id "
                    " WHERE left_signal.user_id = :user_id "
                    "   AND left_signal.embedding IS NOT NULL "
                    "   AND right_signal.embedding IS NOT NULL"
                    ") SELECT count(*) FILTER (WHERE related) AS related_pairs, "
                    "min(distance) FILTER (WHERE related) AS nearest_related, "
                    "avg(distance) FILTER (WHERE related) AS mean_related, "
                    "count(*) FILTER (WHERE NOT related) AS unrelated_pairs, "
                    "min(distance) FILTER (WHERE NOT related) AS nearest_unrelated, "
                    "avg(distance) FILTER (WHERE NOT related) AS mean_unrelated FROM pairs"
                ),
                {"user_id": user_id},
            )
            .mappings()
            .one()
        )
    return {
        "relatedPairCount": int(row["related_pairs"] or 0),
        "nearestRelatedCosineDistance": _optional_float(row["nearest_related"]),
        "meanRelatedCosineDistance": _optional_float(row["mean_related"]),
        "unrelatedPairCount": int(row["unrelated_pairs"] or 0),
        "nearestUnrelatedCosineDistance": _optional_float(row["nearest_unrelated"]),
        "meanUnrelatedCosineDistance": _optional_float(row["mean_unrelated"]),
    }


def _optional_float(value: object) -> float | None:
    return round(float(value), 6) if value is not None else None


def _candidate_diff(
    before: Sequence[dict[str, Any]], after: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    before_by_key = {str(item["canonicalKey"]): item for item in before}
    result: list[dict[str, Any]] = []
    for current in after:
        previous = before_by_key.get(str(current["canonicalKey"]))
        if previous is None:
            continue
        before_contradiction = float(
            previous["scoreComponents"].get("contradiction", 0)
        )
        after_contradiction = float(current["scoreComponents"].get("contradiction", 0))
        result.append(
            {
                "canonicalKey": current["canonicalKey"],
                "patternType": current["patternType"],
                "beforeScore": previous["score"],
                "afterScore": current["score"],
                "beforeStatus": previous["status"],
                "afterStatus": current["status"],
                "beforeContradiction": before_contradiction,
                "afterContradiction": after_contradiction,
            }
        )
    return result


def _snapshot_summary(payload: dict[str, Any]) -> dict[str, Any]:
    snapshot = payload.get("snapshot") or {}
    basis = payload.get("analysisBasis") or {}
    data = payload.get("data") or {}
    return {
        "snapshotId": snapshot.get("id"),
        "version": snapshot.get("version"),
        "sourceVersion": snapshot.get("sourceVersion"),
        "reflectionState": payload.get("reflectionState"),
        "processingState": payload.get("processingState"),
        "validEntryCount": basis.get("validEntryCount"),
        "excludedEntryCount": basis.get("excludedEntryCount"),
        "distinctEntryDates": basis.get("distinctEntryDates"),
        "reflectiveWordCount": basis.get("reflectiveWordCount"),
        "hiddenDriver": _section_summary(data.get("hiddenDriver")),
        "recurringLoop": _section_summary(data.get("recurringLoop")),
        "innerTensions": _section_summary(data.get("innerTensions")),
    }


def _section_summary(section: object) -> dict[str, Any]:
    if not isinstance(section, dict):
        return {"status": "missing"}
    evidence_ids: list[str] = []
    for key in ("evidence", "counterevidence"):
        value = section.get(key)
        if isinstance(value, list):
            evidence_ids.extend(
                str(item.get("entryId"))
                for item in value
                if isinstance(item, dict) and item.get("entryId")
            )
    tensions = section.get("tensions")
    if isinstance(tensions, list):
        for tension in tensions:
            if not isinstance(tension, dict):
                continue
            for key in ("evidence", "counterevidence"):
                value = tension.get(key)
                if isinstance(value, list):
                    evidence_ids.extend(
                        str(item.get("entryId"))
                        for item in value
                        if isinstance(item, dict) and item.get("entryId")
                    )
    return {
        "status": section.get("status"),
        "confidence": section.get("confidence"),
        "reasonCode": section.get("reasonCode"),
        "evidenceEntryCount": section.get("evidenceEntryCount"),
        "evidenceEntryIds": sorted(set(evidence_ids)),
        "tensionCount": len(tensions) if isinstance(tensions, list) else None,
        "tensionEvidenceEntryCounts": (
            [item.get("evidenceEntryCount") for item in tensions if isinstance(item, dict)]
            if isinstance(tensions, list)
            else None
        ),
    }


def _assert_report_safe(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_REPORT_KEYS:
                raise LiveRunError(
                    "UNSAFE_REPORT", "The hardening report contains content."
                )
            _assert_report_safe(item)
    elif isinstance(value, list):
        for item in value:
            _assert_report_safe(item)


def _cleanup_counts(observer: Engine, user_id: UUID) -> dict[str, int]:
    with read_only_connection(observer) as connection:
        return {
            table: int(
                connection.scalar(
                    text(
                        f"SELECT count(*) FROM public.{table} WHERE user_id = :user_id"
                    ),
                    {"user_id": user_id},
                )
                or 0
            )
            for table in COUNT_TABLES
        }


def run(args: argparse.Namespace) -> dict[str, Any]:
    entries = load_dataset(args.input)
    env = _string_env(args.backend_env)
    database_overrides = _pooler_database_overrides(
        env, args.database_session_pooler_host
    )
    runtime_env = {**env, **database_overrides}
    required = (
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_SECRET_KEY",
        "SUPABASE_TEST_OTHER_EMAIL",
        "SUPABASE_TEST_OTHER_PASSWORD",
    )
    if any(not env.get(name) for name in required):
        raise LiveRunError(
            "TEST_CONFIG_MISSING", "Hardening test configuration is missing."
        )
    admin_client = create_client(env["SUPABASE_URL"], env["SUPABASE_SECRET_KEY"])
    public_client = create_client(env["SUPABASE_URL"], env["SUPABASE_PUBLISHABLE_KEY"])
    observer: Engine | None = None
    user_id: UUID | None = None
    collector = SafeEventCollector()
    telemetry_loggers = (
        logging.getLogger("orion.processing.provider"),
        logging.getLogger("orion.processing.embeddings"),
        logging.getLogger("orion.reflection.provider"),
    )
    for logger in telemetry_loggers:
        logger.addHandler(collector)
    result: dict[str, Any] = {}
    try:
        created = admin_client.auth.admin.create_user(
            {
                "email": env["SUPABASE_TEST_OTHER_EMAIL"],
                "password": env["SUPABASE_TEST_OTHER_PASSWORD"],
                "email_confirm": True,
            }
        )
        if created.user is None:
            raise LiveRunError(
                "AUTH_CREATE_FAILED", "The temporary test identity was not created."
            )
        user_id = UUID(str(created.user.id))
        session = public_client.auth.sign_in_with_password(
            {
                "email": env["SUPABASE_TEST_OTHER_EMAIL"],
                "password": env["SUPABASE_TEST_OTHER_PASSWORD"],
            }
        ).session
        if session is None:
            raise LiveRunError(
                "AUTH_SIGN_IN_FAILED", "The temporary test identity could not sign in."
            )
        token = session.access_token
        settings = _build_runtime_settings(
            args.backend_env, user_id, database_overrides
        )
        verify_application_database(settings, user_id)
        verify_worker_database(settings)
        application = create_app(settings=settings)
        observer = build_observer_engine(runtime_env)
        verify_observer_database(observer, user_id)
        owned_active, foreign_active = active_queue_owners(observer, user_id)
        if (
            owned_active
            or foreign_active
            or any(database_snapshot(observer, user_id)["tableRowCounts"].values())
        ):
            raise LiveRunError(
                "TEST_STATE_NOT_EMPTY", "The hardening test state is not empty."
            )
        deadline = time.monotonic() + args.timeout_seconds

        with TestClient(application, raise_server_exceptions=True) as client:
            baseline_entries = _entries_for(entries, "baseline")
            baseline_submitted = _submit(client, token, baseline_entries)
            baseline_jobs = drain_jobs(
                application, observer, user_id, "entry_processing", deadline=deadline
            )
            if baseline_jobs["failed"]:
                raise LiveRunError(
                    "ENTRY_PROCESSING_FAILED", "Baseline entry processing failed."
                )
            baseline_results = _entry_results(
                observer, user_id, baseline_entries, baseline_submitted
            )
            requested = request_json(
                client,
                "GET",
                "/api/v1/reflections?range=all",
                token=token,
                expected_status=200,
            )
            if requested.get("processingState") != "pending":
                raise LiveRunError(
                    "BASELINE_NOT_SCHEDULED", "Baseline synthesis was not requested."
                )
            baseline_synthesis_jobs = drain_jobs(
                application,
                observer,
                user_id,
                "reflection_synthesis",
                deadline=deadline,
            )
            if baseline_synthesis_jobs["failed"]:
                raise LiveRunError(
                    "REFLECTION_SYNTHESIS_FAILED",
                    "Baseline reflection synthesis failed.",
                )
            before_payload = request_json(
                client,
                "GET",
                "/api/v1/reflections?range=all",
                token=token,
                expected_status=200,
            )
            ReflectionResponse.model_validate(before_payload)
            before_snapshot = _snapshot_summary(before_payload)
            if before_snapshot["snapshotId"] is None:
                raise LiveRunError(
                    "BASELINE_SNAPSHOT_MISSING", "Baseline synthesis made no snapshot."
                )
            before_candidates = _candidate_state(observer, user_id)
            state_after_snapshot = _state(observer, user_id)

            excluded_entries = _entries_for(entries, "excluded")
            excluded_submitted = _submit(client, token, excluded_entries)
            excluded_jobs = drain_jobs(
                application, observer, user_id, "entry_processing", deadline=deadline
            )
            if excluded_jobs["failed"]:
                raise LiveRunError(
                    "ENTRY_PROCESSING_FAILED", "Exclusion entry processing failed."
                )
            excluded_results = _entry_results(
                observer, user_id, excluded_entries, excluded_submitted
            )
            state_after_exclusions = _state(observer, user_id)
            if (
                state_after_exclusions["latest_accepted_source_version"]
                != state_after_snapshot["latest_accepted_source_version"]
                or state_after_exclusions["new_valid_entries"] != 0
                or state_after_exclusions["new_accepted_signals"] != 0
                or any(
                    row.get("signalCount", 0) or row.get("embeddingCount", 0)
                    for row in excluded_results
                )
            ):
                raise LiveRunError(
                    "EXCLUSION_CHANGED_COUNTERS",
                    "Excluded hardening content changed reflection counters or embeddings.",
                )
            exclusion_payload = request_json(
                client,
                "GET",
                "/api/v1/reflections?range=all",
                token=token,
                expected_status=200,
            )
            if (exclusion_payload.get("snapshot") or {}).get("id") != before_snapshot[
                "snapshotId"
            ]:
                raise LiveRunError(
                    "EXCLUSION_CHANGED_SNAPSHOT",
                    "Excluded content changed the snapshot.",
                )

            update_entries = _entries_for(entries, "update")
            update_submitted = _submit(client, token, update_entries)
            update_jobs = drain_jobs(
                application, observer, user_id, "entry_processing", deadline=deadline
            )
            if update_jobs["failed"]:
                raise LiveRunError(
                    "ENTRY_PROCESSING_FAILED", "Update entry processing failed."
                )
            update_results = _entry_results(
                observer, user_id, update_entries, update_submitted
            )
            update_request = request_json(
                client,
                "GET",
                "/api/v1/reflections?range=all",
                token=token,
                expected_status=200,
            )
            if update_request.get("processingState") != "pending":
                raise LiveRunError(
                    "UPDATE_NOT_SCHEDULED", "Updated synthesis was not requested."
                )
            update_synthesis_jobs = drain_jobs(
                application,
                observer,
                user_id,
                "reflection_synthesis",
                deadline=deadline,
            )
            if update_synthesis_jobs["failed"]:
                raise LiveRunError(
                    "REFLECTION_SYNTHESIS_FAILED",
                    "Updated reflection synthesis failed.",
                )
            after_payload = request_json(
                client,
                "GET",
                "/api/v1/reflections?range=all",
                token=token,
                expected_status=200,
            )
            ReflectionResponse.model_validate(after_payload)
            after_snapshot = _snapshot_summary(after_payload)
            if (
                after_snapshot["snapshotId"] is None
                or after_snapshot["snapshotId"] == before_snapshot["snapshotId"]
                or int(after_snapshot["sourceVersion"] or 0)
                <= int(before_snapshot["sourceVersion"] or 0)
            ):
                raise LiveRunError(
                    "UPDATED_SNAPSHOT_MISSING", "The updated snapshot did not advance."
                )
            after_candidates = _candidate_state(observer, user_id)
            candidate_diff = _candidate_diff(before_candidates, after_candidates)
            contradiction_observed = any(
                row["afterContradiction"] > row["beforeContradiction"]
                or row["afterScore"] < row["beforeScore"]
                or row["afterStatus"] in {"weakened", "rejected", "superseded"}
                for row in candidate_diff
            )
            if not before_candidates or not contradiction_observed:
                raise LiveRunError(
                    "CONTRADICTION_NOT_OBSERVED",
                    "Contradictory evidence did not weaken or oppose an existing candidate.",
                )

            vectors = _vector_observations(observer, user_id)
            if (
                vectors["relatedPairCount"] == 0
                or vectors["unrelatedPairCount"] == 0
                or database_snapshot(observer, user_id)["missingEmbeddingCount"] != 0
            ):
                raise LiveRunError(
                    "VECTOR_OBSERVATION_MISSING", "Vector observations are incomplete."
                )

        result = {
            "status": "passed",
            "dataset": {
                "caseCount": len(entries),
                "baselineCount": len(_entries_for(entries, "baseline")),
                "excludedCount": len(_entries_for(entries, "excluded")),
                "updateCount": len(_entries_for(entries, "update")),
            },
            "entries": {
                "baseline": baseline_results,
                "excluded": excluded_results,
                "update": update_results,
            },
            "before": before_snapshot,
            "afterExclusions": {
                "snapshotId": before_snapshot["snapshotId"],
                "state": state_after_exclusions,
            },
            "after": after_snapshot,
            "candidateDiff": candidate_diff,
            "contradictionObserved": contradiction_observed,
            "vectorObservations": vectors,
            "modelUsage": model_usage_report(collector.events),
            "privacy": {
                "authenticatedApiOnly": True,
                "temporaryIdentity": True,
                "reportContainsContent": False,
            },
        }
        _assert_report_safe(result)
        return result
    finally:
        for logger in telemetry_loggers:
            logger.removeHandler(collector)
        if user_id is not None:
            admin_client.auth.admin.delete_user(str(user_id))
            if observer is not None:
                deadline = time.monotonic() + 30
                residual = _cleanup_counts(observer, user_id)
                while any(residual.values()) and time.monotonic() < deadline:
                    time.sleep(0.5)
                    residual = _cleanup_counts(observer, user_id)
                if any(residual.values()):
                    raise LiveRunError(
                        "CLEANUP_FAILED", "Hardening test cleanup was incomplete."
                    )
                result["cleanupResidualRows"] = sum(residual.values())
        if observer is not None:
            observer.dispose()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        result = run(args)
    except LiveRunError as exc:
        failure = {
            "status": "failed",
            "errorCode": exc.code,
            "message": exc.safe_message,
        }
        atomic_write_json(args.output, failure)
        print(json.dumps(failure, sort_keys=True))
        raise SystemExit(1) from exc
    atomic_write_json(args.output, result)
    print(json.dumps({"status": "passed", "output": str(args.output)}))


if __name__ == "__main__":
    main()
