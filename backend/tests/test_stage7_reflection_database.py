from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from scripts.migrate import apply_migrations, load_migrations


ROOT = Path(__file__).resolve().parents[1]
USER_ONE = UUID("71111111-1111-4111-8111-111111111111")
USER_TWO = UUID("72222222-2222-4222-8222-222222222222")
USER_THREE = UUID("73333333-3333-4333-8333-333333333333")
ENVELOPE_V2 = json.dumps(
    {
        "version": 2,
        "algorithm": "AES-256-GCM",
        "key_id": "test-key",
        "kdf": "HKDF-SHA256",
        "salt": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "nonce": "AAAAAAAAAAAAAAAA",
        "ciphertext": "YQ==",
        "tag": "AAAAAAAAAAAAAAAAAAAAAA==",
    }
)
ENVELOPE_V1 = {
    "version": 1,
    "algorithm": "AES-256-GCM",
    "key_id": "test-key",
    "kdf": "HKDF-SHA256",
    "salt": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "nonce": "AAAAAAAAAAAAAAAA",
    "ciphertext": "YQ==",
    "tag": "AAAAAAAAAAAAAAAAAAAAAA==",
}
NEW_TABLES = (
    "entry_analyses",
    "entry_signals",
    "user_pii_vaults",
    "processing_jobs",
    "reflection_user_state",
    "pattern_candidates",
    "pattern_candidate_evidence",
    "reflection_snapshots",
    "reflection_snapshot_insights",
    "reflection_snapshot_evidence",
    "reflection_feedback",
)
NEW_FUNCTIONS = (
    "apply_legacy_entry_processing_job",
    "apply_combined_entry_processing_job",
    "apply_entry_analysis",
    "apply_reflection_snapshot",
    "claim_processing_job",
    "complete_processing_job",
    "delete_entry_with_reflection_for_owner",
    "enqueue_processing_job",
    "enqueue_entry_processing_backfill",
    "enqueue_processing_job_for_owner",
    "fail_processing_job",
    "get_user_pii_vault_for_update",
    "get_entry_processing_payload",
    "get_entry_quality_history",
    "is_unit_interval_json_object",
    "is_valid_encrypted_envelope_v1",
    "put_reflection_feedback_for_owner",
    "recover_stale_processing_jobs",
    "retry_entry_processing_for_owner",
    "renew_processing_job",
    "save_user_pii_vault",
    "schedule_reflection_jobs",
)


def database_url() -> str:
    value = os.environ.get("STAGE2_DISPOSABLE_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("STAGE2_DISPOSABLE_DATABASE_URL is not configured")
    parsed = urlsplit(value)
    if parsed.path != "/orion_stage2_test" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        pytest.fail("reflection DB tests require the exact local disposable database")
    return value


def reset(value: str) -> None:
    parsed = urlsplit(value)
    maintenance = urlunsplit((parsed.scheme, parsed.netloc, "/postgres", parsed.query, parsed.fragment))
    name = parsed.path.removeprefix("/")
    with psycopg.connect(maintenance, autocommit=True) as connection:
        connection.execute(
            "SELECT pg_catalog.pg_terminate_backend(pid) FROM pg_catalog.pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_catalog.pg_backend_pid()",
            (name,),
        )
        connection.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def bootstrap(value: str, *user_ids: UUID) -> tuple:
    reset(value)
    with psycopg.connect(value) as connection:
        connection.execute((ROOT / "tests/sql/bootstrap_auth.sql").read_text(), prepare=False)
        connection.cursor().executemany(
            "INSERT INTO auth.users (id) VALUES (%s)", [(item,) for item in user_ids]
        )
        connection.commit()
    migrations = load_migrations(ROOT / "migrations")
    apply_migrations(value, migrations)
    return migrations


def owner(connection: psycopg.Connection, user_id: UUID) -> None:
    connection.execute("SET LOCAL ROLE authenticated")
    connection.execute(
        "SELECT pg_catalog.set_config('request.jwt.claims', %s, true)",
        (json.dumps({"sub": str(user_id), "role": "authenticated"}),),
    )


def worker(connection: psycopg.Connection) -> None:
    connection.execute("SET LOCAL ROLE orion_worker")


def admin(connection: psycopg.Connection) -> None:
    connection.commit()
    connection.execute("RESET ROLE")
    connection.commit()


def insert_entry(
    connection: psycopg.Connection,
    user_id: UUID,
    *,
    entry_date: str = "2026-07-20",
) -> UUID:
    entry_id = uuid4()
    connection.execute(
        "INSERT INTO public.entries "
        "(id, user_id, content_envelope, input_type, entry_date) "
        "VALUES (%s, %s, %s::jsonb, 'text', %s)",
        (entry_id, user_id, ENVELOPE_V2, entry_date),
    )
    return entry_id


def insert_analysis_signal(
    connection: psycopg.Connection,
    user_id: UUID,
    entry_id: UUID,
    *,
    signal_type: str = "self_statement",
    loop_role: str | None = "interpretation",
    need_tag: str = "competence",
) -> tuple[UUID, UUID, int]:
    analysis_id = uuid4()
    source_version = connection.execute(
        "INSERT INTO public.entry_analyses "
        "(id, user_id, entry_id, entry_kind, model_eligibility, eligibility, "
        "deterministic_features, semantic_scores, redacted_text_envelope, "
        "offset_map_envelope, reflective_word_count, model_id, prompt_version) "
        "VALUES (%s, %s, %s, 'personal_reflection', 'accepted', 'accepted', "
        "'{}'::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, 20, 'test-model', 'v1') "
        "RETURNING source_version",
        (
            analysis_id,
            user_id,
            entry_id,
            json.dumps({"confidence": 0.9}),
            json.dumps(ENVELOPE_V1),
            json.dumps(ENVELOPE_V1),
        ),
    ).fetchone()[0]
    signal_id = uuid4()
    connection.execute(
        "INSERT INTO public.entry_signals "
        "(id, user_id, entry_id, analysis_id, signal_type, "
        "normalized_label_fingerprint, payload_envelope, themes, need_tags, "
        "loop_role, confidence, source_start, source_end, occurred_on) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, ARRAY['career'], "
        "ARRAY[%s], %s, 0.9, 0, 4, '2026-07-20')",
        (
            signal_id,
            user_id,
            entry_id,
            analysis_id,
            signal_type,
            "a" * 64,
            json.dumps(ENVELOPE_V1),
            need_tag,
            loop_role,
        ),
    )
    return analysis_id, signal_id, source_version


def schema_signature(connection: psycopg.Connection) -> tuple:
    columns = connection.execute(
        "SELECT table_name, ordinal_position, column_name, data_type, udt_name, "
        "is_nullable, column_default, is_identity "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = ANY(%s) "
        "ORDER BY table_name, ordinal_position",
        (list(NEW_TABLES),),
    ).fetchall()
    constraints = connection.execute(
        "SELECT class.relname, constraint_row.conname, constraint_row.contype, "
        "pg_catalog.pg_get_constraintdef(constraint_row.oid) "
        "FROM pg_catalog.pg_constraint AS constraint_row "
        "JOIN pg_catalog.pg_class AS class ON class.oid = constraint_row.conrelid "
        "WHERE constraint_row.connamespace = 'public'::regnamespace "
        "AND class.relname = ANY(%s) ORDER BY class.relname, constraint_row.conname",
        (list(NEW_TABLES),),
    ).fetchall()
    indexes = connection.execute(
        "SELECT tablename, indexname, indexdef FROM pg_catalog.pg_indexes "
        "WHERE schemaname = 'public' AND tablename = ANY(%s) "
        "ORDER BY tablename, indexname",
        (list(NEW_TABLES),),
    ).fetchall()
    policies = connection.execute(
        "SELECT tablename, policyname, roles, cmd, qual, with_check "
        "FROM pg_catalog.pg_policies WHERE schemaname = 'public' "
        "AND tablename = ANY(%s) ORDER BY tablename, policyname",
        (list(NEW_TABLES),),
    ).fetchall()
    functions = connection.execute(
        "SELECT p.proname, pg_catalog.pg_get_function_identity_arguments(p.oid), "
        "pg_catalog.pg_get_functiondef(p.oid) "
        "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = ANY(%s) "
        "ORDER BY p.proname, pg_catalog.pg_get_function_identity_arguments(p.oid)",
        (list(NEW_FUNCTIONS),),
    ).fetchall()
    return columns, constraints, indexes, policies, functions


def test_upgrade_and_fresh_install_schema_parity_preserves_entry_reflections() -> None:
    value = database_url()
    reset(value)
    migrations = load_migrations(ROOT / "migrations")
    with psycopg.connect(value) as connection:
        connection.execute((ROOT / "tests/sql/bootstrap_auth.sql").read_text(), prepare=False)
        connection.execute("INSERT INTO auth.users (id) VALUES (%s)", (USER_ONE,))
        connection.commit()
    apply_migrations(value, migrations[:4])
    with psycopg.connect(value) as connection:
        entry_id = insert_entry(connection, USER_ONE)
        reflection_id = connection.execute(
            "INSERT INTO public.reflections "
            "(user_id, entry_id, reflection_type, activity, confidence_score) "
            "VALUES (%s, %s, 'learned_about_self', 'I value focus', 0.9) RETURNING id",
            (USER_ONE, entry_id),
        ).fetchone()[0]
        connection.commit()
    assert apply_migrations(value, migrations) == (
        "0005_reflection_engine.sql",
        "0006_shared_entry_queue.sql",
        "0007_combined_entry_analysis.sql",
    )
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT reflection_type, activity FROM public.reflections WHERE id = %s",
            (reflection_id,),
        ).fetchone() == ("learned_about_self", "I value focus")
        upgraded = schema_signature(connection)

    reset(value)
    with psycopg.connect(value) as connection:
        connection.execute((ROOT / "tests/sql/bootstrap_auth.sql").read_text(), prepare=False)
        connection.execute((ROOT / "supabase_schema.sql").read_text(), prepare=False)
        fresh = schema_signature(connection)
    assert fresh == upgraded


def test_schema_constraints_owner_rls_and_account_cascades() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    with psycopg.connect(value) as connection:
        rls_count = connection.execute(
            "SELECT count(*) FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = ANY(%s) "
            "AND c.relrowsecurity AND c.relforcerowsecurity",
            (list(NEW_TABLES),),
        ).fetchone()[0]
        assert rls_count == len(NEW_TABLES)
        entry_one = insert_entry(connection, USER_ONE)
        entry_two = insert_entry(connection, USER_TWO)
        analysis_id, signal_id, source_version = insert_analysis_signal(
            connection, USER_ONE, entry_one
        )
        assert connection.execute(
            "SELECT signal_type FROM public.entry_signals WHERE id = %s", (signal_id,)
        ).fetchone() == ("self_statement",)
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                insert_analysis_signal(
                    connection, USER_TWO, entry_two, signal_type="Self_Statement"
                )
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                insert_analysis_signal(
                    connection, USER_TWO, entry_two, loop_role="Interpretation"
                )
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                insert_analysis_signal(
                    connection, USER_TWO, entry_two, need_tag="Competence"
                )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with connection.transaction():
                connection.execute(
                    "INSERT INTO public.entry_signals "
                    "(user_id, entry_id, analysis_id, signal_type, "
                    "normalized_label_fingerprint, payload_envelope, confidence, "
                    "source_start, source_end, occurred_on) "
                    "VALUES (%s, %s, %s, 'emotion', %s, %s::jsonb, 0.9, 0, 4, CURRENT_DATE)",
                    (USER_TWO, entry_two, analysis_id, "b" * 64, json.dumps(ENVELOPE_V1)),
                )
        candidate_id = uuid4()
        snapshot_id = uuid4()
        insight_id = uuid4()
        connection.execute(
            "INSERT INTO public.user_pii_vaults (user_id, mapping_envelope) "
            "VALUES (%s, %s::jsonb)",
            (USER_ONE, json.dumps(ENVELOPE_V1)),
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) "
            "VALUES (%s, %s, 1, 1, ARRAY['2026-07-20'::date])",
            (USER_ONE, source_version),
        )
        connection.execute(
            "INSERT INTO public.pattern_candidates "
            "(id, user_id, pattern_type, canonical_key, status, score, "
            "score_components, payload_envelope, first_seen_at, last_seen_at) "
            "VALUES (%s, %s, 'hidden_driver', %s, 'published', 0.8, %s::jsonb, "
            "%s::jsonb, pg_catalog.now(), pg_catalog.now())",
            (
                candidate_id,
                USER_ONE,
                "c" * 64,
                json.dumps({"recurrence": 0.8}),
                json.dumps(ENVELOPE_V1),
            ),
        )
        connection.execute(
            "INSERT INTO public.pattern_candidate_evidence "
            "(candidate_id, signal_id, user_id, evidence_role, evidence_weight) "
            "VALUES (%s, %s, %s, 'supporting', 0.9)",
            (candidate_id, signal_id, USER_ONE),
        )
        connection.execute(
            "INSERT INTO public.reflection_snapshots "
            "(id, user_id, version, source_version, basis_start, basis_end, "
            "valid_entry_count, excluded_entry_count, distinct_entry_dates, "
            "reflective_word_count) "
            "VALUES (%s, %s, 1, %s, '2026-07-01', '2026-07-20', 1, 0, 1, 20)",
            (snapshot_id, USER_ONE, source_version),
        )
        connection.execute(
            "UPDATE public.reflection_user_state SET last_snapshot_source_version = %s, "
            "last_successful_snapshot_id = %s WHERE user_id = %s",
            (source_version, snapshot_id, USER_ONE),
        )
        connection.execute(
            "INSERT INTO public.reflection_snapshot_insights "
            "(id, user_id, snapshot_id, candidate_id, pattern_type, ordinal, status, "
            "payload_envelope, confidence_label, score) "
            "VALUES (%s, %s, %s, %s, 'hidden_driver', 0, 'available', "
            "%s::jsonb, 'preliminary', 0.8)",
            (insight_id, USER_ONE, snapshot_id, candidate_id, json.dumps(ENVELOPE_V1)),
        )
        connection.execute(
            "INSERT INTO public.reflection_snapshot_evidence "
            "(insight_id, signal_id, entry_id, user_id, evidence_role, ordinal, "
            "source_start, source_end) VALUES (%s, %s, %s, %s, 'supporting', 0, 0, 4)",
            (insight_id, signal_id, entry_one, USER_ONE),
        )
        connection.execute(
            "INSERT INTO public.reflection_feedback "
            "(user_id, snapshot_id, insight_id, candidate_id, response) "
            "VALUES (%s, %s, %s, %s, 'resonates')",
            (USER_ONE, snapshot_id, insight_id, candidate_id),
        )
        connection.execute(
            "INSERT INTO public.processing_jobs "
            "(user_id, entry_id, job_type, source_version) "
            "VALUES (%s, %s, 'entry_processing', %s)",
            (USER_ONE, entry_one, str(entry_one)),
        )
        connection.commit()

    with psycopg.connect(value) as connection:
        with connection.transaction():
            owner(connection, USER_ONE)
            assert connection.execute(
                "SELECT id FROM public.reflection_snapshots"
            ).fetchall() == [(snapshot_id,)]
            assert connection.execute(
                "SELECT id FROM public.reflection_snapshot_insights"
            ).fetchall() == [(insight_id,)]
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute("SELECT * FROM public.entry_signals")
        with connection.transaction():
            owner(connection, USER_TWO)
            assert connection.execute("SELECT id FROM public.reflection_snapshots").fetchall() == []
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(
                    "INSERT INTO public.reflection_feedback "
                    "(user_id, snapshot_id, insight_id, candidate_id, response) "
                    "VALUES (%s, %s, %s, %s, 'rejected')",
                    (USER_ONE, snapshot_id, insight_id, candidate_id),
                )
        with connection.transaction():
            worker(connection)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute("SELECT * FROM public.processing_jobs")

    with psycopg.connect(value) as connection:
        connection.execute("DELETE FROM auth.users WHERE id = %s", (USER_ONE,))
        for table in NEW_TABLES:
            assert connection.execute(
                sql.SQL("SELECT count(*) FROM public.{} WHERE user_id = %s").format(
                    sql.Identifier(table)
                ),
                (USER_ONE,),
            ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM public.entries WHERE user_id = %s", (USER_TWO,)
        ).fetchone() == (1,)


def test_apply_analysis_closed_catalogs_idempotent_queue_and_concurrent_claims() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    with psycopg.connect(value) as connection:
        entry_one = insert_entry(connection, USER_ONE)
        entry_two = insert_entry(connection, USER_TWO)
        connection.commit()
        with connection.transaction():
            owner(connection, USER_ONE)
            first_job = connection.execute(
                "SELECT public.enqueue_processing_job_for_owner(%s, %s, %s)",
                (USER_ONE, entry_one, str(entry_one)),
            ).fetchone()[0]
            replay_job = connection.execute(
                "SELECT public.enqueue_processing_job_for_owner(%s, %s, %s)",
                (USER_ONE, entry_one, str(entry_one)),
            ).fetchone()[0]
            assert first_job == replay_job
        with connection.transaction():
            owner(connection, USER_TWO)
            second_job = connection.execute(
                "SELECT public.enqueue_processing_job_for_owner(%s, %s, %s)",
                (USER_TWO, entry_two, str(entry_two)),
            ).fetchone()[0]

    def claim(worker_id: str) -> tuple[UUID, UUID, str]:
        with psycopg.connect(value) as connection:
            with connection.transaction():
                worker(connection)
                row = connection.execute(
                    "SELECT job_id, claim_token FROM public.claim_processing_job(%s)",
                    (worker_id,),
                ).fetchone()
                return row[0], row[1], worker_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ["worker-a", "worker-b"]))
    assert {item[0] for item in claims} == {first_job, second_job}
    claim_by_job = {item[0]: (item[1], item[2]) for item in claims}

    analysis = {
        "id": str(uuid4()),
        "entry_kind": "personal_reflection",
        "model_eligibility": "accepted",
        "eligibility": "accepted",
        "deterministic_features": {"word_count": 8},
        "semantic_scores": {"confidence": 0.9, "reflective_score": 0.8},
        "exclusion_reason_codes": [],
        "ngram_sketch": ["0123456789abcdef"],
        "redacted_text_envelope": ENVELOPE_V1,
        "offset_map_envelope": ENVELOPE_V1,
        "reflective_word_count": 8,
        "model_id": "test-model",
        "prompt_version": "v1",
    }
    signal = {
        "id": str(uuid4()),
        "signal_type": "self_statement",
        "normalized_label_fingerprint": "d" * 64,
        "payload_envelope": ENVELOPE_V1,
        "themes": ["personal_growth"],
        "need_tags": ["autonomy"],
        "loop_role": "interpretation",
        "confidence": 0.9,
        "source_start": 0,
        "source_end": 4,
        "occurred_on": "2026-07-20",
    }
    with psycopg.connect(value) as connection:
        token, claiming_worker = claim_by_job[first_job]
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                worker(connection)
                invalid = {**signal, "id": str(uuid4()), "signal_type": "Self_Statement"}
                connection.execute(
                    "SELECT public.apply_entry_analysis(%s, %s, %s, %s::jsonb, %s::jsonb)",
                    (
                        first_job,
                        claiming_worker,
                        token,
                        json.dumps(analysis),
                        json.dumps([invalid]),
                    ),
                )
        with connection.transaction():
            worker(connection)
            source_version = connection.execute(
                "SELECT public.apply_entry_analysis(%s, %s, %s, %s::jsonb, %s::jsonb)",
                (
                    first_job,
                    claiming_worker,
                    token,
                    json.dumps(analysis),
                    json.dumps([signal]),
                ),
            ).fetchone()[0]
            assert connection.execute(
                "SELECT public.apply_entry_analysis(%s, %s, %s, %s::jsonb, %s::jsonb)",
                (
                    first_job,
                    claiming_worker,
                    token,
                    json.dumps(analysis),
                    json.dumps([signal]),
                ),
            ).fetchone() == (source_version,)
        admin(connection)
        assert connection.execute(
            "SELECT status FROM public.processing_jobs WHERE id = %s", (first_job,)
        ).fetchone() == ("completed",)
        assert connection.execute(
            "SELECT latest_accepted_source_version, new_valid_entries, new_accepted_signals "
            "FROM public.reflection_user_state WHERE user_id = %s",
            (USER_ONE,),
        ).fetchone() == (source_version, 1, 1)
        assert connection.execute(
            "SELECT signal_type, loop_role FROM public.entry_signals WHERE user_id = %s",
            (USER_ONE,),
        ).fetchone() == ("self_statement", "interpretation")


def test_queue_heartbeats_backoff_stale_claims_and_bounded_attempts() -> None:
    value = database_url()
    bootstrap(value, USER_ONE)
    with psycopg.connect(value) as connection:
        entry_id = insert_entry(connection, USER_ONE)
        connection.commit()
        with connection.transaction():
            owner(connection, USER_ONE)
            job_id = connection.execute(
                "SELECT public.enqueue_processing_job_for_owner(%s, %s, %s)",
                (USER_ONE, entry_id, str(entry_id)),
            ).fetchone()[0]
        with connection.transaction():
            worker(connection)
            first = connection.execute(
                "SELECT claim_token FROM public.claim_processing_job('worker-a')"
            ).fetchone()[0]
            assert connection.execute(
                "SELECT public.renew_processing_job(%s, 'worker-a', %s)", (job_id, first)
            ).fetchone() == (True,)
        connection.execute(
            "UPDATE public.processing_jobs SET heartbeat_at = pg_catalog.now() - interval '10 minutes' "
            "WHERE id = %s",
            (job_id,),
        )
        connection.commit()
        before = datetime.now(timezone.utc)
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.recover_stale_processing_jobs(pg_catalog.now() - interval '5 minutes')"
            ).fetchone() == (1,)
        status, run_after = connection.execute(
            "SELECT status, run_after FROM public.processing_jobs WHERE id = %s", (job_id,)
        ).fetchone()
        assert status == "pending"
        assert before + timedelta(seconds=29) <= run_after <= before + timedelta(seconds=35)
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.complete_processing_job(%s, 'worker-a', %s)", (job_id, first)
            ).fetchone() == (False,)
        admin(connection)
        connection.execute(
            "UPDATE public.processing_jobs SET run_after = pg_catalog.now() - interval '1 second' "
            "WHERE id = %s",
            (job_id,),
        )
        connection.commit()
        before = datetime.now(timezone.utc)
        with connection.transaction():
            worker(connection)
            second = connection.execute(
                "SELECT claim_token FROM public.claim_processing_job('worker-b')"
            ).fetchone()[0]
            assert connection.execute(
                "SELECT public.fail_processing_job(%s, 'worker-b', %s, 'PROVIDER_TIMEOUT', true)",
                (job_id, second),
            ).fetchone() == ("pending",)
        status, attempts, run_after = connection.execute(
            "SELECT status, attempts, run_after FROM public.processing_jobs WHERE id = %s",
            (job_id,),
        ).fetchone()
        assert (status, attempts) == ("pending", 2)
        assert before + timedelta(seconds=119) <= run_after <= before + timedelta(seconds=125)
        connection.execute(
            "UPDATE public.processing_jobs SET run_after = pg_catalog.now() - interval '1 second' "
            "WHERE id = %s",
            (job_id,),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            third = connection.execute(
                "SELECT claim_token FROM public.claim_processing_job('worker-c')"
            ).fetchone()[0]
            assert connection.execute(
                "SELECT public.fail_processing_job(%s, 'worker-c', %s, 'PROVIDER_TIMEOUT', true)",
                (job_id, third),
            ).fetchone() == ("failed",)
        assert connection.execute(
            "SELECT status, attempts, last_error_code FROM public.processing_jobs WHERE id = %s",
            (job_id,),
        ).fetchone() == ("failed", 3, "PROVIDER_TIMEOUT")
        assert connection.execute(
            "SELECT processing_status, processing_error_code FROM public.entries WHERE id = %s",
            (entry_id,),
        ).fetchone() == ("failed", "PROCESSING_FAILED")


def test_scheduler_local_six_pm_rules_and_source_version_idempotency() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO, USER_THREE)
    with psycopg.connect(value) as connection:
        connection.execute(
            "UPDATE public.user_profiles SET timezone = 'Asia/Kolkata' "
            "WHERE user_id IN (%s, %s, %s)",
            (USER_ONE, USER_TWO, USER_THREE),
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) VALUES "
            "(%s, 11, 2, 2, ARRAY['2026-07-20'::date, '2026-07-21'::date]), "
            "(%s, 12, 2, 2, ARRAY['2026-07-21'::date]), "
            "(%s, 13, 3, 0, ARRAY['2026-07-21'::date])",
            (USER_ONE, USER_TWO, USER_THREE),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.schedule_reflection_jobs('2026-07-21 12:29:00+00')"
            ).fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM public.processing_jobs").fetchone() == (0,)
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.schedule_reflection_jobs('2026-07-21 12:31:00+00')"
            ).fetchone() == (1,)
            assert connection.execute(
                "SELECT public.schedule_reflection_jobs('2026-07-21 13:31:00+00')"
            ).fetchone() == (0,)
        connection.commit()
        assert connection.execute(
            "SELECT user_id, source_version FROM public.processing_jobs"
        ).fetchall() == [(USER_ONE, "11")]
        assert connection.execute(
            "SELECT user_id, last_schedule_local_date FROM public.reflection_user_state "
            "ORDER BY user_id"
        ).fetchall() == [
            (USER_ONE, datetime(2026, 7, 21).date()),
            (USER_TWO, datetime(2026, 7, 21).date()),
            (USER_THREE, datetime(2026, 7, 21).date()),
        ]
        admin(connection)
        connection.execute(
            "UPDATE public.user_profiles SET timezone = 'America/New_York' WHERE user_id = %s",
            (USER_THREE,),
        )
        connection.execute(
            "UPDATE public.reflection_user_state SET latest_accepted_source_version = 14, "
            "new_valid_entries = 3, new_accepted_signals = 1, "
            "pending_local_dates = ARRAY['2026-07-22'::date] WHERE user_id = %s",
            (USER_THREE,),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.schedule_reflection_jobs('2026-07-22 21:59:00+00')"
            ).fetchone() == (0,)
            assert connection.execute(
                "SELECT public.schedule_reflection_jobs('2026-07-22 22:01:00+00')"
            ).fetchone() == (1,)
        admin(connection)
        assert connection.execute(
            "SELECT count(*) FROM public.processing_jobs WHERE user_id = %s "
            "AND job_type = 'reflection_synthesis' AND source_version = '14'",
            (USER_THREE,),
        ).fetchone() == (1,)


def test_snapshot_apply_feedback_idempotency_and_entry_deletion_recovery() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    with psycopg.connect(value) as connection:
        entry_one = insert_entry(connection, USER_ONE, entry_date="2026-07-19")
        entry_two = insert_entry(connection, USER_ONE, entry_date="2026-07-20")
        _, signal_one, source_one = insert_analysis_signal(connection, USER_ONE, entry_one)
        _, _signal_two, source_two = insert_analysis_signal(connection, USER_ONE, entry_two)
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) "
            "VALUES (%s, %s, 2, 2, ARRAY['2026-07-19'::date, '2026-07-20'::date])",
            (USER_ONE, source_two),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            job_id = connection.execute(
                "SELECT public.enqueue_processing_job(%s, NULL, 'reflection_synthesis', %s, pg_catalog.now())",
                (USER_ONE, str(source_two)),
            ).fetchone()[0]
            claim = connection.execute(
                "SELECT claim_token FROM public.claim_processing_job('snapshot-worker')"
            ).fetchone()[0]

        snapshot_id = uuid4()
        candidate_id = uuid4()
        insight_id = uuid4()
        snapshot = {
            "id": str(snapshot_id),
            "version": 1,
            "source_version": source_two,
            "basis_start": "2026-07-01",
            "basis_end": "2026-07-20",
            "valid_entry_count": 2,
            "excluded_entry_count": 0,
            "distinct_entry_dates": 2,
            "reflective_word_count": 40,
        }
        candidates = [
            {
                "id": str(candidate_id),
                "pattern_type": "hidden_driver",
                "canonical_key": "e" * 64,
                "status": "published",
                "score": 0.8,
                "score_components": {"recurrence": 0.8},
                "payload_envelope": ENVELOPE_V1,
                "first_seen_at": "2026-07-19T10:00:00Z",
                "last_seen_at": "2026-07-20T10:00:00Z",
                "version": 1,
            }
        ]
        candidate_evidence = [
            {
                "candidate_id": str(candidate_id),
                "signal_id": str(signal_one),
                "evidence_role": "supporting",
                "evidence_weight": 0.9,
            }
        ]
        insights = [
            {
                "id": str(insight_id),
                "candidate_id": str(candidate_id),
                "pattern_type": "hidden_driver",
                "ordinal": 0,
                "status": "available",
                "payload_envelope": ENVELOPE_V1,
                "confidence_label": "preliminary",
                "score": 0.8,
            },
            {
                "id": str(uuid4()),
                "pattern_type": "recurring_loop",
                "ordinal": 0,
                "status": "insufficient_evidence",
                "reason_code": "LOOP_NOT_REPEATED",
            },
        ]
        evidence = [
            {
                "insight_id": str(insight_id),
                "signal_id": str(signal_one),
                "entry_id": str(entry_one),
                "evidence_role": "supporting",
                "ordinal": 0,
                "source_start": 0,
                "source_end": 4,
            }
        ]
        with connection.transaction():
            worker(connection)
            applied = connection.execute(
                "SELECT public.apply_reflection_snapshot("
                "%s, 'snapshot-worker', %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)",
                (
                    job_id,
                    claim,
                    json.dumps(snapshot),
                    json.dumps(candidates),
                    json.dumps(candidate_evidence),
                    json.dumps(insights),
                    json.dumps(evidence),
                ),
            ).fetchone()[0]
            assert applied == snapshot_id
            replay = connection.execute(
                "SELECT public.apply_reflection_snapshot("
                "%s, 'snapshot-worker', %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)",
                (
                    job_id,
                    claim,
                    json.dumps(snapshot),
                    json.dumps(candidates),
                    json.dumps(candidate_evidence),
                    json.dumps(insights),
                    json.dumps(evidence),
                ),
            ).fetchone()[0]
            assert replay == snapshot_id
        assert connection.execute(
            "SELECT status FROM public.processing_jobs WHERE id = %s", (job_id,)
        ).fetchone() == ("completed",)
        assert connection.execute(
            "SELECT last_snapshot_source_version, new_valid_entries, new_accepted_signals "
            "FROM public.reflection_user_state WHERE user_id = %s",
            (USER_ONE,),
        ).fetchone() == (source_two, 0, 0)

        with connection.transaction():
            owner(connection, USER_ONE)
            first_feedback = connection.execute(
                "SELECT response FROM public.put_reflection_feedback_for_owner(%s, %s, %s, 'partly')",
                (USER_ONE, snapshot_id, insight_id),
            ).fetchone()
            second_feedback = connection.execute(
                "SELECT response FROM public.put_reflection_feedback_for_owner(%s, %s, %s, 'partly')",
                (USER_ONE, snapshot_id, insight_id),
            ).fetchone()
            assert first_feedback == second_feedback == ("partly",)
            assert connection.execute(
                "SELECT count(*) FROM public.reflection_feedback"
            ).fetchone() == (1,)
        admin(connection)
        assert connection.execute(
            "SELECT status, version FROM public.pattern_candidates WHERE id = %s",
            (candidate_id,),
        ).fetchone() == ("weakened", 2)
        admin(connection)
        with connection.transaction():
            owner(connection, USER_TWO)
            with pytest.raises(psycopg.errors.InvalidParameterValue):
                connection.execute(
                    "SELECT public.put_reflection_feedback_for_owner(%s, %s, %s, 'rejected')",
                    (USER_ONE, snapshot_id, insight_id),
                )

        admin(connection)
        with connection.transaction():
            owner(connection, USER_ONE)
            assert connection.execute(
                "SELECT public.delete_entry_with_reflection_for_owner(%s, %s)",
                (USER_ONE, entry_one),
            ).fetchone() == (True,)
        assert connection.execute(
            "SELECT count(*) FROM public.entry_analyses WHERE entry_id = %s", (entry_one,)
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT status FROM public.reflection_snapshots WHERE id = %s", (snapshot_id,)
        ).fetchone() == ("stale",)
        replacement = connection.execute(
            "SELECT status, source_version::bigint FROM public.processing_jobs "
            "WHERE user_id = %s AND job_type = 'reflection_synthesis' "
            "AND source_version <> %s ORDER BY created_at DESC LIMIT 1",
            (USER_ONE, str(source_two)),
        ).fetchone()
        assert replacement is not None
        assert replacement[0] == "pending"
        assert replacement[1] > source_two
