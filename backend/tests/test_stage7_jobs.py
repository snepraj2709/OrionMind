from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import SecretStr, ValidationError
from psycopg import sql

from app.main import create_app
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.schemas import ProcessingJob
from app.modules.processing.schemas import ModelEntryExtraction
from app.shared.config import Settings
from app.shared.database.session import build_database_sessions
from app.shared.security.encryption import AesGcmContentCipher
from scripts.migrate import apply_migrations, load_migrations


ROOT = Path(__file__).resolve().parents[1]
USER_ONE = UUID("91111111-1111-4111-8111-111111111111")
USER_TWO = UUID("92222222-2222-4222-8222-222222222222")
CONFIG_ID = UUID("00000000-0000-0000-0000-000000000801")


def database_url() -> str:
    value = os.environ.get("STAGE2_DISPOSABLE_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("STAGE2_DISPOSABLE_DATABASE_URL is not configured")
    parsed = urlsplit(value)
    if parsed.path != "/orion_stage2_test" or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
    }:
        pytest.fail("job tests require the exact local disposable database")
    return value


def reset(value: str) -> None:
    parsed = urlsplit(value)
    maintenance = urlunsplit(
        (parsed.scheme, parsed.netloc, "/postgres", parsed.query, parsed.fragment)
    )
    name = parsed.path.removeprefix("/")
    with psycopg.connect(maintenance, autocommit=True) as connection:
        connection.execute(
            "SELECT pg_catalog.pg_terminate_backend(pid) "
            "FROM pg_catalog.pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_catalog.pg_backend_pid()",
            (name,),
        )
        connection.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def bootstrap(value: str) -> None:
    reset(value)
    with psycopg.connect(value) as connection:
        connection.execute((ROOT / "tests/sql/bootstrap_auth.sql").read_text(), prepare=False)
        connection.execute(
            "INSERT INTO auth.users (id) VALUES (%s), (%s)",
            (USER_ONE, USER_TWO),
        )
        connection.commit()
    apply_migrations(value, load_migrations(ROOT / "migrations"))


def cipher() -> AesGcmContentCipher:
    return AesGcmContentCipher(
        encryption_keys={"entry-key": b"e" * 32},
        active_encryption_key_id="entry-key",
        fingerprint_keys={"fingerprint-key": b"f" * 32},
        active_fingerprint_key_id="fingerprint-key",
    )


def insert_entry(
    connection: psycopg.Connection,
    *,
    user_id: UUID,
    content: str,
    status: str = "pending",
    materialized: bool = False,
) -> UUID:
    entry_id = uuid4()
    envelope = cipher().encrypt(content, user_id=user_id, record_id=entry_id)
    connection.execute(
        "INSERT INTO public.entries "
        "(id, user_id, content_envelope, input_type, entry_date, "
        "original_theme_config_id, processing_status, completed_at) "
        "VALUES (%s, %s, %s::jsonb, 'text', CURRENT_DATE, %s, %s, "
        "CASE WHEN %s = 'completed' THEN pg_catalog.now() ELSE NULL END)",
        (entry_id, user_id, json.dumps(envelope), CONFIG_ID, status, status),
    )
    if materialized:
        connection.execute(
            "INSERT INTO public.entry_classifications "
            "(user_id, entry_id, theme_config_id, source, mode) "
            "VALUES (%s, %s, %s, 'initial', NULL)",
            (user_id, entry_id, CONFIG_ID),
        )
    return entry_id


def enqueue_owner(connection: psycopg.Connection, user_id: UUID, entry_id: UUID) -> UUID:
    connection.execute("SET LOCAL ROLE authenticated")
    connection.execute(
        "SELECT pg_catalog.set_config('request.jwt.claims', %s, true)",
        (json.dumps({"sub": str(user_id), "role": "authenticated"}),),
    )
    return connection.execute(
        "SELECT public.enqueue_processing_job_for_owner(%s, %s, %s)",
        (user_id, entry_id, str(entry_id)),
    ).fetchone()[0]


def worker(connection: psycopg.Connection) -> None:
    connection.execute("SET LOCAL ROLE orion_worker")


class Provider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.entered = Event()
        self.release = Event()
        self.block = False

    def extract(self, *, content: str, themes) -> ModelEntryExtraction:
        self.calls.append(content)
        if self.block:
            self.entered.set()
            if not self.release.wait(timeout=5):
                raise RuntimeError("test provider release timed out")
        return ModelEntryExtraction.model_validate(
            {
                "ideas": [],
                "memories": [],
                "theme": {"mode": None, "themes": []},
                "reflection": {
                    "filled_energy": None,
                    "drained_energy": None,
                    "learned_about_self": None,
                },
            }
        )


def application(value: str, provider: Provider):
    sqlalchemy_url = value.replace("postgresql://", "postgresql+psycopg://", 1)
    settings = Settings.model_validate(
        {
            "ENVIRONMENT": "test",
            "APP_DATABASE_URL": SecretStr(sqlalchemy_url),
            "WORKER_DATABASE_URL": SecretStr(sqlalchemy_url),
            "CORS_ALLOW_ORIGINS": "https://app.example.test",
            "LOG_FORMAT": "text",
            "RATE_LIMITING_ENABLED": False,
            "PROCESSING_JOB_HEARTBEAT_SECONDS": 1,
        }
    )
    return create_app(
        settings=settings,
        database_sessions=build_database_sessions(settings),
        extraction_provider=provider,
        content_cipher=cipher(),
    )


def test_processing_job_schema_rejects_unknown_values_and_invalid_lifecycle() -> None:
    now = datetime.now(timezone.utc) - timedelta(seconds=1)
    valid = {
        "id": uuid4(),
        "user_id": USER_ONE,
        "entry_id": uuid4(),
        "job_type": "entry_processing",
        "source_version": "",
        "status": "pending",
        "run_after": now,
        "attempts": 0,
    }
    valid["source_version"] = str(valid["entry_id"])
    assert ProcessingJob.model_validate(valid).status == "pending"
    for changes in (
        {"job_type": "entry"},
        {"status": "queued"},
        {"attempts": 4},
        {"source_version": str(uuid4())},
        {"worker_id": "worker"},
    ):
        with pytest.raises(ValidationError):
            ProcessingJob.model_validate({**valid, **changes})


def test_claim_race_heartbeat_exact_backoff_and_stale_token_rejection() -> None:
    value = database_url()
    bootstrap(value)
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT pg_catalog.to_regprocedure(name) IS NULL "
            "FROM unnest(ARRAY["
            "'public.claim_past_entry_import(text)', "
            "'public.renew_past_entry_import(uuid,text,uuid)', "
            "'public.recover_stale_past_entry_imports(timestamptz)', "
            "'public.complete_past_entry_import(uuid,text,uuid)', "
            "'public.apply_past_entry_extraction(uuid,text,uuid,uuid,text,jsonb,jsonb,jsonb,jsonb)'"
            "]) AS name"
        ).fetchall() == [(True,)] * 5
        first_entry = insert_entry(connection, user_id=USER_ONE, content="first")
        second_entry = insert_entry(connection, user_id=USER_TWO, content="second")
        connection.commit()
        with connection.transaction():
            first_job = enqueue_owner(connection, USER_ONE, first_entry)
        with connection.transaction():
            second_job = enqueue_owner(connection, USER_TWO, second_entry)
        with connection.transaction():
            assert enqueue_owner(connection, USER_TWO, second_entry) == second_job

    repository = JobRepository()
    provider = Provider()
    app = application(value, provider)
    uow = app.state.database_sessions.unit_of_work_factory

    def claim(worker_id: str):
        with uow.for_worker() as work:
            return repository.claim(work.session, worker_id=worker_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ("worker-a", "worker-b")))
    assert all(item is not None for item in claims)
    current = [item for item in claims if item is not None]
    assert {item.job_id for item in current} == {first_job, second_job}
    assert len({item.claim_token for item in current}) == 2

    first = current[0]
    with uow.for_worker() as work:
        assert repository.renew(work.session, claim=first, worker_id="worker-a") is True
    # Resolve the actual claimant worker ID without depending on race ordering.
    with psycopg.connect(value) as connection:
        actual_worker = connection.execute(
            "SELECT worker_id FROM public.processing_jobs WHERE id = %s", (first.job_id,)
        ).fetchone()[0]
        connection.execute(
            "UPDATE public.processing_jobs SET heartbeat_at = pg_catalog.now() - interval '10 minutes' "
            "WHERE id = %s",
            (first.job_id,),
        )
        connection.commit()
    with uow.for_worker() as work:
        assert repository.recover(
            work.session, stale_before=datetime.now(timezone.utc) - timedelta(minutes=5)
        ) == 1
        assert repository.fail(
            work.session,
            claim=first,
            worker_id=actual_worker,
            error_code="PROVIDER_UNAVAILABLE",
            retryable=True,
        ) == "stale"

    with psycopg.connect(value) as connection:
        connection.execute(
            "UPDATE public.processing_jobs SET run_after = pg_catalog.now() WHERE id = %s",
            (first.job_id,),
        )
        connection.commit()
    with uow.for_worker() as work:
        second_attempt = repository.claim(work.session, worker_id="worker-c")
    assert second_attempt is not None and second_attempt.job_id == first.job_id
    before = datetime.now(timezone.utc)
    with uow.for_worker() as work:
        assert repository.fail(
            work.session,
            claim=second_attempt,
            worker_id="worker-c",
            error_code="PROVIDER_UNAVAILABLE",
            retryable=True,
        ) == "pending"
    with psycopg.connect(value) as connection:
        status, attempts, run_after = connection.execute(
            "SELECT status, attempts, run_after FROM public.processing_jobs WHERE id = %s",
            (first.job_id,),
        ).fetchone()
        assert status == "pending" and attempts == 2
        assert timedelta(seconds=119) <= run_after - before <= timedelta(seconds=122)
        connection.execute(
            "UPDATE public.processing_jobs SET run_after = pg_catalog.now() WHERE id = %s",
            (first.job_id,),
        )
        connection.commit()
    with uow.for_worker() as work:
        third_attempt = repository.claim(work.session, worker_id="worker-d")
    assert third_attempt is not None and third_attempt.job_id == first.job_id
    with uow.for_worker() as work:
        assert repository.fail(
            work.session,
            claim=third_attempt,
            worker_id="worker-d",
            error_code="PROVIDER_UNAVAILABLE",
            retryable=True,
        ) == "failed"
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT job.status, job.attempts, entry.processing_status, "
            "entry.processing_error_code FROM public.processing_jobs AS job "
            "JOIN public.entries AS entry ON entry.id = job.entry_id "
            "WHERE job.id = %s",
            (first.job_id,),
        ).fetchone() == ("failed", 3, "failed", "PROCESSING_FAILED")

    app.state.database_sessions.dispose()


def test_heartbeat_renews_during_provider_call_and_worker_completes() -> None:
    value = database_url()
    bootstrap(value)
    with psycopg.connect(value) as connection:
        entry_id = insert_entry(connection, user_id=USER_ONE, content="heartbeat content")
        connection.commit()
        with connection.transaction():
            job_id = enqueue_owner(connection, USER_ONE, entry_id)

    provider = Provider()
    provider.block = True
    app = application(value, provider)
    app.state.job_service._heartbeat_interval = 0.02
    uow = app.state.database_sessions.unit_of_work_factory
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            app.state.processing_worker.run_one,
            worker_id="heartbeat-worker",
            uow=uow,
        )
        assert provider.entered.wait(timeout=5)
        with psycopg.connect(value) as connection:
            first, entry_status = connection.execute(
                "SELECT job.heartbeat_at, entry.processing_status "
                "FROM public.processing_jobs AS job JOIN public.entries AS entry "
                "ON entry.id = job.entry_id WHERE job.id = %s",
                (job_id,),
            ).fetchone()
            assert entry_status == "processing"
        Event().wait(0.08)
        with psycopg.connect(value) as connection:
            second = connection.execute(
                "SELECT heartbeat_at FROM public.processing_jobs WHERE id = %s", (job_id,)
            ).fetchone()[0]
        assert second > first
        provider.release.set()
        assert future.result(timeout=5) is True
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT job.status, entry.processing_status "
            "FROM public.processing_jobs AS job JOIN public.entries AS entry "
            "ON entry.id = job.entry_id WHERE job.id = %s",
            (job_id,),
        ).fetchone() == ("completed", "completed")
    app.state.database_sessions.dispose()


def test_apply_uses_per_user_lock_and_backfill_is_idempotent() -> None:
    value = database_url()
    bootstrap(value)
    with psycopg.connect(value) as connection:
        entry_id = insert_entry(connection, user_id=USER_ONE, content="locked content")
        materialized_id = insert_entry(
            connection,
            user_id=USER_TWO,
            content="already processed",
            status="completed",
            materialized=True,
        )
        connection.commit()
        with connection.transaction():
            job_id = enqueue_owner(connection, USER_ONE, entry_id)

    repository = JobRepository()
    provider = Provider()
    app = application(value, provider)
    uow = app.state.database_sessions.unit_of_work_factory
    with uow.for_worker() as work:
        claim = repository.claim(work.session, worker_id="lock-worker")
    assert claim is not None and claim.job_id == job_id

    lock_connection = psycopg.connect(value)
    try:
        lock_connection.execute(
            "SELECT pg_catalog.pg_advisory_xact_lock("
            "pg_catalog.hashtextextended('orion-reflection:' || %s::text, 0))",
            (USER_ONE,),
        )
        with pytest.raises(psycopg.errors.QueryCanceled):
            with psycopg.connect(value) as blocked:
                with blocked.transaction():
                    worker(blocked)
                    blocked.execute("SET LOCAL statement_timeout = '100ms'")
                    blocked.execute(
                        "SELECT public.apply_legacy_entry_processing_job("
                        "%s, 'lock-worker', %s, %s, NULL, '[]'::jsonb, '[]'::jsonb, "
                        "'[]'::jsonb, '[]'::jsonb)",
                        (claim.job_id, claim.claim_token, CONFIG_ID),
                    )
    finally:
        lock_connection.rollback()
        lock_connection.close()

    with psycopg.connect(value) as connection:
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.apply_legacy_entry_processing_job("
                "%s, 'lock-worker', %s, %s, NULL, '[]'::jsonb, '[]'::jsonb, "
                "'[]'::jsonb, '[]'::jsonb)",
                (claim.job_id, claim.claim_token, CONFIG_ID),
            ).fetchone() == (True,)

    now = datetime.now(timezone.utc)
    assert app.state.job_service.enqueue_backfill(
        batch_size=100, uow=uow, run_after=now
    ) == 1
    assert app.state.job_service.enqueue_backfill(
        batch_size=100, uow=uow, run_after=now
    ) == 0
    assert app.state.processing_worker.run_one(
        worker_id="backfill-worker", uow=uow
    ) is True
    assert provider.calls == []
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT job.status, entry.processing_status "
            "FROM public.processing_jobs AS job JOIN public.entries AS entry "
            "ON entry.id = job.entry_id WHERE entry.id = %s",
            (materialized_id,),
        ).fetchone() == ("completed", "completed")
    app.state.database_sessions.dispose()
