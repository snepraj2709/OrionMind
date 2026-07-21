from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from psycopg import sql

from app.main import create_app
from app.modules.profile.types import AccountDeletionOutcome
from app.shared.config import Settings
from app.shared.database.session import build_database_sessions
from scripts.migrate import apply_migrations, load_migrations


ROOT = Path(__file__).resolve().parents[1]
USER_ONE = UUID("11111111-1111-4111-8111-111111111111")
USER_TWO = UUID("22222222-2222-4222-8222-222222222222")
ENVELOPE = (
    '{"version":2,"algorithm":"AES-256-GCM","key_id":"test-key",'
    '"kdf":"HKDF-SHA256","salt":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",'
    '"nonce":"AAAAAAAAAAAAAAAA","ciphertext":"YQ==",'
    '"tag":"AAAAAAAAAAAAAAAAAAAAAA=="}'
)


class UserTwoVerifier:
    def verify_access_token(self, _access_token: str) -> str:
        return str(USER_TWO)


class LocalAccountAuth:
    def verify_user(self, _proof_token: str) -> UUID:
        return USER_TWO

    def delete_user(self, _user_id: UUID) -> AccountDeletionOutcome:
        return AccountDeletionOutcome.ALREADY_MISSING


def disposable_database_url() -> str:
    value = os.environ.get("STAGE2_DISPOSABLE_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("STAGE2_DISPOSABLE_DATABASE_URL is not configured")
    parsed = urlsplit(value)
    if parsed.path != "/orion_stage2_test" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        pytest.fail("Stage 2 database tests require the exact local database orion_stage2_test")
    return value


def maintenance_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    return urlunsplit((parsed.scheme, parsed.netloc, "/postgres", parsed.query, parsed.fragment))


def reset_database(database_url: str) -> None:
    database_name = urlsplit(database_url).path.removeprefix("/")
    with psycopg.connect(maintenance_url(database_url), autocommit=True) as connection:
        connection.execute(
            "SELECT pg_catalog.pg_terminate_backend(pid) FROM pg_catalog.pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_catalog.pg_backend_pid()",
            (database_name,),
        )
        connection.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name)))
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))


def set_owner(connection: psycopg.Connection, user_id: UUID) -> None:
    connection.execute("SET LOCAL ROLE authenticated")
    connection.execute(
        "SELECT pg_catalog.set_config('request.jwt.claims', %s, true)",
        (f'{{"sub":"{user_id}","role":"authenticated"}}',),
    )


def test_fresh_install_migration_ledger_rls_constraints_and_cascades() -> None:
    database_url = disposable_database_url()
    reset_database(database_url)
    migrations = load_migrations(ROOT / "migrations")
    assert [migration.version for migration in migrations] == [1]
    assert (ROOT / "supabase_schema.sql").read_bytes() == (
        ROOT / "migrations" / "0001_foundation.sql"
    ).read_bytes()

    with psycopg.connect(database_url) as connection:
        connection.execute((ROOT / "tests/sql/bootstrap_auth.sql").read_text(), prepare=False)
        connection.execute(
            "INSERT INTO auth.users (id, raw_user_meta_data) VALUES (%s, %s::jsonb)",
            (USER_ONE, '{"display_name":"Existing User"}'),
        )
        connection.commit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: apply_migrations(database_url, migrations), range(2)))
    assert sorted(len(result) for result in results) == [0, 1]
    assert apply_migrations(database_url, migrations) == ()

    with psycopg.connect(database_url) as connection:
        ledger = connection.execute(
            "SELECT version, name, checksum FROM public.schema_migrations"
        ).fetchall()
        assert ledger == [(1, migrations[0].name, migrations[0].checksum)]
        assert connection.execute("SELECT count(*) FROM public.themes").fetchone() == (8,)
        assert connection.execute(
            "SELECT count(*) FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = ANY(%s) "
            "AND c.relrowsecurity AND c.relforcerowsecurity",
            (
                [
                    "user_profiles",
                    "entry_drafts",
                    "entries",
                    "entry_classifications",
                    "entry_themes",
                    "ideas",
                    "extracted_memories",
                    "reflections",
                    "past_entry_imports",
                ],
            ),
        ).fetchone() == (9,)
        assert connection.execute(
            "SELECT rolcanlogin, rolsuper, rolcreaterole, rolcreatedb, rolinherit, rolbypassrls "
            "FROM pg_catalog.pg_roles WHERE rolname = 'orion_worker'"
        ).fetchone() == (False, False, False, False, False, False)
        assert connection.execute(
            "SELECT display_name, timezone FROM public.user_profiles WHERE user_id = %s",
            (USER_ONE,),
        ).fetchone() == ("", "UTC")
        connection.execute(
            "INSERT INTO auth.users (id, raw_user_meta_data) VALUES (%s, %s::jsonb)",
            (USER_TWO, '{"display_name":"New User"}'),
        )
        assert connection.execute(
            "SELECT display_name, timezone FROM public.user_profiles WHERE user_id = %s",
            (USER_TWO,),
        ).fetchone() == ("New User", "UTC")
        connection.commit()

    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            connection.execute(
                "UPDATE public.user_profiles SET timezone = 'Not/A_Real_Zone' WHERE user_id = %s",
                (USER_TWO,),
            )

    sqlalchemy_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    settings = Settings.model_validate(
        {
            "ENVIRONMENT": "test",
            "APP_DATABASE_URL": SecretStr(sqlalchemy_url),
            "CORS_ALLOW_ORIGINS": "https://app.example.test",
            "LOG_FORMAT": "text",
        }
    )
    app = create_app(
        settings=settings,
        database_sessions=build_database_sessions(settings),
        token_verifier=UserTwoVerifier(),
        account_auth=LocalAccountAuth(),
    )
    with TestClient(app) as client:
        read = client.get("/api/v1/profile", headers={"Authorization": "Bearer access"})
        updated = client.patch(
            "/api/v1/profile",
            headers={"Authorization": "Bearer access"},
            json={"timezone": "Asia/Kolkata"},
        )
    assert read.json() == {"display_name": "New User", "timezone": "UTC"}
    assert updated.json() == {"display_name": "New User", "timezone": "Asia/Kolkata"}

    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    "INSERT INTO public.entries (user_id, content_envelope, input_type, entry_date) "
                    "VALUES (%s, '{}'::jsonb, 'text', CURRENT_DATE)",
                    (USER_ONE,),
                )
        with connection.transaction():
            set_owner(connection, USER_ONE)
            assert connection.execute(
                "SELECT user_id FROM public.user_profiles ORDER BY user_id"
            ).fetchall() == [(USER_ONE,)]
            assert connection.execute(
                "UPDATE public.user_profiles SET display_name = 'blocked' WHERE user_id = %s RETURNING user_id",
                (USER_TWO,),
            ).fetchall() == []
            connection.execute(
                "UPDATE public.user_profiles SET display_name = 'Owner' WHERE user_id = %s",
                (USER_ONE,),
            )
        with connection.transaction():
            set_owner(connection, USER_ONE)
            draft_id = connection.execute(
                "INSERT INTO public.entry_drafts "
                "(user_id, content_envelope, fingerprint_key_id, content_fingerprint) "
                "VALUES (%s, %s::jsonb, 'test-key', %s) RETURNING id",
                (USER_ONE, ENVELOPE, "b" * 64),
            ).fetchone()[0]
        with connection.transaction():
            set_owner(connection, USER_TWO)
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                connection.execute(
                    "INSERT INTO public.entries (user_id, content_envelope, input_type, entry_date, source_draft_id) "
                    "VALUES (%s, %s::jsonb, 'text', CURRENT_DATE, %s)",
                    (USER_TWO, ENVELOPE, draft_id),
                )

    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            set_owner(connection, USER_ONE)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute("SELECT * FROM public.past_entry_imports")
        with connection.transaction():
            set_owner(connection, USER_ONE)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(
                    "INSERT INTO public.ideas (user_id, entry_id, content) "
                    "VALUES (%s, %s, 'blocked')",
                    (USER_ONE, UUID(int=0)),
                )
        with connection.transaction():
            connection.execute("SET LOCAL ROLE anon")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute("SELECT * FROM public.theme_configs")
        with connection.transaction():
            connection.execute("SET LOCAL ROLE orion_worker")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute("SELECT * FROM public.past_entry_imports")

    with psycopg.connect(database_url) as connection:
        entry_id = connection.execute(
            "INSERT INTO public.entries (user_id, content_envelope, input_type, entry_date) "
            "VALUES (%s, %s::jsonb, 'text', CURRENT_DATE) RETURNING id",
            (USER_ONE, ENVELOPE),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO public.past_entry_imports "
            "(user_id, entry_id, fingerprint_key_id, request_fingerprint) "
            "VALUES (%s, %s, 'test-key', %s)",
            (USER_ONE, entry_id, "a" * 64),
        )
        connection.execute("DELETE FROM auth.users WHERE id = %s", (USER_ONE,))
        for table in (
            "user_profiles",
            "entry_drafts",
            "entries",
            "entry_classifications",
            "entry_themes",
            "ideas",
            "extracted_memories",
            "reflections",
            "past_entry_imports",
        ):
            assert connection.execute(
                sql.SQL("SELECT count(*) FROM public.{} WHERE user_id = %s").format(
                    sql.Identifier(table)
                ),
                (USER_ONE,),
            ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM public.user_profiles WHERE user_id = %s", (USER_TWO,)
        ).fetchone() == (1,)
        connection.commit()

    with psycopg.connect(database_url) as connection:
        connection.execute(
            "UPDATE public.schema_migrations SET checksum = %s WHERE version = 1",
            ("0" * 64,),
        )
        connection.commit()
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        apply_migrations(database_url, migrations)
