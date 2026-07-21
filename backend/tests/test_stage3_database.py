from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import psycopg
import pytest
from psycopg import sql

from scripts.migrate import apply_migrations, load_migrations


ROOT = Path(__file__).resolve().parents[1]
USER_ID = UUID("33333333-3333-4333-8333-333333333333")
OTHER_ID = UUID("44444444-4444-4444-8444-444444444444")
CONFIG_ID = UUID("00000000-0000-0000-0000-000000000801")
ENVELOPE = json.dumps(
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


def database_url() -> str:
    value = os.environ.get("STAGE2_DISPOSABLE_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("STAGE2_DISPOSABLE_DATABASE_URL is not configured")
    parsed = urlsplit(value)
    if parsed.path != "/orion_stage2_test" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        pytest.fail("processing DB test requires exact local disposable database")
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


def owner(connection: psycopg.Connection, user_id: UUID) -> None:
    connection.execute("SET LOCAL ROLE authenticated")
    connection.execute(
        "SELECT pg_catalog.set_config('request.jwt.claims', %s, true)",
        (json.dumps({"sub": str(user_id), "role": "authenticated"}),),
    )


def insert_processing_entry(connection: psycopg.Connection, user_id: UUID) -> tuple[UUID, UUID]:
    entry_id = UUID(bytes=os.urandom(16), version=4)
    token = UUID(bytes=os.urandom(16), version=4)
    connection.execute(
        "INSERT INTO public.entries "
        "(id, user_id, content_envelope, input_type, entry_date, processing_status, "
        "processing_token, processing_started_at) "
        "VALUES (%s, %s, %s::jsonb, 'text', CURRENT_DATE, 'processing', %s, pg_catalog.now())",
        (entry_id, user_id, ENVELOPE, token),
    )
    return entry_id, token


def apply(
    connection: psycopg.Connection,
    *,
    user_id: UUID,
    entry_id: UUID,
    token: UUID,
    theme_key: str = "career",
    idea: str = "I should call my mentor.",
    past_import: bool = False,
) -> None:
    owner(connection, user_id)
    connection.execute(
        "SELECT public.apply_entry_extraction_for_owner("
        "%s, %s, %s, %s, 'dominant', %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s)",
        (
            user_id,
            entry_id,
            token,
            CONFIG_ID,
            json.dumps(
                [
                    {
                        "key": theme_key,
                        "tier": "primary",
                        "evidence": "Work felt meaningful.",
                        "score": 1,
                    }
                ]
            ),
            json.dumps([{"content": idea}]),
            json.dumps([{"content": "Last year I moved to Pune."}]),
            json.dumps(
                [
                    {
                        "reflection_type": "filled_energy",
                        "activity": "walking",
                        "confidence_score": 0.8,
                    }
                ]
            ),
            past_import,
        ),
    )


def test_atomic_processing_current_token_concurrency_and_rollback() -> None:
    value = database_url()
    reset(value)
    with psycopg.connect(value) as connection:
        connection.execute((ROOT / "tests/sql/bootstrap_auth.sql").read_text(), prepare=False)
        connection.execute(
            "INSERT INTO auth.users (id) VALUES (%s), (%s)", (USER_ID, OTHER_ID)
        )
        connection.commit()
    apply_migrations(value, load_migrations(ROOT / "migrations"))

    with psycopg.connect(value) as connection:
        entry_id, token = insert_processing_entry(connection, USER_ID)
        connection.commit()
    with psycopg.connect(value) as connection:
        with connection.transaction():
            apply(connection, user_id=USER_ID, entry_id=entry_id, token=token)
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT processing_status, processing_token FROM public.entries WHERE id = %s",
            (entry_id,),
        ).fetchone() == ("completed", None)
        assert connection.execute(
            "SELECT mode FROM public.entry_classifications WHERE entry_id = %s", (entry_id,)
        ).fetchone() == ("dominant",)
        assert connection.execute(
            "SELECT tier, score FROM public.entry_themes WHERE user_id = %s", (USER_ID,)
        ).fetchone() == ("primary", Decimal("1.00000"))
        assert connection.execute(
            "SELECT status, decision_source FROM public.ideas WHERE entry_id = %s", (entry_id,)
        ).fetchone() == ("pending_approval", None)
        assert connection.execute(
            "SELECT count(*) FROM public.reflections WHERE entry_id = %s", (entry_id,)
        ).fetchone() == (1,)
        with pytest.raises(psycopg.errors.RaiseException):
            with connection.transaction():
                owner(connection, USER_ID)
                connection.execute(
                    "SELECT public.apply_entry_extraction_for_owner("
                    "%s, %s, %s, %s, NULL, '[]'::jsonb, '[]'::jsonb, "
                    "'[]'::jsonb, '[]'::jsonb, false)",
                    (USER_ID, entry_id, token, CONFIG_ID),
                )

    with psycopg.connect(value) as connection:
        rollback_id, rollback_token = insert_processing_entry(connection, USER_ID)
        connection.commit()
    with psycopg.connect(value) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                apply(
                    connection,
                    user_id=USER_ID,
                    entry_id=rollback_id,
                    token=rollback_token,
                    idea="x" * 4001,
                )
        assert connection.execute(
            "SELECT count(*) FROM public.entry_classifications WHERE entry_id = %s",
            (rollback_id,),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT processing_status FROM public.entries WHERE id = %s", (rollback_id,)
        ).fetchone() == ("processing",)

        provenance_id, provenance_token = insert_processing_entry(connection, USER_ID)
        connection.commit()
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            with connection.transaction():
                apply(
                    connection,
                    user_id=USER_ID,
                    entry_id=provenance_id,
                    token=provenance_token,
                    past_import=True,
                )
        assert connection.execute(
            "SELECT processing_status FROM public.entries WHERE id = %s", (provenance_id,)
        ).fetchone() == ("processing",)

    with psycopg.connect(value) as connection:
        concurrent_id, concurrent_token = insert_processing_entry(connection, USER_ID)
        connection.commit()

    def contender(_index: int) -> str:
        try:
            with psycopg.connect(value) as connection:
                with connection.transaction():
                    apply(
                        connection,
                        user_id=USER_ID,
                        entry_id=concurrent_id,
                        token=concurrent_token,
                    )
            return "committed"
        except psycopg.Error:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(contender, range(2)))
    assert outcomes == ["committed", "rejected"]
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT count(*) FROM public.entry_classifications WHERE entry_id = %s",
            (concurrent_id,),
        ).fetchone() == (1,)

        failed_id, failed_token = insert_processing_entry(connection, USER_ID)
        connection.commit()
        with connection.transaction():
            owner(connection, USER_ID)
            assert connection.execute(
                "SELECT public.mark_entry_processing_failed_for_owner(%s, %s, %s, 'PROVIDER_UNAVAILABLE')",
                (USER_ID, failed_id, failed_token),
            ).fetchone() == (True,)
        with connection.transaction():
            owner(connection, USER_ID)
            claimed = connection.execute(
                "SELECT public.claim_failed_entry_for_owner(%s, %s)", (USER_ID, failed_id)
            ).fetchone()[0]
            assert claimed != failed_token
        with connection.transaction():
            owner(connection, OTHER_ID)
            assert connection.execute(
                "SELECT public.mark_entry_processing_failed_for_owner(%s, %s, %s, 'FAILED')",
                (OTHER_ID, failed_id, claimed),
            ).fetchone() == (False,)
