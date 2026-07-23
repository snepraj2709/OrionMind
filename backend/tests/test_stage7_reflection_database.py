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
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.modules.review.repository import (
    ReviewItemNotFoundError,
    ReviewItemStaleError,
    ReviewRepository,
    ReviewRepositoryDataError,
)
from app.shared.security.encryption import AesGcmContentCipher
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
TEST_CIPHER = AesGcmContentCipher(
    encryption_keys={"test-key": b"e" * 32},
    active_encryption_key_id="test-key",
    fingerprint_keys={"test-fingerprint": b"f" * 32},
    active_fingerprint_key_id="test-fingerprint",
)
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
    "review_items",
)
USER_OWNED_NEW_TABLES = tuple(
    table for table in NEW_TABLES if table != "processing_backfill_runs"
)
NEW_FUNCTIONS = (
    "apply_combined_entry_processing_job",
    "apply_deterministic_reflection_candidates",
    "apply_weighted_deterministic_reflection_candidates",
    "apply_weighted_reflection_snapshot",
    "apply_entry_analysis",
    "apply_reflection_snapshot",
    "claim_processing_job",
    "complete_reflection_shadow",
    "complete_processing_job",
    "delete_entry_with_reflection_for_owner",
    "enqueue_processing_job",
    "enqueue_processing_job_for_owner",
    "fail_processing_job",
    "find_signal_semantic_neighbors",
    "get_user_pii_vault_for_update",
    "get_entry_processing_payload",
    "get_entry_processing_backfill_status",
    "get_processing_queue_observability",
    "get_entry_quality_history",
    "get_signal_embedding_backfill_status",
    "get_reflection_candidate_basis",
    "get_reflection_recalculation_basis_for_owner",
    "get_reflection_synthesis_basis",
    "get_reflections_for_owner",
    "is_reflection_recalculation_eligible",
    "is_unit_interval_json_object",
    "is_valid_encrypted_envelope_v1",
    "materialize_entry_review_items",
    "put_reflection_feedback_for_owner",
    "put_review_feedback_for_owner",
    "plan_entry_processing_backfill",
    "claim_signal_embedding_backfill_batch",
    "recover_stale_processing_jobs",
    "retry_entry_processing_for_owner",
    "renew_processing_job",
    "release_signal_embedding_backfill_batch",
    "request_reflection_synthesis_if_eligible",
    "request_reflection_recalculation_for_owner",
    "run_entry_processing_backfill_batch",
    "save_user_pii_vault",
    "schedule_reflection_jobs",
    "schedule_reflection_jobs_observed",
    "set_entry_processing_backfill_state",
    "store_entry_signal_embeddings",
    "store_signal_embedding_backfill_batch",
)
RETIRED_ENTRY_APPLY_SIGNATURE = (
    "public.apply_legacy_entry_processing_job("
    "uuid,text,uuid,uuid,text,jsonb,jsonb,jsonb,jsonb)"
)
RETIRED_WEIGHT_BYPASS_SIGNATURES = (
    "public.apply_deterministic_reflection_candidates(uuid,bigint,jsonb,jsonb)",
    "public.apply_reflection_snapshot(uuid,text,uuid,jsonb,jsonb,jsonb,jsonb,jsonb)",
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


def grant_retired_weight_bypasses_for_behavior_test(
    connection: psycopg.Connection,
) -> None:
    connection.execute(
        "GRANT EXECUTE ON FUNCTION "
        "public.apply_deterministic_reflection_candidates(uuid,bigint,jsonb,jsonb) "
        "TO orion_worker"
    )
    connection.execute(
        "GRANT EXECUTE ON FUNCTION "
        "public.apply_reflection_snapshot("
        "uuid,text,uuid,jsonb,jsonb,jsonb,jsonb,jsonb) TO orion_worker"
    )


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
    signal_type: str = "need",
    loop_role: str | None = None,
    need_tag: str = "competence",
    materialize_review: bool = True,
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
    if materialize_review and signal_type in {
        "energy_gain",
        "energy_loss",
        "self_knowledge",
        "realization",
        "explicit_preference",
        "need",
        "belief",
        "avoidance",
        "protective_strategy",
        "conflict",
        "causal_relationship",
    }:
        entry_date = connection.execute(
            "SELECT entry_date FROM public.entries WHERE id = %s AND user_id = %s",
            (entry_id, user_id),
        ).fetchone()[0]
        insert_review_for_signal(
            connection,
            user_id,
            entry_id,
            signal_id,
            entry_date=entry_date.isoformat(),
            item_type=signal_type,
        )
    return analysis_id, signal_id, source_version


def insert_accepted_basis(
    connection: psycopg.Connection,
    user_id: UUID,
    entry_dates: tuple[str, ...],
) -> int:
    latest_source = 0
    for entry_date in entry_dates:
        entry_id = insert_entry(connection, user_id, entry_date=entry_date)
        analysis_id, signal_id, latest_source = insert_analysis_signal(
            connection,
            user_id,
            entry_id,
            signal_type="need",
            loop_role=None,
            materialize_review=False,
        )
        connection.execute(
            "UPDATE public.entry_analyses SET reflective_word_count = 100 "
            "WHERE id = %s",
            (analysis_id,),
        )
        insert_review_for_signal(
            connection,
            user_id,
            entry_id,
            signal_id,
            entry_date=entry_date,
        )
    return latest_source


def insert_review_for_signal(
    connection: psycopg.Connection,
    user_id: UUID,
    entry_id: UUID,
    signal_id: UUID,
    *,
    entry_date: str = "2026-07-20",
    evidence_weight: float = 1.0,
    item_type: str = "need",
) -> UUID:
    review_item_id = uuid4()
    category = (
        "energy"
        if item_type in {"energy_gain", "energy_loss"}
        else (
            "self_knowledge"
            if item_type
            in {"self_knowledge", "realization", "explicit_preference"}
            else "needs_beliefs"
        )
    )
    review_status = {
        1.0: "pending",
        0.5: "partially_confirmed",
        0.0: "rejected",
    }[evidence_weight]
    verdict = {
        1.0: None,
        0.5: "partly_accurate",
        0.0: "not_accurate",
    }[evidence_weight]
    feedback = (
        None
        if verdict is None
        else json.dumps({"verdict": verdict, "updated_at": "2026-07-20T00:00:00Z"})
    )
    connection.execute(
        "INSERT INTO public.review_items "
        "(id, user_id, entry_id, entry_signal_id, scope, item_type, category, "
        "statement_envelope, source_quote_envelope, source_entry_ids, "
        "source_dates, inference_level, model_confidence, review_status, "
        "user_feedback, evidence_weight, reflection_eligible, metadata) "
        "VALUES (%s, %s, %s, %s, 'entry_insight', %s, %s, "
        "%s::jsonb, %s::jsonb, ARRAY[%s], ARRAY[%s::date], 'inferred', "
        "0.9, %s, %s::jsonb, %s, true, '{}'::jsonb)",
        (
            review_item_id,
            user_id,
            entry_id,
            signal_id,
            item_type,
            category,
            json.dumps(ENVELOPE_V1),
            json.dumps(ENVELOPE_V1),
            entry_id,
            entry_date,
            review_status,
            feedback,
            evidence_weight,
        ),
    )
    return review_item_id


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


def insert_pattern_candidate(
    connection: psycopg.Connection,
    user_id: UUID,
    *,
    pattern_type: str = "hidden_driver",
) -> UUID:
    candidate_id = uuid4()
    connection.execute(
        "INSERT INTO public.pattern_candidates "
        "(id, user_id, pattern_type, canonical_key, status, score, "
        "score_components, payload_envelope, first_seen_at, last_seen_at) "
        "VALUES (%s, %s, %s, %s, 'published', 0.8, %s::jsonb, %s::jsonb, "
        "'2026-07-01T00:00:00Z', '2026-07-20T00:00:00Z')",
        (
            candidate_id,
            user_id,
            pattern_type,
            candidate_id.hex * 2,
            json.dumps({"recurrence": 0.8}),
            json.dumps(ENVELOPE_V1),
        ),
    )
    return candidate_id


def insert_review_item(
    connection: psycopg.Connection,
    *,
    user_id: UUID,
    entry_id: UUID | None = None,
    entry_signal_id: UUID | None = None,
    pattern_candidate_id: UUID | None = None,
    scope: str = "entry_insight",
    item_type: str = "realization",
    category: str = "self_knowledge",
    inference_level: str = "direct",
    source_entry_ids: list[UUID] | None = None,
    source_dates: list[str] | None = None,
    review_status: str = "pending",
    user_feedback: dict[str, object] | None = None,
    evidence_weight: float = 1.0,
    reflection_eligible: bool = True,
    item_id: UUID | None = None,
    statement: str = "You value focused work.",
    source_quote: str | None = "I value focused work.",
    corrected_statement: str | None = None,
    feedback_note: str | None = None,
    statement_envelope: dict[str, object] | None = None,
    created_at: str = "2026-07-20T12:00:00Z",
) -> UUID:
    item_id = item_id or uuid4()
    if source_entry_ids is None:
        source_entry_ids = [entry_id] if entry_id is not None else [uuid4()]
    if source_dates is None:
        source_dates = ["2026-07-20"]
    encrypted_statement = (
        statement_envelope
        if statement_envelope is not None
        else TEST_CIPHER.encrypt_json(
            statement,
            user_id=user_id,
            record_id=item_id,
            purpose="review_item_statement",
        )
    )
    encrypted_quote = (
        TEST_CIPHER.encrypt_json(
            source_quote,
            user_id=user_id,
            record_id=item_id,
            purpose="review_item_source_quote",
        )
        if source_quote is not None
        else None
    )
    encrypted_correction = (
        TEST_CIPHER.encrypt_json(
            corrected_statement,
            user_id=user_id,
            record_id=item_id,
            purpose="review_item_corrected_statement",
        )
        if corrected_statement is not None
        else None
    )
    encrypted_note = (
        TEST_CIPHER.encrypt_json(
            feedback_note,
            user_id=user_id,
            record_id=item_id,
            purpose="review_item_feedback_note",
        )
        if feedback_note is not None
        else None
    )
    connection.execute(
        "INSERT INTO public.review_items "
        "(id, user_id, entry_id, entry_signal_id, pattern_candidate_id, scope, "
        "item_type, category, statement_envelope, source_quote_envelope, "
        "source_entry_ids, source_dates, inference_level, model_confidence, "
        "review_status, user_feedback, corrected_statement_envelope, "
        "feedback_note_envelope, evidence_weight, reflection_eligible, metadata, "
        "created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, "
        "%s::uuid[], %s::date[], %s, 0.9, %s, %s::jsonb, %s::jsonb, %s::jsonb, "
        "%s, %s, %s::jsonb, %s)",
        (
            item_id,
            user_id,
            entry_id,
            entry_signal_id,
            pattern_candidate_id,
            scope,
            item_type,
            category,
            json.dumps(encrypted_statement),
            json.dumps(encrypted_quote) if encrypted_quote is not None else None,
            source_entry_ids,
            source_dates,
            inference_level,
            review_status,
            json.dumps(user_feedback) if user_feedback is not None else None,
            (
                json.dumps(encrypted_correction)
                if encrypted_correction is not None
                else None
            ),
            json.dumps(encrypted_note) if encrypted_note is not None else None,
            evidence_weight,
            reflection_eligible,
            json.dumps({"prompt_version": "test-v1"}),
            created_at,
        ),
    )
    return item_id


def vector_value(first: float, second: float = 0.0) -> str:
    return "[" + ",".join(
        [str(first), str(second), *("0" for _index in range(1534))]
    ) + "]"


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
        "0014_reflection_on_demand.sql",
        "0015_fix_reflection_job_expedite.sql",
        "0016_signal_embeddings.sql",
        "0017_reflection_recalculation_eligibility.sql",
        "0018_semantic_signal_retrieval.sql",
        "0019_review_items.sql",
        "0020_review_item_materialization.sql",
        "0021_review_feedback.sql",
        "0022_review_weighted_reflections.sql",
        "0023_reflection_recalculation.sql",
        "0024_reflection_deletion_source_version.sql",
        "0025_reflection_deletion_race_guard.sql",
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
        embedding_rpc_privileges = connection.execute(
            "SELECT role_name, pg_catalog.has_function_privilege("
            "role_name, 'public.store_entry_signal_embeddings(uuid,uuid,jsonb,text)', "
            "'EXECUTE') FROM pg_catalog.unnest("
            "ARRAY['anon', 'authenticated', 'orion_app', 'orion_worker']) AS role_name "
            "ORDER BY role_name"
        ).fetchall()
        assert embedding_rpc_privileges == [
            ("anon", False),
            ("authenticated", False),
            ("orion_app", False),
            ("orion_worker", True),
        ]
        for signature in RETIRED_WEIGHT_BYPASS_SIGNATURES:
            assert connection.execute(
                "SELECT pg_catalog.has_function_privilege("
                "'orion_worker', %s, 'EXECUTE')",
                (signature,),
            ).fetchone() == (False,)
        for signature in (
            "public.find_signal_semantic_neighbors(uuid,uuid[],bigint,text,integer,numeric)",
            "public.get_signal_embedding_backfill_status(text)",
            "public.claim_signal_embedding_backfill_batch(integer,text)",
            "public.store_signal_embedding_backfill_batch(uuid,jsonb,text)",
            "public.release_signal_embedding_backfill_batch(uuid)",
        ):
            privileges = connection.execute(
                "SELECT role_name, pg_catalog.has_function_privilege("
                "role_name, %s, 'EXECUTE') FROM pg_catalog.unnest("
                "ARRAY['anon', 'authenticated', 'orion_app', 'orion_worker']) "
                "AS role_name ORDER BY role_name",
                (signature,),
            ).fetchall()
            assert privileges == [
                ("anon", False),
                ("authenticated", False),
                ("orion_app", False),
                ("orion_worker", True),
            ]
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
            connection,
            USER_ONE,
            entry_one,
            signal_type="self_statement",
            loop_role="interpretation",
            materialize_review=False,
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
        source_one = insert_accepted_basis(
            connection, USER_ONE, ("2026-07-20", "2026-07-21", "2026-07-21")
        )
        source_two = insert_accepted_basis(
            connection, USER_TWO, ("2026-07-20", "2026-07-21")
        )
        source_three = insert_accepted_basis(
            connection, USER_THREE, ("2026-07-20", "2026-07-21", "2026-07-21")
        )
        connection.execute(
            "DELETE FROM public.entry_signals WHERE user_id = %s", (USER_THREE,)
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) VALUES "
            "(%s, %s, 3, 3, ARRAY['2026-07-20'::date, '2026-07-21'::date]), "
            "(%s, %s, 2, 2, ARRAY['2026-07-20'::date, '2026-07-21'::date]), "
            "(%s, %s, 3, 0, ARRAY['2026-07-20'::date, '2026-07-21'::date])",
            (USER_ONE, source_one, USER_TWO, source_two, USER_THREE, source_three),
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
        ).fetchall() == [(USER_ONE, str(source_one))]
        assert connection.execute(
            "SELECT user_id, last_schedule_local_date FROM public.reflection_user_state "
            "ORDER BY user_id"
        ).fetchall() == [
            (USER_ONE, datetime(2026, 7, 21).date()),
            (USER_TWO, datetime(2026, 7, 21).date()),
            (USER_THREE, datetime(2026, 7, 21).date()),
        ]
        admin(connection)
        entry_two_refresh = insert_entry(connection, USER_TWO, entry_date="2026-07-21")
        analysis_two_refresh, signal_two_refresh, source_two_refresh = (
            insert_analysis_signal(
                connection,
                USER_TWO,
                entry_two_refresh,
                signal_type="need",
                loop_role=None,
                materialize_review=False,
            )
        )
        insert_review_for_signal(
            connection,
            USER_TWO,
            entry_two_refresh,
            signal_two_refresh,
            entry_date="2026-07-21",
        )
        connection.execute(
            "UPDATE public.entry_analyses SET reflective_word_count = 100 WHERE id = %s",
            (analysis_two_refresh,),
        )
        connection.execute(
            "UPDATE public.reflection_user_state "
            "SET latest_accepted_source_version = %s, new_valid_entries = 3, "
            "new_accepted_signals = 1, pending_local_dates = ARRAY['2026-07-21'::date] "
            "WHERE user_id = %s",
            (source_two_refresh, USER_TWO),
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
            "AND job_type = 'reflection_synthesis' AND source_version = %s",
            (USER_TWO, str(source_two_refresh)),
        ).fetchone() == (1,)
        admin(connection)
        connection.execute(
            "UPDATE public.user_profiles SET timezone = 'America/New_York' WHERE user_id = %s",
            (USER_THREE,),
        )
        source_three_refresh = insert_accepted_basis(
            connection,
            USER_THREE,
            ("2026-07-21", "2026-07-22", "2026-07-22"),
        )
        connection.execute(
            "UPDATE public.reflection_user_state SET latest_accepted_source_version = %s, "
            "new_valid_entries = 3, new_accepted_signals = 1, "
            "pending_local_dates = ARRAY['2026-07-22'::date], "
            "last_schedule_local_date = '2026-07-21' WHERE user_id = %s",
            (source_three_refresh, USER_THREE),
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
            "AND job_type = 'reflection_synthesis' AND source_version = %s",
            (USER_THREE, str(source_three_refresh)),
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
        source_one = insert_accepted_basis(
            connection, USER_ONE, ("2026-03-07", "2026-03-08", "2026-03-08")
        )
        source_two = insert_accepted_basis(
            connection, USER_TWO, ("2026-03-28", "2026-03-29", "2026-03-29")
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates, last_schedule_local_date) VALUES "
            "(%s, %s, 3, 1, ARRAY['2026-03-07'::date, '2026-03-08'::date], NULL), "
            "(%s, %s, 3, 1, ARRAY['2026-03-28'::date, '2026-03-29'::date], '2026-03-08')",
            (USER_ONE, source_one, USER_TWO, source_two),
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
            "latest_accepted_source_version = CASE WHEN user_id = %s THEN %s ELSE %s END "
            "WHERE user_id IN (%s, %s)",
            (USER_ONE, USER_ONE, source_one, source_two, USER_ONE, USER_TWO),
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
        concurrent_source = source_two + 1
        connection.execute(
            "UPDATE public.reflection_user_state SET last_schedule_local_date = NULL, "
            "latest_accepted_source_version = %s WHERE user_id = %s",
            (concurrent_source, USER_TWO),
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
            "AND job_type = 'reflection_synthesis' AND source_version = %s",
            (USER_TWO, str(concurrent_source)),
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
        source_version = insert_accepted_basis(
            connection, USER_ONE, ("2026-07-19", "2026-07-20", "2026-07-20")
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) VALUES "
            "(%s, %s, 3, 3, ARRAY['2026-07-19'::date, '2026-07-20'::date])",
            (USER_ONE, source_version),
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
        grant_retired_weight_bypasses_for_behavior_test(connection)
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
        source_before_delete = connection.execute(
            "SELECT latest_accepted_source_version "
            "FROM public.reflection_user_state WHERE user_id = %s",
            (USER_ONE,),
        ).fetchone()[0]
        connection.commit()
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
        assert connection.execute(
            "SELECT latest_accepted_source_version > %s "
            "FROM public.reflection_user_state WHERE user_id = %s",
            (source_before_delete, USER_ONE),
        ).fetchone() == (True,)


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
        grant_retired_weight_bypasses_for_behavior_test(connection)
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
        grant_retired_weight_bypasses_for_behavior_test(connection)
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
        grant_retired_weight_bypasses_for_behavior_test(connection)
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


def test_reflection_api_evidence_counts_are_snapshot_distinct_entries_per_insight() -> None:
    value = database_url()
    bootstrap(value, USER_ONE)
    with psycopg.connect(value) as connection:
        signals: list[tuple[UUID, UUID]] = []
        latest_source = 0
        for entry_date in ("2026-07-18", "2026-07-19", "2026-07-20"):
            entry_id = insert_entry(connection, USER_ONE, entry_date=entry_date)
            _, signal_id, latest_source = insert_analysis_signal(
                connection, USER_ONE, entry_id
            )
            signals.append((entry_id, signal_id))

        duplicate_step_signal = uuid4()
        connection.execute(
            "INSERT INTO public.entry_signals "
            "(id, user_id, entry_id, analysis_id, signal_type, "
            "normalized_label_fingerprint, payload_envelope, themes, need_tags, "
            "loop_role, confidence, source_start, source_end, occurred_on) "
            "SELECT %s, user_id, entry_id, analysis_id, signal_type, %s, "
            "payload_envelope, themes, need_tags, loop_role, confidence, 1, 4, "
            "occurred_on FROM public.entry_signals WHERE id = %s",
            (duplicate_step_signal, "e" * 64, signals[0][1]),
        )

        snapshot_id = uuid4()
        connection.execute(
            "INSERT INTO public.reflection_snapshots "
            "(id, user_id, version, source_version, basis_start, basis_end, "
            "valid_entry_count, excluded_entry_count, distinct_entry_dates, "
            "reflective_word_count) "
            "VALUES (%s, %s, 1, %s, '2026-07-18', '2026-07-20', 3, 0, 3, 300)",
            (snapshot_id, USER_ONE, latest_source),
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, last_snapshot_source_version, "
            "last_successful_snapshot_id) VALUES (%s, %s, %s, %s)",
            (USER_ONE, latest_source, latest_source, snapshot_id),
        )

        insights: dict[tuple[str, int], UUID] = {}
        for index, (pattern_type, ordinal) in enumerate(
            (
                ("hidden_driver", 0),
                ("recurring_loop", 0),
                ("inner_tension", 0),
                ("inner_tension", 1),
            )
        ):
            candidate_id = uuid4()
            insight_id = uuid4()
            insights[(pattern_type, ordinal)] = insight_id
            connection.execute(
                "INSERT INTO public.pattern_candidates "
                "(id, user_id, pattern_type, canonical_key, status, score, "
                "score_components, payload_envelope, first_seen_at, last_seen_at, "
                "last_source_version) VALUES (%s, %s, %s, %s, 'published', 0.8, "
                "%s::jsonb, %s::jsonb, pg_catalog.now(), pg_catalog.now(), %s)",
                (
                    candidate_id,
                    USER_ONE,
                    pattern_type,
                    f"{index + 1:x}" * 64,
                    json.dumps({"recurrence": 0.8}),
                    json.dumps(ENVELOPE_V1),
                    latest_source,
                ),
            )
            connection.execute(
                "INSERT INTO public.reflection_snapshot_insights "
                "(id, user_id, snapshot_id, candidate_id, pattern_type, ordinal, "
                "status, payload_envelope, confidence_label, score) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'available', %s::jsonb, "
                "'emerging', 0.8)",
                (
                    insight_id,
                    USER_ONE,
                    snapshot_id,
                    candidate_id,
                    pattern_type,
                    ordinal,
                    json.dumps(ENVELOPE_V1),
                ),
            )

        evidence_by_insight = {
            insights[("hidden_driver", 0)]: [
                (*signals[0], "supporting"),
                (*signals[1], "supporting"),
                (*signals[2], "counter"),
            ],
            insights[("recurring_loop", 0)]: [
                (*signals[0], "supporting"),
                (signals[0][0], duplicate_step_signal, "supporting"),
                (*signals[1], "supporting"),
            ],
            insights[("inner_tension", 0)]: [
                (*signals[0], "supporting"),
                (*signals[1], "counter"),
            ],
            insights[("inner_tension", 1)]: [(*signals[2], "supporting")],
        }
        for insight_id, evidence_rows in evidence_by_insight.items():
            for ordinal, (entry_id, signal_id, role) in enumerate(evidence_rows):
                connection.execute(
                    "INSERT INTO public.reflection_snapshot_evidence "
                    "(insight_id, signal_id, entry_id, user_id, evidence_role, "
                    "ordinal, source_start, source_end) "
                    "VALUES (%s, %s, %s, %s, %s, %s, 0, 4)",
                    (insight_id, signal_id, entry_id, USER_ONE, role, ordinal),
                )
        connection.commit()

        with connection.transaction():
            owner(connection, USER_ONE)
            payload = connection.execute(
                "SELECT public.get_reflections_for_owner(%s, 1)", (USER_ONE,)
            ).fetchone()[0]

        counts = {
            (row["pattern_type"], row["ordinal"]): row["evidence_entry_count"]
            for row in payload["insights"]
        }
        assert counts == {
            ("hidden_driver", 0): 2,
            ("recurring_loop", 0): 2,
            ("inner_tension", 0): 1,
            ("inner_tension", 1): 1,
        }


def test_semantic_neighbors_are_owner_basis_model_same_entry_and_topk_scoped() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    model_id = "text-embedding-3-small"
    with psycopg.connect(value) as connection:
        def stored_signal(
            user_id: UUID,
            entry_date: str,
            vector: str | None,
            *,
            embedding_model: str = model_id,
        ) -> tuple[UUID, UUID, int]:
            entry_id = insert_entry(connection, user_id, entry_date=entry_date)
            analysis_id, signal_id, source_version = insert_analysis_signal(
                connection, user_id, entry_id
            )
            if vector is not None:
                connection.execute(
                    "UPDATE public.entry_signals SET embedding = %s::extensions.vector, "
                    "embedding_model = %s, embedded_at = pg_catalog.now() WHERE id = %s",
                    (vector, embedding_model, signal_id),
                )
            return analysis_id, signal_id, source_version

        _, anchor_id, source_version = stored_signal(
            USER_ONE, "2026-07-01", vector_value(1)
        )
        _, nearest_id, source_version = stored_signal(
            USER_ONE, "2026-07-08", vector_value(0.999, 0.001)
        )
        _, second_id, source_version = stored_signal(
            USER_ONE, "2026-07-09", vector_value(0.98, 0.02)
        )
        _, _, source_version = stored_signal(
            USER_ONE, "2026-07-10", vector_value(0, 1)
        )
        _, _, source_version = stored_signal(
            USER_ONE,
            "2026-07-11",
            vector_value(1),
            embedding_model="different-model",
        )
        _, _, source_version = stored_signal(USER_ONE, "2026-07-12", None)
        _, _, source_version = stored_signal(
            USER_ONE, "2026-01-01", vector_value(1)
        )
        _, foreign_id, _ = stored_signal(USER_TWO, "2026-07-08", vector_value(1))

        same_entry_signal = uuid4()
        connection.execute(
            "INSERT INTO public.entry_signals "
            "(id, user_id, entry_id, analysis_id, signal_type, "
            "normalized_label_fingerprint, payload_envelope, themes, need_tags, "
            "loop_role, confidence, source_start, source_end, occurred_on, "
            "embedding, embedding_model, embedded_at) "
            "SELECT %s, user_id, entry_id, analysis_id, signal_type, %s, "
            "payload_envelope, themes, need_tags, loop_role, confidence, 1, 4, "
            "occurred_on, %s::extensions.vector, %s, pg_catalog.now() "
            "FROM public.entry_signals WHERE id = %s",
            (same_entry_signal, "b" * 64, vector_value(1), model_id, anchor_id),
        )
        connection.commit()

        with connection.transaction():
            worker(connection)
            rows = connection.execute(
                "SELECT anchor_signal_id, neighbor_signal_id, similarity "
                "FROM public.find_signal_semantic_neighbors(%s, %s, %s, %s, 1, 0.90)",
                (USER_ONE, [anchor_id], source_version, model_id),
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == anchor_id
            assert rows[0][1] == nearest_id
            assert rows[0][2] >= 0.90
            assert rows[0][1] not in {same_entry_signal, foreign_id}

            all_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT neighbor_signal_id "
                    "FROM public.find_signal_semantic_neighbors("
                    "%s, %s, %s, %s, 8, 0.90)",
                    (USER_ONE, [anchor_id], source_version, model_id),
                ).fetchall()
            }
            assert all_ids == {nearest_id, second_id}

            assert connection.execute(
                "SELECT count(*) FROM public.find_signal_semantic_neighbors("
                "%s, %s, %s, %s, 8, 0.90)",
                (USER_ONE, [foreign_id], source_version, model_id),
            ).fetchone() == (0,)


def test_signal_embedding_backfill_store_retry_is_idempotent_after_commit() -> None:
    value = database_url()
    bootstrap(value, USER_ONE)
    model_id = "text-embedding-3-small"
    with psycopg.connect(value) as connection:
        entry_id = insert_entry(connection, USER_ONE, entry_date="2026-07-20")
        _, signal_id, _ = insert_analysis_signal(connection, USER_ONE, entry_id)
        connection.commit()

        with connection.transaction():
            worker(connection)
            batch = connection.execute(
                "SELECT public.claim_signal_embedding_backfill_batch(1, %s)",
                (model_id,),
            ).fetchone()[0]
        batch_token = UUID(batch["batch_token"])
        assert [UUID(item["signal_id"]) for item in batch["items"]] == [signal_id]
        embeddings = json.dumps(
            [{"signal_id": str(signal_id), "values": [1.0, *([0.0] * 1535)]}]
        )

        with connection.transaction():
            worker(connection)
            first = connection.execute(
                "SELECT public.store_signal_embedding_backfill_batch(%s, %s::jsonb, %s)",
                (batch_token, embeddings, model_id),
            ).fetchone()[0]
        stored_at = connection.execute(
            "SELECT embedded_at FROM public.entry_signals WHERE id = %s", (signal_id,)
        ).fetchone()[0]
        connection.commit()

        with connection.transaction():
            worker(connection)
            retried = connection.execute(
                "SELECT public.store_signal_embedding_backfill_batch(%s, %s::jsonb, %s)",
                (batch_token, embeddings, model_id),
            ).fetchone()[0]

        assert first == retried == 1
        altered = json.dumps(
            [{"signal_id": str(signal_id), "values": [0.0, 1.0, *([0.0] * 1534)]}]
        )
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            with connection.transaction():
                worker(connection)
                connection.execute(
                    "SELECT public.store_signal_embedding_backfill_batch("
                    "%s, %s::jsonb, %s)",
                    (batch_token, altered, model_id),
                )

        admin(connection)
        assert connection.execute(
            "SELECT embedding_model, embedded_at, embedding_backfill_token, "
            "extensions.vector_dims(embedding) "
            "FROM public.entry_signals WHERE id = %s",
            (signal_id,),
        ).fetchone() == (model_id, stored_at, batch_token, 1536)


def test_observability_rpcs_are_worker_only_and_report_scheduler_and_queue_counts() -> None:
    value = database_url()
    bootstrap(value, USER_ONE)
    with psycopg.connect(value) as connection:
        connection.execute(
            "UPDATE public.user_profiles SET timezone = 'Asia/Kolkata' "
            "WHERE user_id = %s",
            (USER_ONE,),
        )
        latest_source = 0
        for entry_date in ("2026-07-20", "2026-07-21", "2026-07-21"):
            entry_id = insert_entry(connection, USER_ONE, entry_date=entry_date)
            analysis_id, _, latest_source = insert_analysis_signal(
                connection, USER_ONE, entry_id
            )
            connection.execute(
                "UPDATE public.entry_analyses SET reflective_word_count = 100 "
                "WHERE id = %s",
                (analysis_id,),
            )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) "
            "VALUES (%s, %s, 3, 3, "
            "ARRAY['2026-07-20'::date, '2026-07-21'::date])",
            (USER_ONE, latest_source),
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


def test_recalculation_eligibility_boundaries_and_atomic_request() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    check_at = "2026-07-22 12:00:00+00"
    with psycopg.connect(value) as connection:
        baseline_entry = insert_entry(connection, USER_ONE, entry_date="2026-07-01")
        baseline_analysis, _, baseline_source = insert_analysis_signal(
            connection, USER_ONE, baseline_entry
        )
        connection.execute(
            "UPDATE public.entry_analyses SET reflective_word_count = 200 "
            "WHERE id = %s",
            (baseline_analysis,),
        )
        snapshot_id = uuid4()
        connection.execute(
            "INSERT INTO public.reflection_snapshots "
            "(id, user_id, version, source_version, basis_start, basis_end, "
            "valid_entry_count, excluded_entry_count, distinct_entry_dates, "
            "reflective_word_count) "
            "VALUES (%s, %s, 1, %s, '2026-04-03', '2026-07-01', 3, 0, 2, 200)",
            (snapshot_id, USER_ONE, baseline_source),
        )
        pending_entry = insert_entry(connection, USER_ONE, entry_date="2026-07-20")
        pending_analysis, _, pending_source = insert_analysis_signal(
            connection, USER_ONE, pending_entry
        )
        connection.execute(
            "UPDATE public.entry_analyses SET reflective_word_count = 499 "
            "WHERE id = %s",
            (pending_analysis,),
        )
        connection.execute(
            "UPDATE public.entries SET created_at = '2026-07-20 12:00:00+00' "
            "WHERE id = %s",
            (pending_entry,),
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, last_snapshot_source_version, "
            "new_valid_entries, new_accepted_signals, pending_local_dates, "
            "last_successful_snapshot_id) "
            "VALUES (%s, %s, %s, 1, 1, ARRAY['2026-07-20'::date], %s)",
            (USER_ONE, pending_source, baseline_source, snapshot_id),
        )
        connection.commit()

        with connection.transaction():
            owner(connection, USER_ONE)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(
                    "SELECT public.is_reflection_recalculation_eligible(%s, %s)",
                    (USER_ONE, check_at),
                )
        with connection.transaction():
            owner(connection, USER_ONE)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(
                    "SELECT * FROM public.request_reflection_synthesis_if_eligible("
                    "%s, %s)",
                    (USER_ONE, check_at),
                )

        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.is_reflection_recalculation_eligible(%s, %s)",
                (USER_ONE, check_at),
            ).fetchone() == (False,)
            assert connection.execute(
                "SELECT * FROM public.request_reflection_synthesis_if_eligible(%s, %s)",
                (USER_ONE, check_at),
            ).fetchone() is None

        admin(connection)
        connection.execute(
            "UPDATE public.entry_analyses SET reflective_word_count = 500 "
            "WHERE id = %s",
            (pending_analysis,),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.is_reflection_recalculation_eligible(%s, %s)",
                (USER_ONE, check_at),
            ).fetchone() == (True,)
            request = connection.execute(
                "SELECT * FROM public.request_reflection_synthesis_if_eligible(%s, %s)",
                (USER_ONE, check_at),
            ).fetchone()
            assert request is not None and request[1] == pending_source
            replay = connection.execute(
                "SELECT * FROM public.request_reflection_synthesis_if_eligible(%s, %s)",
                (USER_ONE, check_at),
            ).fetchone()
            assert replay == request

        admin(connection)
        assert connection.execute(
            "SELECT count(*) FROM public.processing_jobs "
            "WHERE user_id = %s AND job_type = 'reflection_synthesis'",
            (USER_ONE,),
        ).fetchone() == (1,)

        connection.execute(
            "DELETE FROM public.processing_jobs "
            "WHERE user_id = %s AND job_type = 'reflection_synthesis'",
            (USER_ONE,),
        )
        connection.execute(
            "UPDATE public.entry_analyses SET reflective_word_count = 499 "
            "WHERE id = %s",
            (pending_analysis,),
        )
        connection.execute(
            "UPDATE public.entries SET created_at = '2026-07-19 12:00:00+00' "
            "WHERE id = %s",
            (pending_entry,),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.is_reflection_recalculation_eligible(%s, %s)",
                (USER_ONE, check_at),
            ).fetchone() == (True,)

        admin(connection)
        connection.execute(
            "UPDATE public.entries "
            "SET created_at = '2026-07-19 12:00:01+00' WHERE id = %s",
            (pending_entry,),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.is_reflection_recalculation_eligible(%s, %s)",
                (USER_ONE, check_at),
            ).fetchone() == (False,)

        admin(connection)
        latest_source = pending_source
        for entry_date in ("2026-07-21", "2026-07-22"):
            entry_id = insert_entry(connection, USER_ONE, entry_date=entry_date)
            analysis_id, _, latest_source = insert_analysis_signal(
                connection, USER_ONE, entry_id
            )
            connection.execute(
                "UPDATE public.entry_analyses "
                "SET reflective_word_count = 1, created_at = '2026-07-22 11:00:00+00' "
                "WHERE id = %s",
                (analysis_id,),
            )
        connection.execute(
            "UPDATE public.reflection_user_state "
            "SET latest_accepted_source_version = %s, new_valid_entries = 3, "
            "new_accepted_signals = 3, "
            "pending_local_dates = ARRAY['2026-07-20'::date, "
            "'2026-07-21'::date, '2026-07-22'::date] "
            "WHERE user_id = %s",
            (latest_source, USER_ONE),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.is_reflection_recalculation_eligible(%s, %s)",
                (USER_ONE, check_at),
            ).fetchone() == (True,)

        admin(connection)
        connection.execute(
            "DELETE FROM public.entry_signals WHERE user_id = %s AND analysis_id IN ("
            "SELECT id FROM public.entry_analyses WHERE user_id = %s "
            "AND source_version > %s)",
            (USER_ONE, USER_ONE, baseline_source),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.is_reflection_recalculation_eligible(%s, %s)",
                (USER_ONE, check_at),
            ).fetchone() == (False,)

        admin(connection)
        initial_sources: list[int] = []
        initial_analysis_ids: list[UUID] = []
        initial_entry_ids: list[UUID] = []
        for entry_date in ("2026-07-20", "2026-07-21", "2026-07-21"):
            entry_id = insert_entry(connection, USER_TWO, entry_date=entry_date)
            analysis_id, _, source_version = insert_analysis_signal(
                connection, USER_TWO, entry_id
            )
            initial_entry_ids.append(entry_id)
            initial_analysis_ids.append(analysis_id)
            initial_sources.append(source_version)
        connection.cursor().executemany(
            "UPDATE public.entry_analyses SET reflective_word_count = %s WHERE id = %s",
            [
                (100, initial_analysis_ids[0]),
                (25, initial_analysis_ids[1]),
                (25, initial_analysis_ids[2]),
            ],
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) "
            "VALUES (%s, %s, 3, 3, "
            "ARRAY['2026-07-20'::date, '2026-07-21'::date])",
            (USER_TWO, max(initial_sources)),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.is_reflection_recalculation_eligible(%s, %s)",
                (USER_TWO, check_at),
            ).fetchone() == (True,)

        admin(connection)
        connection.execute(
            "UPDATE public.entry_analyses SET reflective_word_count = 24 WHERE id = %s",
            (initial_analysis_ids[2],),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.is_reflection_recalculation_eligible(%s, %s)",
                (USER_TWO, check_at),
            ).fetchone() == (False,)

        admin(connection)
        connection.execute(
            "UPDATE public.entry_analyses SET reflective_word_count = 50 WHERE id = %s",
            (initial_analysis_ids[2],),
        )
        connection.execute(
            "UPDATE public.entries SET entry_date = '2026-07-21' WHERE id = %s",
            (initial_entry_ids[0],),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.is_reflection_recalculation_eligible(%s, %s)",
                (USER_TWO, check_at),
            ).fetchone() == (False,)


def test_owner_recalculation_request_is_concurrent_idempotent_and_current_aware() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    with psycopg.connect(value) as connection:
        latest_source = insert_accepted_basis(
            connection,
            USER_ONE,
            ("2026-07-20", "2026-07-21", "2026-07-22"),
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) "
            "VALUES (%s, %s, 3, 3, "
            "ARRAY['2026-07-20'::date, '2026-07-21'::date, "
            "'2026-07-22'::date])",
            (USER_ONE, latest_source),
        )
        connection.commit()

        with connection.transaction():
            owner(connection, USER_TWO)
            ineligible = connection.execute(
                "SELECT * FROM public.request_reflection_recalculation_for_owner("
                "%s, %s)",
                (USER_TWO, "2026-07-23 12:00:00+00"),
            ).fetchone()
            assert ineligible == ("not_eligible", None, 0, 0, 0, 0)

        with connection.transaction():
            owner(connection, USER_TWO)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(
                    "SELECT * FROM "
                    "public.request_reflection_recalculation_for_owner(%s, %s)",
                    (USER_ONE, "2026-07-23 12:00:00+00"),
                )

    def request_once() -> tuple:
        with psycopg.connect(value) as connection:
            with connection.transaction():
                owner(connection, USER_ONE)
                return connection.execute(
                    "SELECT * FROM "
                    "public.request_reflection_recalculation_for_owner(%s, %s)",
                    (USER_ONE, "2026-07-23 12:00:00+00"),
                ).fetchone()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(lambda _index: request_once(), range(2))

    assert first == second
    assert first[0] == "accepted"
    assert first[1] is not None
    assert first[2:] == (latest_source, 3, 3, 300)

    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT count(*), min(execution_mode), min(priority) "
            "FROM public.processing_jobs "
            "WHERE user_id = %s AND job_type = 'reflection_synthesis'",
            (USER_ONE,),
        ).fetchone() == (1, "publish", 80)
        running_claim = uuid4()
        connection.execute(
            "UPDATE public.processing_jobs "
            "SET status = 'running', attempts = 1, worker_id = 'test-worker', "
            "claim_token = %s, heartbeat_at = pg_catalog.now() "
            "WHERE id = %s",
            (running_claim, first[1]),
        )
        connection.commit()
        with connection.transaction():
            owner(connection, USER_ONE)
            running = connection.execute(
                "SELECT * FROM public.request_reflection_recalculation_for_owner("
                "%s, %s)",
                (USER_ONE, "2026-07-23 12:00:00+00"),
            ).fetchone()
        assert running == first
        admin(connection)
        connection.execute(
            "UPDATE public.processing_jobs "
            "SET status = 'failed', worker_id = NULL, heartbeat_at = NULL, "
            "last_error_code = 'PROVIDER_UNAVAILABLE', "
            "completed_at = pg_catalog.now() WHERE id = %s",
            (first[1],),
        )
        connection.execute(
            "UPDATE public.reflection_user_state "
            "SET last_processing_error_code = 'PROVIDER_UNAVAILABLE' "
            "WHERE user_id = %s",
            (USER_ONE,),
        )
        connection.commit()
        with connection.transaction():
            owner(connection, USER_ONE)
            retried = connection.execute(
                "SELECT * FROM public.request_reflection_recalculation_for_owner("
                "%s, %s)",
                (USER_ONE, "2026-07-23 12:00:00+00"),
            ).fetchone()
        assert retried == first
        admin(connection)
        assert connection.execute(
            "SELECT status, execution_mode, priority, attempts, worker_id, "
            "claim_token, heartbeat_at, last_error_code, completed_at "
            "FROM public.processing_jobs WHERE id = %s",
            (first[1],),
        ).fetchone() == (
            "pending",
            "publish",
            80,
            0,
            None,
            None,
            None,
            None,
            None,
        )
        assert connection.execute(
            "SELECT last_processing_error_code "
            "FROM public.reflection_user_state WHERE user_id = %s",
            (USER_ONE,),
        ).fetchone() == (None,)
        shadow_claim = uuid4()
        connection.execute(
            "UPDATE public.processing_jobs "
            "SET status = 'completed', execution_mode = 'shadow', priority = 60, "
            "attempts = 1, claim_token = %s, completed_at = pg_catalog.now() "
            "WHERE id = %s",
            (shadow_claim, first[1]),
        )
        connection.commit()
        with connection.transaction():
            owner(connection, USER_ONE)
            promoted_shadow = connection.execute(
                "SELECT * FROM public.request_reflection_recalculation_for_owner("
                "%s, %s)",
                (USER_ONE, "2026-07-23 12:00:00+00"),
            ).fetchone()
        assert promoted_shadow == first
        admin(connection)
        assert connection.execute(
            "SELECT status, execution_mode, priority, attempts, claim_token, "
            "completed_at FROM public.processing_jobs WHERE id = %s",
            (first[1],),
        ).fetchone() == ("pending", "publish", 80, 0, None, None)
        connection.execute(
            "DELETE FROM public.processing_jobs "
            "WHERE user_id = %s AND job_type = 'reflection_synthesis'",
            (USER_ONE,),
        )
        snapshot_id = uuid4()
        connection.execute(
            "INSERT INTO public.reflection_snapshots "
            "(id, user_id, version, source_version, basis_start, basis_end, "
            "valid_entry_count, excluded_entry_count, distinct_entry_dates, "
            "reflective_word_count, status) "
            "VALUES (%s, %s, 1, %s, '2026-04-24', '2026-07-22', "
            "3, 0, 3, 300, 'available')",
            (snapshot_id, USER_ONE, latest_source),
        )
        connection.execute(
            "UPDATE public.reflection_user_state "
            "SET last_snapshot_source_version = %s, "
            "last_successful_snapshot_id = %s "
            "WHERE user_id = %s",
            (latest_source, snapshot_id, USER_ONE),
        )
        connection.commit()
        with connection.transaction():
            owner(connection, USER_ONE)
            current = connection.execute(
                "SELECT * FROM public.request_reflection_recalculation_for_owner("
                "%s, %s)",
                (USER_ONE, "2026-07-23 12:00:00+00"),
            ).fetchone()
        assert current == (
            "already_current",
            None,
            latest_source,
            3,
            3,
            300,
        )
        admin(connection)
        connection.execute(
            "UPDATE public.reflection_snapshots SET status = 'stale' "
            "WHERE id = %s AND user_id = %s",
            (snapshot_id, USER_ONE),
        )
        feedback_source = connection.execute(
            "UPDATE public.reflection_user_state "
            "SET latest_accepted_source_version = pg_catalog.nextval("
            "'public.entry_analyses_source_version_seq'::pg_catalog.regclass) "
            "WHERE user_id = %s RETURNING latest_accepted_source_version",
            (USER_ONE,),
        ).fetchone()[0]
        connection.commit()
        with connection.transaction():
            owner(connection, USER_ONE)
            feedback_refresh = connection.execute(
                "SELECT * FROM public.request_reflection_recalculation_for_owner("
                "%s, %s)",
                (USER_ONE, "2026-07-23 12:00:00+00"),
            ).fetchone()
        assert feedback_refresh[0] == "accepted"
        assert feedback_refresh[1] is not None
        assert feedback_refresh[2:] == (feedback_source, 3, 3, 300)


def test_owner_recalculation_uses_global_basis_after_a_current_snapshot() -> None:
    value = database_url()
    bootstrap(value, USER_ONE)
    with psycopg.connect(value) as connection:
        snapshot_source = insert_accepted_basis(
            connection,
            USER_ONE,
            ("2026-07-20", "2026-07-21", "2026-07-22"),
        )
        snapshot_id = uuid4()
        connection.execute(
            "INSERT INTO public.reflection_snapshots "
            "(id, user_id, version, source_version, basis_start, basis_end, "
            "valid_entry_count, excluded_entry_count, distinct_entry_dates, "
            "reflective_word_count, status) "
            "VALUES (%s, %s, 1, %s, '2026-04-24', '2026-07-22', "
            "3, 0, 3, 300, 'available')",
            (snapshot_id, USER_ONE, snapshot_source),
        )
        entry_id = insert_entry(connection, USER_ONE, entry_date="2026-07-23")
        analysis_id, _, latest_source = insert_analysis_signal(
            connection,
            USER_ONE,
            entry_id,
        )
        connection.execute(
            "UPDATE public.entry_analyses SET reflective_word_count = 100 "
            "WHERE id = %s",
            (analysis_id,),
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, "
            "last_snapshot_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates, "
            "last_successful_snapshot_id) "
            "VALUES (%s, %s, %s, 1, 1, ARRAY['2026-07-23'::date], %s)",
            (USER_ONE, latest_source, snapshot_source, snapshot_id),
        )
        connection.commit()

        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.is_reflection_recalculation_eligible(%s, %s)",
                (USER_ONE, "2026-07-23 12:00:00+00"),
            ).fetchone() == (False,)
        with connection.transaction():
            owner(connection, USER_ONE)
            request = connection.execute(
                "SELECT * FROM public.request_reflection_recalculation_for_owner("
                "%s, %s)",
                (USER_ONE, "2026-07-23 12:00:00+00"),
            ).fetchone()

        assert request[0] == "accepted"
        assert request[1] is not None
        assert request[2:] == (latest_source, 4, 4, 400)


def test_owner_recalculation_basis_excludes_zero_weight_evidence() -> None:
    value = database_url()
    bootstrap(value, USER_ONE)
    with psycopg.connect(value) as connection:
        latest_source = insert_accepted_basis(
            connection,
            USER_ONE,
            ("2026-07-20", "2026-07-21", "2026-07-22"),
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) "
            "VALUES (%s, %s, 3, 3, "
            "ARRAY['2026-07-20'::date, '2026-07-21'::date, "
            "'2026-07-22'::date])",
            (USER_ONE, latest_source),
        )
        connection.execute(
            "UPDATE public.review_items AS review "
            "SET review_status = 'rejected', "
            "user_feedback = pg_catalog.jsonb_build_object("
            "'verdict', 'not_accurate', "
            "'updated_at', '2026-07-23T12:00:00Z'), "
            "evidence_weight = 0 "
            "FROM public.entries AS entry "
            "WHERE entry.id = review.entry_id "
            "AND review.user_id = %s "
            "AND entry.entry_date = '2026-07-22'",
            (USER_ONE,),
        )
        connection.commit()

        with connection.transaction():
            owner(connection, USER_ONE)
            basis = connection.execute(
                "SELECT public.get_reflection_recalculation_basis_for_owner("
                "%s, %s)",
                (USER_ONE, "2026-07-23 12:00:00+00"),
            ).fetchone()[0]
            request = connection.execute(
                "SELECT * FROM public.request_reflection_recalculation_for_owner("
                "%s, %s)",
                (USER_ONE, "2026-07-23 12:00:00+00"),
            ).fetchone()

        assert basis == {
            "basis_end": "2026-07-21",
            "basis_start": "2026-04-23",
            "valid_entry_count": 2,
            "excluded_entry_count": 0,
            "distinct_entry_dates": 2,
            "reflective_word_count": 200,
            "excluded_reasons": {},
        }
        assert request == (
            "not_eligible",
            None,
            latest_source,
            2,
            2,
            200,
        )


def test_review_items_constraints_rls_privileges_cascades_and_indexes() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    with psycopg.connect(value) as connection:
        entry_one = insert_entry(connection, USER_ONE)
        _, signal_one, _ = insert_analysis_signal(
            connection, USER_ONE, entry_one, materialize_review=False
        )
        entry_two = insert_entry(connection, USER_TWO)
        _, signal_two, _ = insert_analysis_signal(
            connection, USER_TWO, entry_two, materialize_review=False
        )
        item_one = insert_review_item(
            connection,
            user_id=USER_ONE,
            entry_id=entry_one,
            entry_signal_id=signal_one,
        )
        candidate_one = insert_pattern_candidate(connection, USER_ONE)
        pattern_item = insert_review_item(
            connection,
            user_id=USER_ONE,
            pattern_candidate_id=candidate_one,
            scope="pattern",
            item_type="hidden_driver",
            category="hidden_driver",
            inference_level="synthesized",
            source_entry_ids=[entry_one],
            source_quote=None,
        )
        connection.commit()

        privilege_rows = connection.execute(
            "SELECT role_name, "
            "pg_catalog.has_table_privilege(role_name, 'public.review_items', 'SELECT'), "
            "pg_catalog.has_table_privilege(role_name, 'public.review_items', 'INSERT'), "
            "pg_catalog.has_table_privilege(role_name, 'public.review_items', 'UPDATE'), "
            "pg_catalog.has_table_privilege(role_name, 'public.review_items', 'DELETE') "
            "FROM pg_catalog.unnest("
            "ARRAY['anon', 'authenticated', 'orion_app', 'orion_worker']) AS role_name "
            "ORDER BY role_name"
        ).fetchall()
        assert privilege_rows == [
            ("anon", False, False, False, False),
            ("authenticated", True, False, False, False),
            ("orion_app", False, False, False, False),
            ("orion_worker", False, False, False, False),
        ]
        materializer_privileges = connection.execute(
            "SELECT role_name, pg_catalog.has_function_privilege("
            "role_name, 'public.materialize_entry_review_items(uuid,uuid,jsonb)', "
            "'EXECUTE') FROM pg_catalog.unnest("
            "ARRAY['anon', 'authenticated', 'orion_app', 'orion_worker']) "
            "AS role_name ORDER BY role_name"
        ).fetchall()
        assert materializer_privileges == [
            ("anon", False),
            ("authenticated", False),
            ("orion_app", False),
            ("orion_worker", True),
        ]
        feedback_privileges = connection.execute(
            "SELECT role_name, pg_catalog.has_function_privilege("
            "role_name, 'public.put_review_feedback_for_owner("
            "uuid,uuid,text,jsonb,text,text[],jsonb,text,text[])', 'EXECUTE') "
            "FROM pg_catalog.unnest("
            "ARRAY['anon', 'authenticated', 'orion_app', 'orion_worker']) "
            "AS role_name ORDER BY role_name"
        ).fetchall()
        assert feedback_privileges == [
            ("anon", False),
            ("authenticated", True),
            ("orion_app", False),
            ("orion_worker", False),
        ]

        with pytest.raises(psycopg.errors.UniqueViolation):
            with connection.transaction():
                insert_review_item(
                    connection,
                    user_id=USER_ONE,
                    entry_id=entry_one,
                    entry_signal_id=signal_one,
                )

        invalid_cases = (
            {"item_type": "hidden_driver", "category": "hidden_driver"},
            {"category": "energy"},
            {"inference_level": "synthesized"},
            {
                "review_status": "confirmed",
                "user_feedback": {
                    "verdict": "accurate",
                    "updated_at": "2026-07-20T12:00:00Z",
                },
                "evidence_weight": 0.5,
            },
            {"source_entry_ids": []},
            {"statement_envelope": {}},
        )
        for overrides in invalid_cases:
            invalid_entry = insert_entry(connection, USER_ONE)
            _, invalid_signal, _ = insert_analysis_signal(
                connection, USER_ONE, invalid_entry, materialize_review=False
            )
            with pytest.raises(psycopg.errors.CheckViolation):
                with connection.transaction():
                    insert_review_item(
                        connection,
                        user_id=USER_ONE,
                        entry_id=invalid_entry,
                        entry_signal_id=invalid_signal,
                        **overrides,
                    )
        connection.rollback()

        cross_owner_entry = insert_entry(connection, USER_ONE)
        _, cross_owner_signal, _ = insert_analysis_signal(
            connection, USER_ONE, cross_owner_entry, materialize_review=False
        )
        connection.commit()
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with connection.transaction():
                insert_review_item(
                    connection,
                    user_id=USER_TWO,
                    entry_id=cross_owner_entry,
                    entry_signal_id=cross_owner_signal,
                    source_entry_ids=[cross_owner_entry],
                )

        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                insert_review_item(
                    connection,
                    user_id=USER_ONE,
                    pattern_candidate_id=candidate_one,
                    scope="pattern",
                    item_type="hidden_driver",
                    category="hidden_driver",
                    inference_level="synthesized",
                    source_entry_ids=[entry_one],
                    source_quote="Patterns cannot store a direct source quote.",
                )

        with connection.transaction():
            owner(connection, USER_ONE)
            assert connection.execute(
                "SELECT id FROM public.review_items ORDER BY id"
            ).fetchall() == sorted([(item_one,), (pattern_item,)])
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                insert_review_item(
                    connection,
                    user_id=USER_ONE,
                    entry_id=entry_one,
                    entry_signal_id=signal_one,
                )

        with connection.transaction():
            owner(connection, USER_TWO)
            assert connection.execute(
                "SELECT id FROM public.review_items"
            ).fetchall() == []

        with connection.transaction():
            worker(connection)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                insert_review_item(
                    connection,
                    user_id=USER_TWO,
                    entry_id=entry_two,
                    entry_signal_id=signal_two,
                )

        with connection.transaction():
            worker(connection)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute("SELECT id FROM public.review_items")

        admin(connection)
        index_names = {
            row[0]
            for row in connection.execute(
                "SELECT indexname FROM pg_catalog.pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'review_items'"
            ).fetchall()
        }
        assert {
            "review_items_owner_list_idx",
            "review_items_owner_status_updated_idx",
            "review_items_entry_signal_unique_idx",
            "review_items_pattern_candidate_unique_idx",
        } <= index_names
        connection.execute("SET LOCAL enable_seqscan = off")
        plan = "\n".join(
            row[0]
            for row in connection.execute(
                "EXPLAIN SELECT id FROM public.review_items "
                "WHERE user_id = %s AND scope = 'entry_insight' "
                "AND category = 'self_knowledge' AND review_status = 'pending' "
                "ORDER BY created_at DESC, id DESC LIMIT 20",
                (USER_ONE,),
            ).fetchall()
        )
        assert "review_items_owner_list_idx" in plan
        encrypted_at_rest = connection.execute(
            "SELECT statement_envelope::text, source_quote_envelope::text "
            "FROM public.review_items WHERE id = %s",
            (item_one,),
        ).fetchone()
        assert "You value focused work." not in encrypted_at_rest[0]
        assert "I value focused work." not in encrypted_at_rest[1]

        connection.execute("DELETE FROM public.entries WHERE id = %s", (entry_one,))
        assert connection.execute(
            "SELECT count(*) FROM public.review_items WHERE id = %s", (item_one,)
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM public.review_items WHERE id = %s", (pattern_item,)
        ).fetchone() == (1,)
        connection.execute("DELETE FROM public.pattern_candidates WHERE id = %s", (candidate_one,))
        assert connection.execute(
            "SELECT count(*) FROM public.review_items WHERE id = %s", (pattern_item,)
        ).fetchone() == (0,)
        connection.execute("DELETE FROM auth.users WHERE id = %s", (USER_TWO,))
        assert connection.execute(
            "SELECT count(*) FROM public.review_items WHERE user_id = %s", (USER_TWO,)
        ).fetchone() == (0,)


def test_review_repository_owner_filters_stable_pagination_and_corrupt_ciphertext() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    ordered_ids: list[UUID] = []
    with psycopg.connect(value) as connection:
        for index in range(4):
            entry_id = insert_entry(connection, USER_ONE)
            _, signal_id, _ = insert_analysis_signal(
                connection, USER_ONE, entry_id, materialize_review=False
            )
            item_id = insert_review_item(
                connection,
                user_id=USER_ONE,
                entry_id=entry_id,
                entry_signal_id=signal_id,
                statement=f"Review statement {index}",
                created_at=f"2026-07-2{index + 1}T12:00:00Z",
            )
            ordered_ids.insert(0, item_id)
        feedback_entry = insert_entry(connection, USER_ONE)
        _, feedback_signal, _ = insert_analysis_signal(
            connection, USER_ONE, feedback_entry, materialize_review=False
        )
        feedback_item = insert_review_item(
            connection,
            user_id=USER_ONE,
            entry_id=feedback_entry,
            entry_signal_id=feedback_signal,
            review_status="partially_confirmed",
            user_feedback={
                "verdict": "partly_accurate",
                "updated_at": "2026-07-24T12:00:00Z",
            },
            evidence_weight=0.5,
            corrected_statement="I value calm, focused work.",
            feedback_note="This is more precise.",
            created_at="2026-07-24T12:00:00Z",
        )
        candidate_id = insert_pattern_candidate(connection, USER_ONE)
        pattern_item = insert_review_item(
            connection,
            user_id=USER_ONE,
            pattern_candidate_id=candidate_id,
            scope="pattern",
            item_type="hidden_driver",
            category="hidden_driver",
            inference_level="synthesized",
            source_entry_ids=[feedback_entry],
            source_quote=None,
            statement="Perfectionism may be delaying completion.",
            created_at="2026-07-24T13:00:00Z",
        )
        other_entry = insert_entry(connection, USER_TWO)
        _, other_signal, _ = insert_analysis_signal(
            connection, USER_TWO, other_entry, materialize_review=False
        )
        other_item = insert_review_item(
            connection,
            user_id=USER_TWO,
            entry_id=other_entry,
            entry_signal_id=other_signal,
        )
        corrupt_entry = insert_entry(connection, USER_ONE)
        _, corrupt_signal, _ = insert_analysis_signal(
            connection, USER_ONE, corrupt_entry, materialize_review=False
        )
        corrupt_item = insert_review_item(
            connection,
            user_id=USER_ONE,
            entry_id=corrupt_entry,
            entry_signal_id=corrupt_signal,
            statement_envelope=ENVELOPE_V1,
            created_at="2026-07-01T12:00:00Z",
        )
        connection.commit()

    engine = create_engine(value.replace("postgresql://", "postgresql+psycopg://", 1))
    repository = ReviewRepository(cipher=TEST_CIPHER)
    try:
        with Session(engine) as session, session.begin():
            session.execute(text("SET LOCAL ROLE authenticated"))
            session.execute(
                text(
                    "SELECT pg_catalog.set_config("
                    "'request.jwt.claims', :claims, true)"
                ),
                {
                    "claims": json.dumps(
                        {"sub": str(USER_ONE), "role": "authenticated"}
                    )
                },
            )
            assert repository.count_items(
                session,
                user_id=USER_ONE,
                scope="entry_insight",
                category="all",
                status="pending",
            ) == 5
            first_page = repository.list_items(
                session,
                user_id=USER_ONE,
                scope="entry_insight",
                category="self_knowledge",
                status="pending",
                page=1,
                page_size=2,
            )
            second_page = repository.list_items(
                session,
                user_id=USER_ONE,
                scope="entry_insight",
                category="self_knowledge",
                status="pending",
                page=2,
                page_size=2,
            )
            assert [item.id for item in first_page] == ordered_ids[:2]
            assert [item.id for item in second_page] == ordered_ids[2:4]
            assert [item.statement for item in first_page] == [
                "Review statement 3",
                "Review statement 2",
            ]
            assert repository.get_by_owner(
                session,
                user_id=USER_ONE,
                item_id=other_item,
            ) is None
            saved_feedback = repository.get_by_owner(
                session,
                user_id=USER_ONE,
                item_id=feedback_item,
            )
            assert saved_feedback is not None
            assert saved_feedback.feedback is not None
            assert saved_feedback.feedback.corrected_statement == (
                "I value calm, focused work."
            )
            assert saved_feedback.feedback.note == "This is more precise."
            saved_pattern = repository.get_by_owner(
                session,
                user_id=USER_ONE,
                item_id=pattern_item,
            )
            assert saved_pattern is not None
            assert saved_pattern.scope == "pattern"
            assert saved_pattern.source_quote is None
            assert saved_pattern.statement == (
                "Perfectionism may be delaying completion."
            )
            with pytest.raises(
                ReviewRepositoryDataError,
                match="review item data is unavailable",
            ):
                repository.get_by_owner(
                    session,
                    user_id=USER_ONE,
                    item_id=corrupt_item,
                )
            with pytest.raises(ValueError, match="category is not valid"):
                repository.count_items(
                    session,
                    user_id=USER_ONE,
                    scope="entry_insight",
                    category="hidden_driver",
                    status="pending",
                )
            with pytest.raises(ValueError, match="invalid review pagination"):
                repository.list_items(
                    session,
                    user_id=USER_ONE,
                    scope="entry_insight",
                    category="all",
                    status="pending",
                    page=0,
                    page_size=20,
                )
    finally:
        engine.dispose()


def test_review_feedback_command_is_encrypted_owner_safe_replaceable_and_idempotent() -> None:
    value = database_url()
    bootstrap(value, USER_ONE, USER_TWO)
    snapshot_id = uuid4()
    with psycopg.connect(value) as connection:
        entry_id = insert_entry(connection, USER_ONE)
        _, signal_id, source_version = insert_analysis_signal(
            connection, USER_ONE, entry_id, materialize_review=False
        )
        item_id = insert_review_item(
            connection,
            user_id=USER_ONE,
            entry_id=entry_id,
            entry_signal_id=signal_id,
        )
        connection.execute(
            "INSERT INTO public.reflection_snapshots "
            "(id, user_id, version, source_version, basis_start, basis_end, "
            "valid_entry_count, excluded_entry_count, distinct_entry_dates, "
            "reflective_word_count, status) "
            "VALUES (%s, %s, 1, %s, '2026-07-20', '2026-07-20', "
            "1, 0, 1, 150, 'available')",
            (snapshot_id, USER_ONE, source_version),
        )
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, "
            "last_snapshot_source_version, last_successful_snapshot_id) "
            "VALUES (%s, %s, %s, %s)",
            (USER_ONE, source_version, source_version, snapshot_id),
        )
        candidate_id = insert_pattern_candidate(connection, USER_ONE)
        pattern_item_id = insert_review_item(
            connection,
            user_id=USER_ONE,
            pattern_candidate_id=candidate_id,
            scope="pattern",
            item_type="hidden_driver",
            category="hidden_driver",
            inference_level="synthesized",
            source_entry_ids=[entry_id],
            source_quote=None,
        )
        connection.commit()

    engine = create_engine(value.replace("postgresql://", "postgresql+psycopg://", 1))
    repository = ReviewRepository(cipher=TEST_CIPHER)
    rotated_repository = ReviewRepository(
        cipher=AesGcmContentCipher(
            encryption_keys={"test-key": b"e" * 32},
            active_encryption_key_id="test-key",
            fingerprint_keys={
                "test-fingerprint": b"f" * 32,
                "rotated-fingerprint": b"r" * 32,
            },
            active_fingerprint_key_id="rotated-fingerprint",
        )
    )

    def save(
        target: UUID,
        verdict: str,
        *,
        corrected: str | None = None,
        note: str | None = None,
        user_id: UUID = USER_ONE,
        target_repository: ReviewRepository = repository,
    ):
        with Session(engine) as session, session.begin():
            session.execute(text("SET LOCAL ROLE authenticated"))
            session.execute(
                text(
                    "SELECT pg_catalog.set_config("
                    "'request.jwt.claims', :claims, true)"
                ),
                {
                    "claims": json.dumps(
                        {"sub": str(user_id), "role": "authenticated"}
                    )
                },
            )
            return target_repository.put_feedback(
                session,
                user_id=user_id,
                item_id=target,
                verdict=verdict,  # type: ignore[arg-type]
                corrected_statement=corrected,
                note=note,
            )

    private_correction = "I value focused work when the deadline is realistic."
    private_note = "This wording is more precise."
    try:
        first = save(
            item_id,
            "accurate",
            corrected=private_correction,
            note=private_note,
        )
        replay = save(
            item_id,
            "accurate",
            corrected=private_correction,
            note=private_note,
            target_repository=rotated_repository,
        )
        replacement = save(
            item_id,
            "partly_accurate",
            corrected=private_correction,
            note=private_note,
            target_repository=rotated_repository,
        )
        assert first.changed is True
        assert replay.changed is False
        assert replay.source_version == first.source_version
        assert replacement.changed is True
        assert replacement.source_version > first.source_version

        with Session(engine) as session, session.begin():
            session.execute(text("SET LOCAL ROLE authenticated"))
            session.execute(
                text(
                    "SELECT pg_catalog.set_config("
                    "'request.jwt.claims', :claims, true)"
                ),
                {
                    "claims": json.dumps(
                        {"sub": str(USER_ONE), "role": "authenticated"}
                    )
                },
            )
            saved_item = repository.get_by_owner(
                session,
                user_id=USER_ONE,
                item_id=item_id,
            )
        assert saved_item is not None
        assert saved_item.status == "partially_confirmed"
        assert saved_item.feedback is not None
        assert saved_item.feedback.evidence_weight == 0.5
        assert saved_item.feedback.corrected_statement == private_correction
        assert saved_item.feedback.note == private_note

        with psycopg.connect(value) as connection:
            stored = connection.execute(
                "SELECT review_status, evidence_weight, "
                "corrected_statement_envelope::text, "
                "feedback_note_envelope::text, metadata::text "
                "FROM public.review_items WHERE id = %s",
                (item_id,),
            ).fetchone()
            assert stored[:2] == ("partially_confirmed", 0.5)
            assert private_correction not in stored[2]
            assert private_note not in stored[3]
            assert private_correction not in stored[4]
            assert private_note not in stored[4]
            assert connection.execute(
                "SELECT latest_accepted_source_version "
                "FROM public.reflection_user_state WHERE user_id = %s",
                (USER_ONE,),
            ).fetchone() == (replacement.source_version,)
            assert connection.execute(
                "SELECT status FROM public.reflection_snapshots WHERE id = %s",
                (snapshot_id,),
            ).fetchone() == ("stale",)

        with pytest.raises(ReviewItemNotFoundError):
            save(item_id, "accurate", user_id=USER_TWO)

        pattern_version = 1
        for verdict, expected_review, expected_weight, expected_pattern in (
            ("resonates", "confirmed", 1.0, "published"),
            ("partly_true", "partially_confirmed", 0.5, "weakened"),
            ("not_true", "rejected", 0.0, "rejected"),
        ):
            saved = save(pattern_item_id, verdict)
            assert saved.changed is True
            pattern_version += 1
            with psycopg.connect(value) as connection:
                assert connection.execute(
                    "SELECT review_status, evidence_weight "
                    "FROM public.review_items WHERE id = %s",
                    (pattern_item_id,),
                ).fetchone() == (expected_review, expected_weight)
                assert connection.execute(
                    "SELECT status, version FROM public.pattern_candidates "
                    "WHERE id = %s",
                    (candidate_id,),
                ).fetchone() == (expected_pattern, pattern_version)

        with psycopg.connect(value) as connection:
            connection.execute(
                "UPDATE public.review_items SET reflection_eligible = false "
                "WHERE id = %s",
                (item_id,),
            )
            connection.commit()
        with pytest.raises(ReviewItemStaleError):
            save(item_id, "not_accurate")
    finally:
        engine.dispose()


def test_weighted_snapshot_persists_metadata_and_one_pattern_review_on_replay() -> None:
    value = database_url()
    bootstrap(value, USER_ONE)
    with psycopg.connect(value) as connection:
        entry_dates = tuple(
            ("2026-07-20", "2026-07-21", "2026-07-22")[index % 3]
            for index in range(101)
        )
        source_version = insert_accepted_basis(
            connection,
            USER_ONE,
            entry_dates,
        )
        signal_rows = connection.execute(
            "SELECT signal.id, signal.entry_id, entry.entry_date "
            "FROM public.entry_signals AS signal "
            "JOIN public.entries AS entry ON entry.id = signal.entry_id "
            "AND entry.user_id = signal.user_id "
            "WHERE signal.user_id = %s ORDER BY entry.entry_date, signal.id",
            (USER_ONE,),
        ).fetchall()
        connection.execute(
            "INSERT INTO public.reflection_user_state "
            "(user_id, latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates) "
            "VALUES (%s, %s, 101, 101, "
            "ARRAY['2026-07-20'::date, '2026-07-21'::date, '2026-07-22'::date])",
            (USER_ONE, source_version),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            job_id = connection.execute(
                "SELECT public.enqueue_processing_job("
                "%s, NULL, 'reflection_synthesis', %s, pg_catalog.now())",
                (USER_ONE, str(source_version)),
            ).fetchone()[0]
            claim_token = connection.execute(
                "SELECT claim_token FROM public.claim_processing_job('weighted-worker')"
            ).fetchone()[0]

        snapshot_id = uuid4()
        candidate_id = uuid4()
        insight_id = uuid4()
        review_item_id = uuid4()
        snapshot = {
            "id": str(snapshot_id),
            "version": 1,
            "source_version": source_version,
            "basis_start": "2026-04-24",
            "basis_end": "2026-07-22",
            "valid_entry_count": 101,
            "excluded_entry_count": 0,
            "distinct_entry_dates": 3,
            "reflective_word_count": 10100,
            "status": "available",
            "model_name": "test-synthesis-model",
            "prompt_version": "reflection-synthesis-v2",
            "generated_at": "2026-07-23T12:00:00Z",
        }
        candidates = [
            candidate_payload(
                candidate_id,
                canonical_key="f" * 64,
                status="published",
            )
        ]
        candidate_evidence = [
            evidence_payload(candidate_id, row[0]) for row in signal_rows
        ]
        insights = [
            {
                "id": str(insight_id),
                "candidate_id": str(candidate_id),
                "pattern_type": "hidden_driver",
                "ordinal": 0,
                "status": "available",
                "payload_envelope": ENVELOPE_V1,
                "confidence_label": "emerging",
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
        snapshot_evidence = [
            {
                "insight_id": str(insight_id),
                "signal_id": str(row[0]),
                "entry_id": str(row[1]),
                "evidence_role": "supporting",
                "ordinal": index,
                "source_start": 0,
                "source_end": 4,
            }
            for index, row in enumerate(signal_rows)
        ]
        review_source_rows = sorted(
            signal_rows,
            key=lambda row: (row[2], str(row[1])),
        )[:100]
        pattern_reviews = [
            {
                "id": str(review_item_id),
                "pattern_candidate_id": str(candidate_id),
                "item_type": "hidden_driver",
                "category": "hidden_driver",
                "statement_envelope": ENVELOPE_V1,
                "source_entry_ids": [str(row[1]) for row in review_source_rows],
                "source_dates": sorted(
                    {row[2].isoformat() for row in review_source_rows}
                ),
                "inference_level": "synthesized",
                "model_confidence": 0.8,
                "metadata": {
                    "model_id": "test-synthesis-model",
                    "prompt_version": "reflection-synthesis-v2",
                    "source": "reflection_synthesis",
                    "source_version": source_version,
                    "candidate_version": 1,
                },
            }
        ]
        arguments = (
            job_id,
            claim_token,
            json.dumps(snapshot),
            json.dumps(candidates),
            json.dumps(candidate_evidence),
            json.dumps(insights),
            json.dumps(snapshot_evidence),
            json.dumps(pattern_reviews),
        )
        with connection.transaction():
            worker(connection)
            first = connection.execute(
                "SELECT public.apply_weighted_reflection_snapshot("
                "%s, 'weighted-worker', %s, %s::jsonb, %s::jsonb, %s::jsonb, "
                "%s::jsonb, %s::jsonb, %s::jsonb)",
                arguments,
            ).fetchone()[0]
            replay = connection.execute(
                "SELECT public.apply_weighted_reflection_snapshot("
                "%s, 'weighted-worker', %s, %s::jsonb, %s::jsonb, %s::jsonb, "
                "%s::jsonb, %s::jsonb, %s::jsonb)",
                arguments,
            ).fetchone()[0]

        assert first == replay == snapshot_id
        admin(connection)
        connection.execute(
            "UPDATE public.reflection_user_state "
            "SET latest_accepted_source_version = latest_accepted_source_version + 1 "
            "WHERE user_id = %s",
            (USER_ONE,),
        )
        connection.commit()
        changed_snapshot = {
            **snapshot,
            "generated_at": "2026-07-24T12:00:00Z",
        }
        changed_arguments = (
            job_id,
            claim_token,
            json.dumps(changed_snapshot),
            json.dumps(candidates),
            json.dumps(candidate_evidence),
            json.dumps(insights),
            json.dumps(snapshot_evidence),
            json.dumps(pattern_reviews),
        )
        with connection.transaction():
            worker(connection)
            advanced_basis = connection.execute(
                "SELECT public.get_reflection_candidate_basis(%s, %s, 90)",
                (USER_ONE, source_version + 1),
            ).fetchone()[0]
        assert advanced_basis["candidates"][0]["review_item_id"] == str(
            review_item_id
        )
        with connection.transaction():
            worker(connection)
            delayed_replay = connection.execute(
                "SELECT public.apply_weighted_reflection_snapshot("
                "%s, 'weighted-worker', %s, %s::jsonb, %s::jsonb, %s::jsonb, "
                "%s::jsonb, %s::jsonb, %s::jsonb)",
                changed_arguments,
            ).fetchone()[0]

        assert delayed_replay == snapshot_id
        admin(connection)
        assert connection.execute(
            "SELECT model_name, prompt_version, generated_at "
            "FROM public.reflection_snapshots WHERE id = %s",
            (snapshot_id,),
        ).fetchone() == (
            "test-synthesis-model",
            "reflection-synthesis-v2",
            datetime(2026, 7, 23, 12, tzinfo=timezone.utc),
        )
        assert connection.execute(
            "SELECT id, review_status, evidence_weight, source_entry_ids, "
            "source_dates FROM public.review_items "
            "WHERE pattern_candidate_id = %s",
            (candidate_id,),
        ).fetchone() == (
            review_item_id,
            "pending",
            1.0,
            [row[1] for row in review_source_rows],
            sorted({row[2] for row in review_source_rows}),
        )

        feedback = {
            "verdict": "resonates",
            "updated_at": "2026-07-23T13:00:00Z",
        }
        connection.execute(
            "UPDATE public.review_items "
            "SET review_status = 'confirmed', user_feedback = %s::jsonb, "
            "evidence_weight = 1.0 WHERE id = %s",
            (json.dumps(feedback), review_item_id),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            next_job_id = connection.execute(
                "SELECT public.enqueue_processing_job("
                "%s, NULL, 'reflection_synthesis', %s, pg_catalog.now())",
                (USER_ONE, str(source_version + 1)),
            ).fetchone()[0]
            next_claim_token = connection.execute(
                "SELECT claim_token "
                "FROM public.claim_processing_job('weighted-worker')"
            ).fetchone()[0]

        refreshed_envelope = {
            **ENVELOPE_V1,
            "ciphertext": "Yg==",
        }
        next_snapshot_id = uuid4()
        next_insight_id = uuid4()
        next_snapshot = {
            **snapshot,
            "id": str(next_snapshot_id),
            "version": 2,
            "source_version": source_version + 1,
            "generated_at": "2026-07-24T12:00:00Z",
        }
        next_candidates = [
            candidate_payload(
                candidate_id,
                canonical_key="f" * 64,
                status="published",
                version=2,
            )
        ]
        next_insights = [
            {
                **insights[0],
                "id": str(next_insight_id),
            },
            {
                **insights[1],
                "id": str(uuid4()),
            },
            {
                **insights[2],
                "id": str(uuid4()),
            },
        ]
        next_snapshot_evidence = [
            {
                **item,
                "insight_id": str(next_insight_id),
            }
            for item in snapshot_evidence
        ]
        next_pattern_reviews = [
            {
                **pattern_reviews[0],
                "statement_envelope": refreshed_envelope,
                "metadata": {
                    **pattern_reviews[0]["metadata"],
                    "source_version": source_version + 1,
                    "candidate_version": 2,
                },
            }
        ]
        next_arguments = (
            next_job_id,
            next_claim_token,
            json.dumps(next_snapshot),
            json.dumps(next_candidates),
            json.dumps(candidate_evidence),
            json.dumps(next_insights),
            json.dumps(next_snapshot_evidence),
            json.dumps(next_pattern_reviews),
        )
        with connection.transaction():
            worker(connection)
            assert connection.execute(
                "SELECT public.apply_weighted_reflection_snapshot("
                "%s, 'weighted-worker', %s, %s::jsonb, %s::jsonb, %s::jsonb, "
                "%s::jsonb, %s::jsonb, %s::jsonb)",
                next_arguments,
            ).fetchone()[0] == next_snapshot_id

        admin(connection)
        assert connection.execute(
            "SELECT statement_envelope, review_status, user_feedback, "
            "evidence_weight FROM public.review_items WHERE id = %s",
            (review_item_id,),
        ).fetchone() == (
            ENVELOPE_V1,
            "confirmed",
            feedback,
            1.0,
        )

        unsafe_pattern_reviews = [
            {
                **next_pattern_reviews[0],
                "metadata": {
                    **next_pattern_reviews[0]["metadata"],
                    "raw_journal": "private journal content",
                },
            }
        ]
        unsafe_arguments = (
            next_job_id,
            next_claim_token,
            json.dumps(next_snapshot),
            json.dumps(next_candidates),
            json.dumps(candidate_evidence),
            json.dumps(next_insights),
            json.dumps(next_snapshot_evidence),
            json.dumps(unsafe_pattern_reviews),
        )
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            with connection.transaction():
                worker(connection)
                connection.execute(
                    "SELECT public.apply_weighted_reflection_snapshot("
                    "%s, 'weighted-worker', %s, %s::jsonb, %s::jsonb, %s::jsonb, "
                    "%s::jsonb, %s::jsonb, %s::jsonb)",
                    unsafe_arguments,
                )


def test_candidate_basis_applies_full_partial_and_rejected_review_weights() -> None:
    value = database_url()
    bootstrap(value, USER_ONE)
    with psycopg.connect(value) as connection:
        source_version = insert_accepted_basis(
            connection,
            USER_ONE,
            ("2026-07-20", "2026-07-21", "2026-07-22"),
        )
        reviews = connection.execute(
            "SELECT review.id, entry.entry_date "
            "FROM public.review_items AS review "
            "JOIN public.entries AS entry ON entry.id = review.entry_id "
            "AND entry.user_id = review.user_id "
            "WHERE review.user_id = %s ORDER BY entry.entry_date",
            (USER_ONE,),
        ).fetchall()
        connection.execute(
            "UPDATE public.review_items SET review_status = 'partially_confirmed', "
            "user_feedback = %s::jsonb, evidence_weight = 0.5 WHERE id = %s",
            (
                json.dumps(
                    {
                        "verdict": "partly_accurate",
                        "updated_at": "2026-07-23T12:00:00Z",
                    }
                ),
                reviews[1][0],
            ),
        )
        connection.execute(
            "UPDATE public.review_items SET review_status = 'rejected', "
            "user_feedback = %s::jsonb, evidence_weight = 0.0 WHERE id = %s",
            (
                json.dumps(
                    {
                        "verdict": "not_accurate",
                        "updated_at": "2026-07-23T12:00:00Z",
                    }
                ),
                reviews[2][0],
            ),
        )
        connection.commit()
        with connection.transaction():
            worker(connection)
            basis = connection.execute(
                "SELECT public.get_reflection_candidate_basis(%s, %s, 90)",
                (USER_ONE, source_version),
            ).fetchone()[0]

        assert basis["valid_entry_count"] == 2
        assert basis["distinct_entry_dates"] == 2
        assert basis["reflective_word_count"] == 200
        assert [row["evidence_weight"] for row in basis["signals"]] == [1.0, 0.5]
        assert [row["model_confidence"] for row in basis["signals"]] == [0.9, 0.9]
        assert [row["confidence"] for row in basis["signals"]] == [0.9, 0.45]
