from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
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
    "reflection_shadow_runs",
    "processing_backfill_runs",
    "processing_backfill_users",
)
USER_OWNED_NEW_TABLES = tuple(
    table for table in NEW_TABLES if table != "processing_backfill_runs"
)
NEW_FUNCTIONS = (
    "apply_combined_entry_processing_job",
    "apply_deterministic_reflection_candidates",
    "apply_entry_analysis",
    "apply_reflection_snapshot",
    "claim_processing_job",
    "complete_reflection_shadow",
    "complete_processing_job",
    "delete_entry_with_reflection_for_owner",
    "enqueue_processing_job",
    "enqueue_processing_job_for_owner",
    "fail_processing_job",
    "get_user_pii_vault_for_update",
    "get_entry_processing_payload",
    "get_entry_processing_backfill_status",
    "get_processing_queue_observability",
    "get_entry_quality_history",
    "get_reflection_candidate_basis",
    "get_reflection_synthesis_basis",
    "get_reflections_for_owner",
    "is_unit_interval_json_object",
    "is_valid_encrypted_envelope_v1",
    "put_reflection_feedback_for_owner",
    "plan_entry_processing_backfill",
    "recover_stale_processing_jobs",
    "retry_entry_processing_for_owner",
    "renew_processing_job",
    "run_entry_processing_backfill_batch",
    "save_user_pii_vault",
    "schedule_reflection_jobs",
    "schedule_reflection_jobs_observed",
    "set_entry_processing_backfill_state",
)
RETIRED_ENTRY_APPLY_SIGNATURE = (
    "public.apply_legacy_entry_processing_job("
    "uuid,text,uuid,uuid,text,jsonb,jsonb,jsonb,jsonb)"
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


def schedule_reflections(
    connection: psycopg.Connection,
    moment: str,
    user_ids: tuple[UUID, ...],
    *,
    mode: str = "publish",
) -> int:
    return connection.execute(
        "SELECT public.schedule_reflection_jobs(%s, %s, %s)",
        (moment, mode, list(user_ids)),
    ).fetchone()[0]


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


def candidate_payload(
    candidate_id: UUID,
    *,
    canonical_key: str = "c" * 64,
    status: str = "candidate",
    version: int = 1,
    rejected_at: str | None = None,
    rejected_source_version: int | None = None,
    publication_gate_passed: bool = True,
) -> dict[str, object]:
    return {
        "id": str(candidate_id),
        "pattern_type": "hidden_driver",
        "canonical_key": canonical_key,
        "status": status,
        "score": 0.8,
        "score_components": {"recurrence": 0.8, "stability": 0.5},
        "payload_envelope": ENVELOPE_V1,
        "first_seen_at": "2026-07-01T00:00:00+00:00",
        "last_seen_at": "2026-07-20T00:00:00+00:00",
        "version": version,
        "rejected_at": rejected_at,
        "rejected_source_version": rejected_source_version,
        "publication_gate_passed": publication_gate_passed,
    }


def evidence_payload(candidate_id: UUID, signal_id: UUID) -> dict[str, object]:
    return {
        "candidate_id": str(candidate_id),
        "signal_id": str(signal_id),
        "evidence_role": "supporting",
        "evidence_weight": 0.9,
    }


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
        "0008_deterministic_reflection_candidates.sql",
        "0009_reflection_synthesis.sql",
        "0010_reflections_api.sql",
        "0011_reflection_rollout.sql",
        "0012_reflection_observability.sql",
        "0013_reflections_api_snapshot_id.sql",
    )
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT reflection_type, activity FROM public.reflections WHERE id = %s",
            (reflection_id,),
        ).fetchone() == ("learned_about_self", "I value focus")
        assert connection.execute(
            "SELECT pg_catalog.to_regprocedure(%s)",
            (RETIRED_ENTRY_APPLY_SIGNATURE,),
        ).fetchone() == (None,)
        upgraded = schema_signature(connection)

    reset(value)
    with psycopg.connect(value) as connection:
        connection.execute((ROOT / "tests/sql/bootstrap_auth.sql").read_text(), prepare=False)
        connection.execute((ROOT / "supabase_schema.sql").read_text(), prepare=False)
        assert connection.execute(
            "SELECT pg_catalog.to_regprocedure(%s)",
            (RETIRED_ENTRY_APPLY_SIGNATURE,),
        ).fetchone() == (None,)
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
        for table in USER_OWNED_NEW_TABLES:
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
            assert schedule_reflections(
                connection,
                "2026-07-21 12:29:00+00",
                (USER_ONE, USER_TWO, USER_THREE),
            ) == 0
        assert connection.execute("SELECT count(*) FROM public.processing_jobs").fetchone() == (0,)
        with connection.transaction():
            worker(connection)
            assert schedule_reflections(
                connection,
                "2026-07-21 12:31:00+00",
                (USER_TWO, USER_THREE),
            ) == 0
        admin(connection)
        assert connection.execute(
            "SELECT last_schedule_local_date FROM public.reflection_user_state "
            "WHERE user_id = %s",
            (USER_ONE,),
        ).fetchone() == (None,)
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert schedule_reflections(
                connection,
                "2026-07-21 12:31:00+00",
                (USER_ONE, USER_TWO, USER_THREE),
            ) == 1
            assert schedule_reflections(
                connection,
                "2026-07-21 13:31:00+00",
                (USER_ONE, USER_TWO, USER_THREE),
            ) == 0
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
            "UPDATE public.reflection_user_state "
            "SET latest_accepted_source_version = 15, new_valid_entries = 3, "
            "new_accepted_signals = 1, pending_local_dates = ARRAY['2026-07-21'::date] "
            "WHERE user_id = %s",
            (USER_TWO,),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert schedule_reflections(
                connection,
                "2026-07-21 14:00:00+00",
                (USER_ONE, USER_TWO, USER_THREE),
            ) == 0
            assert schedule_reflections(
                connection,
                "2026-07-22 12:31:00+00",
                (USER_ONE, USER_TWO, USER_THREE),
            ) == 1
        assert connection.execute(
            "SELECT count(*) FROM public.processing_jobs WHERE user_id = %s "
            "AND job_type = 'reflection_synthesis' AND source_version = '15'",
            (USER_TWO,),
        ).fetchone() == (1,)
        admin(connection)
        connection.execute(
            "UPDATE public.user_profiles SET timezone = 'America/New_York' WHERE user_id = %s",
            (USER_THREE,),
        )
        connection.execute(
            "UPDATE public.reflection_user_state SET latest_accepted_source_version = 14, "
            "new_valid_entries = 3, new_accepted_signals = 1, "
            "pending_local_dates = ARRAY['2026-07-22'::date], "
            "last_schedule_local_date = '2026-07-21' WHERE user_id = %s",
            (USER_THREE,),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert schedule_reflections(
                connection,
                "2026-07-22 21:59:00+00",
                (USER_ONE, USER_TWO, USER_THREE),
            ) == 0
            assert schedule_reflections(
                connection,
                "2026-07-22 22:01:00+00",
                (USER_ONE, USER_TWO, USER_THREE),
            ) == 1
        admin(connection)
        assert connection.execute(
            "SELECT count(*) FROM public.processing_jobs WHERE user_id = %s "
            "AND job_type = 'reflection_synthesis' AND source_version = '14'",
            (USER_THREE,),
        ).fetchone() == (1,)


def test_scheduler_uses_profile_iana_timezone_across_dst_and_serializes_sweeps() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    with psycopg.connect(value) as connection:
        connection.execute(
            "UPDATE public.user_profiles SET timezone = CASE "
            "WHEN user_id = %s THEN 'America/New_York' ELSE 'Europe/London' END "
            "WHERE user_id IN (%s, %s)",
            (USER_ONE, USER_ONE, USER_TWO),
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates, last_schedule_local_date) VALUES "
            "(%s, 21, 3, 1, ARRAY['2026-03-08'::date], NULL), "
            "(%s, 22, 3, 1, ARRAY['2026-03-08'::date], '2026-03-08')",
            (USER_ONE, USER_TWO),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert schedule_reflections(
                connection, "2026-03-08 21:59:59+00", (USER_ONE, USER_TWO)
            ) == 0
            assert schedule_reflections(
                connection, "2026-03-08 22:00:00+00", (USER_ONE, USER_TWO)
            ) == 1

        admin(connection)
        connection.execute(
            "UPDATE public.reflection_user_state SET last_schedule_local_date = CASE "
            "WHEN user_id = %s THEN '2026-03-29'::date ELSE NULL END, "
            "latest_accepted_source_version = CASE WHEN user_id = %s THEN 21 ELSE 23 END "
            "WHERE user_id IN (%s, %s)",
            (USER_ONE, USER_ONE, USER_ONE, USER_TWO),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert schedule_reflections(
                connection, "2026-03-29 16:59:59+00", (USER_ONE, USER_TWO)
            ) == 0
            assert schedule_reflections(
                connection, "2026-03-29 17:00:00+00", (USER_ONE, USER_TWO)
            ) == 1

        admin(connection)
        connection.execute(
            "UPDATE public.reflection_user_state SET last_schedule_local_date = NULL, "
            "latest_accepted_source_version = 24 WHERE user_id = %s",
            (USER_TWO,),
        )
        connection.commit()

    def sweep(_index: int) -> int:
        with psycopg.connect(value) as concurrent, concurrent.transaction():
            worker(concurrent)
            return schedule_reflections(
                concurrent, "2026-03-30 17:00:00+00", (USER_ONE, USER_TWO)
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(sweep, range(2)))
    assert sorted(results) == [0, 1]
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT count(*) FROM public.processing_jobs WHERE user_id = %s "
            "AND job_type = 'reflection_synthesis' AND source_version = '24'",
            (USER_TWO,),
        ).fetchone() == (1,)


def test_shadow_completion_is_atomic_idempotent_and_snapshot_free() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    with psycopg.connect(value) as connection:
        connection.execute(
            "UPDATE public.user_profiles SET timezone = 'Asia/Kolkata' "
            "WHERE user_id = %s",
            (USER_ONE,),
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) VALUES "
            "(%s, 7, 3, 2, ARRAY['2026-07-19'::date, '2026-07-20'::date])",
            (USER_ONE,),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert schedule_reflections(
                connection,
                "2026-07-20 12:31:00+00",
                (USER_ONE,),
                mode="shadow",
            ) == 1
            claimed = connection.execute(
                "SELECT job_id, execution_mode, claim_token "
                "FROM public.claim_processing_job('shadow-worker')"
            ).fetchone()
        assert claimed is not None
        job_id, execution_mode, claim_token = claimed
        assert execution_mode == "shadow"

        with pytest.raises(psycopg.errors.RaiseException):
            with connection.transaction():
                worker(connection)
                connection.execute(
                    "SELECT public.complete_reflection_shadow("
                    "%s, 'shadow-worker', %s, 4, 2, true)",
                    (job_id, uuid4()),
                )

        with connection.transaction():
            worker(connection)
            shadow_id = connection.execute(
                "SELECT public.complete_reflection_shadow("
                "%s, 'shadow-worker', %s, 4, 2, true)",
                (job_id, claim_token),
            ).fetchone()[0]
            replay = connection.execute(
                "SELECT public.complete_reflection_shadow("
                "%s, 'shadow-worker', %s, 4, 2, true)",
                (job_id, claim_token),
            ).fetchone()[0]
            assert replay == shadow_id
        admin(connection)
        assert connection.execute(
            "SELECT status, execution_mode, priority FROM public.processing_jobs "
            "WHERE id = %s",
            (job_id,),
        ).fetchone() == ("completed", "shadow", 60)
        assert connection.execute(
            "SELECT candidate_count, selected_count, provider_called "
            "FROM public.reflection_shadow_runs WHERE id = %s",
            (shadow_id,),
        ).fetchone() == (4, 2, True)
        assert connection.execute(
            "SELECT (SELECT count(*) FROM public.pattern_candidates), "
            "(SELECT count(*) FROM public.reflection_snapshots)"
        ).fetchone() == (0, 0)
        connection.commit()

        with connection.transaction():
            worker(connection)
            assert schedule_reflections(
                connection,
                "2026-07-21 12:31:00+00",
                (USER_ONE,),
                mode="publish",
            ) == 1
        admin(connection)
        assert connection.execute(
            "SELECT status, execution_mode, priority, attempts "
            "FROM public.processing_jobs WHERE id = %s",
            (job_id,),
        ).fetchone() == ("pending", "publish", 80, 0)
        assert connection.execute(
            "SELECT count(*) FROM public.reflection_snapshots"
        ).fetchone() == (0,)


def test_snapshot_apply_feedback_idempotency_and_entry_deletion_recovery() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    with psycopg.connect(value) as connection:
        entry_one = insert_entry(connection, USER_ONE, entry_date="2026-07-19")
        entry_two = insert_entry(connection, USER_ONE, entry_date="2026-07-20")
        entry_three = insert_entry(connection, USER_ONE, entry_date="2026-07-18")
        _, signal_one, source_one = insert_analysis_signal(connection, USER_ONE, entry_one)
        _, signal_two, source_two = insert_analysis_signal(connection, USER_ONE, entry_two)
        _, signal_three, source_three = insert_analysis_signal(
            connection, USER_ONE, entry_three
        )
        connection.execute(
            "UPDATE public.entry_analyses SET reflective_word_count = 100 "
            "WHERE user_id = %s",
            (USER_ONE,),
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) "
            "VALUES (%s, %s, 3, 3, "
            "ARRAY['2026-07-18'::date, '2026-07-19'::date, '2026-07-20'::date])",
            (USER_ONE, source_three),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            job_id = connection.execute(
                "SELECT public.enqueue_processing_job(%s, NULL, 'reflection_synthesis', %s, pg_catalog.now())",
                    (USER_ONE, str(source_three)),
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
                "source_version": source_three,
                "basis_start": "2026-04-22",
                "basis_end": "2026-07-20",
                "valid_entry_count": 3,
                "excluded_entry_count": 0,
                "distinct_entry_dates": 3,
                "reflective_word_count": 300,
                "status": "available",
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
                "publication_gate_passed": True,
            }
        ]
        candidate_evidence = [
            {
                "candidate_id": str(candidate_id),
                "signal_id": str(signal_one),
                "evidence_role": "supporting",
                "evidence_weight": 0.9,
            },
            {
                "candidate_id": str(candidate_id),
                "signal_id": str(signal_two),
                "evidence_role": "supporting",
                "evidence_weight": 0.9,
            },
            {
                "candidate_id": str(candidate_id),
                "signal_id": str(signal_three),
                "evidence_role": "supporting",
                "evidence_weight": 0.9,
            },
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
            {
                "id": str(uuid4()),
                "pattern_type": "inner_tension",
                "ordinal": 0,
                "status": "insufficient_evidence",
                "reason_code": "BOTH_SIDES_NOT_SUPPORTED",
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
            },
            {
                "insight_id": str(insight_id),
                "signal_id": str(signal_two),
                "entry_id": str(entry_two),
                "evidence_role": "supporting",
                "ordinal": 1,
                "source_start": 0,
                "source_end": 4,
            },
            {
                "insight_id": str(insight_id),
                "signal_id": str(signal_three),
                "entry_id": str(entry_three),
                "evidence_role": "supporting",
                "ordinal": 2,
                "source_start": 0,
                "source_end": 4,
            },
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
        ).fetchone() == (source_three, 0, 0)

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
            "SELECT status FROM public.processing_jobs "
            "WHERE user_id = %s AND job_type = 'reflection_synthesis' "
            "AND source_version <> %s ORDER BY created_at DESC LIMIT 1",
            (USER_ONE, str(source_three)),
        ).fetchone()
        assert replacement is None
        assert connection.execute(
            "SELECT last_schedule_local_date FROM public.reflection_user_state "
            "WHERE user_id = %s",
            (USER_ONE,),
        ).fetchone() == (None,)


def test_snapshot_versions_reject_stale_claims_and_preserve_concurrent_counters() -> None:
    value = database_url()
    bootstrap(value, USER_ONE)

    def snapshot_payload(
        *, snapshot_id: UUID, version: int, source: int, start: str, end: str, count: int
    ) -> dict[str, object]:
        return {
            "id": str(snapshot_id),
            "version": version,
            "source_version": source,
            "basis_start": start,
            "basis_end": end,
            "valid_entry_count": count,
            "excluded_entry_count": 0,
            "distinct_entry_dates": count,
            "reflective_word_count": count * 100,
            "status": "available",
        }

    def insufficient(snapshot_id: UUID) -> list[dict[str, object]]:
        return [
            {
                "id": str(uuid4()),
                "pattern_type": pattern_type,
                "ordinal": 0,
                "status": "insufficient_evidence",
                "reason_code": reason,
            }
            for pattern_type, reason in (
                ("hidden_driver", "DRIVER_NOT_REPEATED"),
                ("recurring_loop", "LOOP_NOT_REPEATED"),
                ("inner_tension", "BOTH_SIDES_NOT_SUPPORTED"),
            )
        ]

    with psycopg.connect(value) as connection:
        sources: list[int] = []
        for entry_date in ("2026-05-01", "2026-05-10", "2026-06-01"):
            entry_id = insert_entry(connection, USER_ONE, entry_date=entry_date)
            _, _, source = insert_analysis_signal(connection, USER_ONE, entry_id)
            sources.append(source)
        connection.execute(
            "UPDATE public.entry_analyses SET reflective_word_count = 100 "
            "WHERE user_id = %s",
            (USER_ONE,),
        )
        source_three = sources[-1]
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) VALUES "
            "(%s, %s, 3, 3, ARRAY['2026-05-01'::date, '2026-05-10'::date, "
            "'2026-06-01'::date])",
            (USER_ONE, source_three),
        )
        connection.commit()

        with connection.transaction():
            worker(connection)
            first_job = connection.execute(
                "SELECT public.enqueue_processing_job(%s, NULL, 'reflection_synthesis', %s, "
                "pg_catalog.now())",
                (USER_ONE, str(source_three)),
            ).fetchone()[0]
            first_claim = connection.execute(
                "SELECT claim_token FROM public.claim_processing_job('snapshot-worker')"
            ).fetchone()[0]

        admin(connection)
        concurrent_entry = insert_entry(connection, USER_ONE, entry_date="2026-06-02")
        _, _, source_four = insert_analysis_signal(
            connection, USER_ONE, concurrent_entry
        )
        connection.execute(
            "UPDATE public.entry_analyses SET reflective_word_count = 100 "
            "WHERE entry_id = %s",
            (concurrent_entry,),
        )
        connection.execute(
            "UPDATE public.reflection_user_state SET "
            "latest_accepted_source_version = %s, new_valid_entries = 4, "
            "new_accepted_signals = 4, pending_local_dates = "
            "ARRAY['2026-05-01'::date, '2026-05-10'::date, '2026-06-01'::date, "
            "'2026-06-02'::date] WHERE user_id = %s",
            (source_four, USER_ONE),
        )
        connection.commit()

        first_snapshot = uuid4()
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.apply_reflection_snapshot("
                "%s, 'snapshot-worker', %s, %s::jsonb, '[]'::jsonb, '[]'::jsonb, "
                "%s::jsonb, '[]'::jsonb)",
                (
                    first_job,
                    first_claim,
                    json.dumps(
                        snapshot_payload(
                            snapshot_id=first_snapshot,
                            version=1,
                            source=source_three,
                            start="2026-03-04",
                            end="2026-06-01",
                            count=3,
                        )
                    ),
                    json.dumps(insufficient(first_snapshot)),
                ),
            ).fetchone() == (first_snapshot,)
        assert connection.execute(
            "SELECT last_snapshot_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates "
            "FROM public.reflection_user_state WHERE user_id = %s",
            (USER_ONE,),
        ).fetchone() == (source_three, 1, 1, [date(2026, 6, 2)])

        admin(connection)
        with connection.transaction():
            worker(connection)
            second_job = connection.execute(
                "SELECT public.enqueue_processing_job(%s, NULL, 'reflection_synthesis', %s, "
                "pg_catalog.now())",
                (USER_ONE, str(source_four)),
            ).fetchone()[0]
            second_claim = connection.execute(
                "SELECT claim_token FROM public.claim_processing_job('snapshot-worker')"
            ).fetchone()[0]

        second_snapshot = uuid4()
        second_payload = snapshot_payload(
            snapshot_id=second_snapshot,
            version=2,
            source=source_four,
            start="2026-03-05",
            end="2026-06-02",
            count=4,
        )
        with pytest.raises(psycopg.errors.RaiseException):
            with connection.transaction():
                worker(connection)
                connection.execute(
                    "SELECT public.apply_reflection_snapshot("
                    "%s, 'snapshot-worker', %s, %s::jsonb, '[]'::jsonb, '[]'::jsonb, "
                    "%s::jsonb, '[]'::jsonb)",
                    (
                        second_job,
                        uuid4(),
                        json.dumps(second_payload),
                        json.dumps(insufficient(second_snapshot)),
                    ),
                )
        assert connection.execute(
            "SELECT count(*) FROM public.reflection_snapshots WHERE user_id = %s",
            (USER_ONE,),
        ).fetchone() == (1,)

        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.apply_reflection_snapshot("
                "%s, 'snapshot-worker', %s, %s::jsonb, '[]'::jsonb, '[]'::jsonb, "
                "%s::jsonb, '[]'::jsonb)",
                (
                    second_job,
                    second_claim,
                    json.dumps(second_payload),
                    json.dumps(insufficient(second_snapshot)),
                ),
            ).fetchone() == (second_snapshot,)
        admin(connection)
        assert connection.execute(
            "SELECT version, source_version FROM public.reflection_snapshots "
            "WHERE user_id = %s ORDER BY version",
            (USER_ONE,),
        ).fetchall() == [(1, source_three), (2, source_four)]
        assert connection.execute(
            "SELECT new_valid_entries, new_accepted_signals, last_successful_snapshot_id "
            "FROM public.reflection_user_state WHERE user_id = %s",
            (USER_ONE,),
        ).fetchone() == (0, 0, second_snapshot)


def test_candidate_basis_and_atomic_apply_are_worker_only_owner_safe_and_idempotent() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    with psycopg.connect(value) as connection:
        entry_one = insert_entry(connection, USER_ONE, entry_date="2026-07-01")
        _, signal_one, source_one = insert_analysis_signal(
            connection, USER_ONE, entry_one
        )
        entry_two = insert_entry(connection, USER_TWO, entry_date="2026-07-02")
        _, signal_two, _ = insert_analysis_signal(connection, USER_TWO, entry_two)
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version) VALUES (%s, %s)",
            (USER_ONE, source_one),
        )
        connection.commit()

        with connection.transaction():
            owner(connection, USER_ONE)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(
                    "SELECT public.get_reflection_candidate_basis(%s, %s, 90)",
                    (USER_ONE, source_one),
                )

        candidate_id = uuid4()
        candidates = [candidate_payload(candidate_id)]
        evidence = [evidence_payload(candidate_id, signal_one)]
        with connection.transaction():
            worker(connection)
            candidate_basis = connection.execute(
                "SELECT public.get_reflection_candidate_basis(%s, %s, 90)",
                (USER_ONE, source_one),
            ).fetchone()[0]
            assert candidate_basis["source_version"] == source_one
            assert candidate_basis["valid_entry_count"] == 1
            assert [item["id"] for item in candidate_basis["signals"]] == [
                str(signal_one)
            ]
            first = connection.execute(
                "SELECT public.apply_deterministic_reflection_candidates("
                "%s, %s, %s::jsonb, %s::jsonb)",
                (
                    USER_ONE,
                    source_one,
                    json.dumps(candidates),
                    json.dumps(evidence),
                ),
            ).fetchone()[0]
            replay = connection.execute(
                "SELECT public.apply_deterministic_reflection_candidates("
                "%s, %s, %s::jsonb, %s::jsonb)",
                (
                    USER_ONE,
                    source_one,
                    json.dumps(candidates),
                    json.dumps(evidence),
                ),
            ).fetchone()[0]
            assert (first, replay) == (1, 0)
        assert connection.execute(
            "SELECT last_source_version, count(evidence.signal_id) "
            "FROM public.pattern_candidates AS candidate "
            "JOIN public.pattern_candidate_evidence AS evidence "
            "ON evidence.candidate_id = candidate.id AND evidence.user_id = candidate.user_id "
            "WHERE candidate.id = %s GROUP BY candidate.last_source_version",
            (candidate_id,),
        ).fetchone() == (source_one, 1)

        with pytest.raises(psycopg.errors.RaiseException):
            with connection.transaction():
                worker(connection)
                connection.execute(
                    "SELECT public.apply_deterministic_reflection_candidates("
                    "%s, 0, %s::jsonb, '[]'::jsonb)",
                    (USER_ONE, json.dumps([candidate_payload(uuid4())])),
                )
        bad_candidate_id = uuid4()
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            with connection.transaction():
                worker(connection)
                connection.execute(
                    "SELECT public.apply_deterministic_reflection_candidates("
                    "%s, %s, %s::jsonb, %s::jsonb)",
                    (
                        USER_ONE,
                        source_one,
                        json.dumps(
                            [
                                candidate_payload(
                                    bad_candidate_id, canonical_key="e" * 64
                                )
                            ]
                        ),
                        json.dumps(
                            [evidence_payload(bad_candidate_id, signal_two)]
                        ),
                    ),
                )
        assert connection.execute(
            "SELECT count(*) FROM public.pattern_candidates WHERE id = %s",
            (bad_candidate_id,),
        ).fetchone() == (0,)


def test_synthesis_basis_is_claim_bound_accepted_only_and_capped_at_90_days() -> None:
    value = database_url()
    bootstrap(value, USER_ONE)
    with psycopg.connect(value) as connection:
        old_entry = insert_entry(connection, USER_ONE, entry_date="2026-01-01")
        _, old_signal, _ = insert_analysis_signal(connection, USER_ONE, old_entry)
        inside_entry = insert_entry(connection, USER_ONE, entry_date="2026-06-01")
        _, inside_signal, _ = insert_analysis_signal(connection, USER_ONE, inside_entry)
        uncertain_entry = insert_entry(connection, USER_ONE, entry_date="2026-06-15")
        connection.execute(
            "INSERT INTO public.entry_analyses "
            "(user_id, entry_id, entry_kind, model_eligibility, eligibility, "
            "deterministic_features, semantic_scores, redacted_text_envelope, "
            "offset_map_envelope, reflective_word_count, model_id, prompt_version) "
            "VALUES (%s, %s, 'unclear', 'uncertain', 'uncertain', '{}'::jsonb, "
            "%s::jsonb, %s::jsonb, %s::jsonb, 50, 'test-model', 'v1')",
            (
                USER_ONE,
                uncertain_entry,
                json.dumps(
                    {
                        "lived_experience_score": 0.5,
                        "self_reference_score": 0.5,
                        "emotional_information_score": 0.5,
                        "causal_reasoning_score": 0.5,
                        "personal_relevance_score": 0.5,
                        "confidence": 0.5,
                    }
                ),
                json.dumps(ENVELOPE_V1),
                json.dumps(ENVELOPE_V1),
            ),
        )
        latest_entry = insert_entry(connection, USER_ONE, entry_date="2026-07-01")
        _, latest_signal, latest_source = insert_analysis_signal(
            connection, USER_ONE, latest_entry
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) "
            "VALUES (%s, %s, 3, 3, ARRAY['2026-01-01'::date, '2026-06-01'::date, "
            "'2026-07-01'::date])",
            (USER_ONE, latest_source),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            job_id = connection.execute(
                "SELECT public.enqueue_processing_job(%s, NULL, 'reflection_synthesis', %s, "
                "pg_catalog.now())",
                (USER_ONE, str(latest_source)),
            ).fetchone()[0]
            claim = connection.execute(
                "SELECT claim_token FROM public.claim_processing_job('basis-worker')"
            ).fetchone()[0]
            basis = connection.execute(
                "SELECT public.get_reflection_synthesis_basis(%s, 'basis-worker', %s, 90)",
                (job_id, claim),
            ).fetchone()[0]
            assert basis["basis_start"] == "2026-04-03"
            assert basis["basis_end"] == "2026-07-01"
            assert basis["valid_entry_count"] == 2
            assert basis["excluded_entry_count"] == 1
            assert {item["id"] for item in basis["signals"]} == {
                str(inside_signal),
                str(latest_signal),
            }
            assert str(old_signal) not in json.dumps(basis)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(
                    "SELECT public.get_reflection_synthesis_basis("
                    "%s, 'basis-worker', %s, 89)",
                    (job_id, claim),
                )


def test_database_rejected_candidate_reentry_requires_three_new_entries_on_two_dates() -> None:
    value = database_url()
    bootstrap(value, USER_ONE)
    with psycopg.connect(value) as connection:
        old_entry = insert_entry(connection, USER_ONE, entry_date="2026-07-01")
        _, _, rejected_source = insert_analysis_signal(
            connection, USER_ONE, old_entry
        )
        new_signal_ids: list[UUID] = []
        latest_source = rejected_source
        for entry_date in ("2026-07-10", "2026-07-10", "2026-07-11"):
            entry_id = insert_entry(connection, USER_ONE, entry_date=entry_date)
            _, signal_id, latest_source = insert_analysis_signal(
                connection, USER_ONE, entry_id
            )
            new_signal_ids.append(signal_id)
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version) VALUES (%s, %s)",
            (USER_ONE, latest_source),
        )
        candidate_id = uuid4()
        connection.execute(
            "INSERT INTO public.pattern_candidates "
            "(id, user_id, pattern_type, canonical_key, status, score, "
            "score_components, payload_envelope, first_seen_at, last_seen_at, "
            "rejected_at, rejected_source_version, last_source_version) "
            "VALUES (%s, %s, 'hidden_driver', %s, 'rejected', 0.8, %s::jsonb, "
            "%s::jsonb, pg_catalog.now(), pg_catalog.now(), pg_catalog.now(), %s, %s)",
            (
                candidate_id,
                USER_ONE,
                "d" * 64,
                json.dumps({"recurrence": 0.8}),
                json.dumps(ENVELOPE_V1),
                rejected_source,
                rejected_source,
            ),
        )
        connection.commit()

        reentry = candidate_payload(
            candidate_id,
            canonical_key="d" * 64,
            version=2,
            publication_gate_passed=True,
        )
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            with connection.transaction():
                worker(connection)
                connection.execute(
                    "SELECT public.apply_deterministic_reflection_candidates("
                    "%s, %s, %s::jsonb, %s::jsonb)",
                    (
                        USER_ONE,
                        latest_source,
                        json.dumps([reentry]),
                        json.dumps(
                            [
                                evidence_payload(candidate_id, signal_id)
                                for signal_id in new_signal_ids[:2]
                            ]
                        ),
                    ),
                )
        assert connection.execute(
            "SELECT status, last_source_version FROM public.pattern_candidates WHERE id = %s",
            (candidate_id,),
        ).fetchone() == ("rejected", rejected_source)

        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.apply_deterministic_reflection_candidates("
                "%s, %s, %s::jsonb, %s::jsonb)",
                (
                    USER_ONE,
                    latest_source,
                    json.dumps([reentry]),
                    json.dumps(
                        [
                            evidence_payload(candidate_id, signal_id)
                            for signal_id in new_signal_ids
                        ]
                    ),
                ),
            ).fetchone() == (1,)
        admin(connection)
        assert connection.execute(
            "SELECT status, rejected_at, rejected_source_version, last_source_version "
            "FROM public.pattern_candidates WHERE id = %s",
            (candidate_id,),
        ).fetchone() == ("candidate", None, None, latest_source)


def test_reflection_api_read_rpc_is_authenticated_owner_checked_and_bounded() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    with psycopg.connect(value) as connection:
        entry_id = insert_entry(connection, USER_ONE, entry_date="2026-07-20")
        insert_analysis_signal(connection, USER_ONE, entry_id)
        connection.commit()

        owner(connection, USER_ONE)
        payload = connection.execute(
            "SELECT public.get_reflections_for_owner(%s, 12)", (USER_ONE,)
        ).fetchone()[0]
        assert payload["snapshot"] is None
        assert payload["current_basis"]["valid_entry_count"] == 1
        assert payload["current_basis"]["basis_start"] == "2026-04-22"
        assert payload["current_basis"]["basis_end"] == "2026-07-20"
        assert payload["evidence"] == []
        connection.rollback()

        snapshot_id = uuid4()
        insight_id = uuid4()
        admin(connection)
        connection.execute(
            "INSERT INTO public.reflection_snapshots "
            "(id, user_id, version, source_version, basis_start, basis_end, "
            "valid_entry_count, excluded_entry_count, distinct_entry_dates, "
            "reflective_word_count) "
            "VALUES (%s, %s, 1, 1, '2026-07-20', '2026-07-20', 1, 0, 1, 20)",
            (snapshot_id, USER_ONE),
        )
        connection.execute(
            "INSERT INTO public.reflection_snapshot_insights "
            "(id, user_id, snapshot_id, pattern_type, ordinal, status, reason_code) "
            "VALUES (%s, %s, %s, 'hidden_driver', 0, "
            "'insufficient_evidence', 'DRIVER_NOT_REPEATED')",
            (insight_id, USER_ONE, snapshot_id),
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, last_snapshot_source_version, "
            "last_successful_snapshot_id) VALUES (%s, 1, 1, %s) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "last_snapshot_source_version = EXCLUDED.last_snapshot_source_version, "
            "last_successful_snapshot_id = EXCLUDED.last_successful_snapshot_id",
            (USER_ONE, snapshot_id),
        )
        connection.commit()

        owner(connection, USER_ONE)
        payload = connection.execute(
            "SELECT public.get_reflections_for_owner(%s, 12)", (USER_ONE,)
        ).fetchone()[0]
        assert payload["snapshot"]["id"] == str(snapshot_id)
        assert payload["insights"][0]["id"] == str(insight_id)
        connection.rollback()

        owner(connection, USER_TWO)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "SELECT public.get_reflections_for_owner(%s, 12)", (USER_ONE,)
            )
        connection.rollback()

        owner(connection, USER_ONE)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "SELECT public.get_reflections_for_owner(%s, 13)", (USER_ONE,)
            )
def test_observability_rpcs_are_worker_only_and_report_scheduler_and_queue_counts() -> None:
    value = database_url()
    bootstrap(value, USER_ONE)
    with psycopg.connect(value) as connection:
        connection.execute(
            "UPDATE public.user_profiles SET timezone = 'Asia/Kolkata' "
            "WHERE user_id = %s",
            (USER_ONE,),
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) "
            "VALUES (%s, 21, 3, 1, ARRAY['2026-07-21'::date])",
            (USER_ONE,),
        )
        connection.commit()

        owner(connection, USER_ONE)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "SELECT * FROM public.get_processing_queue_observability()"
            )
        connection.rollback()

        with connection.transaction():
            worker(connection)
            stats = connection.execute(
                "SELECT public.schedule_reflection_jobs_observed(%s, %s, %s)",
                (
                    "2026-07-21 12:31:00+00",
                    "publish",
                    [USER_ONE],
                ),
            ).fetchone()[0]
            assert stats == {"checked": 1, "eligible": 1, "enqueued": 1}
            queue = connection.execute(
                "SELECT * FROM public.get_processing_queue_observability()"
            ).fetchall()
            assert [row[0] for row in queue] == [
                "entry_processing",
                "reflection_synthesis",
            ]
            assert queue[0][1:] == (0, 0)
            assert queue[1][1] == 1
            assert queue[1][2] >= 0
