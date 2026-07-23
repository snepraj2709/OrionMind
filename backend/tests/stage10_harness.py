from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import psycopg
import uvicorn
from psycopg import sql

from app.main import create_app
from app.modules.entries import service as entry_service_module
from app.modules.processing.redaction import PiiRedactor
from app.modules.processing.schemas import ModelEntryAnalysis
from tests.test_review_reflection_flow import (
    ENTRY_IDS,
    GENUINE_ENTRIES,
    OTHER_ID,
    OWNER_ID,
    ControlledAnalysisProvider,
    ControlledEmbeddingProvider,
    NoopAnalyzer,
    _cipher,
    _reset_and_migrate,
    _settings,
)
from scripts.run_sample_reflection_offline import OfflineReflectionProvider


API_ORIGIN = "http://127.0.0.1:3101"


def _database_url() -> str:
    value = os.environ.get("STAGE2_DISPOSABLE_DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("STAGE2_DISPOSABLE_DATABASE_URL is required")
    parsed = urlsplit(value)
    if parsed.path != "/orion_stage2_test" or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
    }:
        raise RuntimeError(
            "Stage 10 requires the exact local disposable database "
            "orion_stage2_test"
        )
    return value


class BrowserTokenVerifier:
    def verify_access_token(self, token: str) -> str:
        try:
            _header, payload, _signature = token.split(".")
            padding = "=" * (-len(payload) % 4)
            claims = json.loads(
                base64.urlsafe_b64decode(f"{payload}{padding}").decode("utf-8")
            )
            user_id = UUID(str(claims["sub"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("invalid synthetic browser token") from exc
        if user_id not in {OWNER_ID, OTHER_ID}:
            raise RuntimeError("synthetic browser token owner is not allowed")
        return str(user_id)


class Stage10AnalysisProvider(ControlledAnalysisProvider):
    def __init__(self, *, first_call_delay_seconds: float = 0) -> None:
        super().__init__()
        self._first_call_delay_seconds = first_call_delay_seconds
        self._delayed = False

    def analyze(self, **kwargs: Any) -> ModelEntryAnalysis:
        if self._first_call_delay_seconds > 0 and not self._delayed:
            self._delayed = True
            time.sleep(self._first_call_delay_seconds)
        result = super().analyze(**kwargs)
        payload = result.model_dump(mode="python")
        if payload["signals"]:
            label = payload["signals"][0]["normalized_label"]
            payload["signals"][0]["interpretation"] = (
                f"Supported Stage 10 insight: {label}."
            )
        if kwargs["redacted_text"] == GENUINE_ENTRIES[0][1]:
            payload["legacy"]["ideas"] = [
                {"source_segment_id": "segment_0002"}
            ]
            payload["legacy"]["memories"] = [
                {"source_segment_id": "segment_0003"}
            ]
        return ModelEntryAnalysis.model_validate(payload)


@dataclass(slots=True)
class Harness:
    application: Any
    analysis_provider: Stage10AnalysisProvider
    embedding_provider: ControlledEmbeddingProvider
    reflection_provider: OfflineReflectionProvider


def _build_harness(
    *,
    reset_database: bool,
    first_call_delay_seconds: float = 0,
) -> Harness:
    database_url = _database_url()
    if reset_database:
        _reset_and_migrate(database_url)

    settings = _settings(database_url).model_copy(
        update={
            "CORS_ALLOW_ORIGINS": API_ORIGIN,
            "PROCESSING_JOB_POLL_SECONDS": 0.1,
            "PROCESSING_JOB_RECOVERY_INTERVAL_SECONDS": 10.0,
            "PROCESSING_JOB_STALE_SECONDS": 60,
        }
    )
    cipher = _cipher()
    analysis_provider = Stage10AnalysisProvider(
        first_call_delay_seconds=first_call_delay_seconds
    )
    embedding_provider = ControlledEmbeddingProvider()
    reflection_provider = OfflineReflectionProvider()
    application = create_app(
        settings=settings,
        token_verifier=BrowserTokenVerifier(),
        extraction_provider=analysis_provider,
        embedding_provider=embedding_provider,
        reflection_provider=reflection_provider,
        content_cipher=cipher,
        pii_redactor=PiiRedactor(analyzer=NoopAnalyzer(), cipher=cipher),
    )
    if reset_database:
        stable_ids = iter(ENTRY_IDS)
        original_uuid4 = entry_service_module.uuid4

        def next_entry_id() -> UUID:
            try:
                return next(stable_ids)
            except StopIteration:
                return original_uuid4()

        entry_service_module.uuid4 = next_entry_id
    return Harness(
        application=application,
        analysis_provider=analysis_provider,
        embedding_provider=embedding_provider,
        reflection_provider=reflection_provider,
    )


def _dispose(application: Any) -> None:
    application.state.database_sessions.dispose()
    tracer_provider = getattr(application.state, "tracer_provider", None)
    if tracer_provider is not None:
        tracer_provider.shutdown()
    meter_provider = getattr(application.state, "meter_provider", None)
    if meter_provider is not None:
        meter_provider.shutdown()


def run_server(port: int) -> None:
    harness = _build_harness(reset_database=True)
    try:
        uvicorn.run(
            harness.application,
            host="127.0.0.1",
            port=port,
            access_log=False,
            log_level="warning",
        )
    finally:
        _dispose(harness.application)


def run_worker(
    *,
    first_call_delay_seconds: float,
) -> None:
    harness = _build_harness(
        reset_database=False,
        first_call_delay_seconds=first_call_delay_seconds,
    )
    application = harness.application
    sessions = application.state.database_sessions
    worker = application.state.processing_worker
    try:
        worker.run(
            worker_id=f"stage-10-worker-{os.getpid()}",
            uow=sessions.unit_of_work_factory,
        )
    finally:
        print(
            json.dumps(
                {
                    "analysisCalls": len(harness.analysis_provider.calls),
                    "criticCalls": harness.reflection_provider.critic_calls,
                    "embeddingCalls": len(harness.embedding_provider.calls),
                    "synthesisCalls": harness.reflection_provider.synthesis_calls,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        _dispose(application)


def age_running_jobs(*, seconds: int) -> None:
    with psycopg.connect(_database_url()) as connection:
        rows = connection.execute(
            "UPDATE public.processing_jobs "
            "SET heartbeat_at = pg_catalog.now() - "
            "pg_catalog.make_interval(secs => %s) "
            "WHERE status = 'running' "
            "RETURNING id",
            (seconds,),
        ).fetchall()
    print(json.dumps({"agedJobs": len(rows)}, sort_keys=True))


def _json_default(value: object) -> str:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return str(value)


def _state_digest(connection: psycopg.Connection[Any]) -> str:
    state: dict[str, list[dict[str, object]]] = {}
    table_names = connection.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
        "ORDER BY table_name"
    ).fetchall()
    for (name,) in table_names:
        cursor = connection.execute(
            sql.SQL("SELECT * FROM public.{}").format(sql.Identifier(name))
        )
        columns = tuple(column.name for column in cursor.description or ())
        rows = [
            dict(zip(columns, row, strict=True)) for row in cursor.fetchall()
        ]
        state[name] = sorted(
            rows,
            key=lambda row: json.dumps(
                row,
                default=_json_default,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
    payload = json.dumps(
        state,
        default=_json_default,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def inspect_database() -> None:
    with psycopg.connect(_database_url()) as connection:
        row = connection.execute(
            "SELECT "
            "(SELECT count(*) FROM public.processing_jobs), "
            "(SELECT count(*) FROM public.processing_jobs "
            " WHERE status <> 'completed'), "
            "(SELECT count(*) FROM public.reflection_snapshots "
            " WHERE user_id = %s), "
            "(SELECT count(*) FROM public.review_items "
            " WHERE user_id = %s AND scope = 'entry_insight'), "
            "(SELECT count(*) FROM public.review_items "
            " WHERE user_id = %s AND scope = 'pattern'), "
            "(SELECT count(*) FROM public.entries "
            " WHERE user_id = %s AND processing_status = 'completed')",
            (OWNER_ID, OWNER_ID, OWNER_ID, OWNER_ID),
        ).fetchone()
        state_digest = _state_digest(connection)
    assert row is not None
    print(
        json.dumps(
            {
                "jobs": int(row[0]),
                "nonCompletedJobs": int(row[1]),
                "snapshots": int(row[2]),
                "entryReviewItems": int(row[3]),
                "patternReviewItems": int(row[4]),
                "completedEntries": int(row[5]),
                "stateDigest": state_digest,
            },
            sort_keys=True,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    server = subparsers.add_parser("server")
    server.add_argument("--port", type=int, default=18080)
    worker = subparsers.add_parser("worker")
    worker.add_argument("--first-call-delay-seconds", type=float, default=0)
    age_stale = subparsers.add_parser("age-stale")
    age_stale.add_argument("--seconds", type=int, default=61)
    subparsers.add_parser("inspect")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "server":
        run_server(args.port)
    elif args.command == "worker":
        run_worker(
            first_call_delay_seconds=args.first_call_delay_seconds,
        )
    elif args.command == "age-stale":
        age_running_jobs(seconds=args.seconds)
    else:
        inspect_database()


if __name__ == "__main__":
    main()
