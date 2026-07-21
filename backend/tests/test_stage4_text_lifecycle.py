from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID
from zoneinfo import ZoneInfo
from datetime import datetime

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from psycopg import sql

from app.main import create_app
from app.modules.processing.provider import ProviderUnavailableError
from app.modules.processing.schemas import ModelEntryAnalysis, ModelEntryExtraction
from app.modules.profile.types import AccountDeletionOutcome
from app.shared.config import Settings
from app.shared.database.session import build_database_sessions
from app.shared.security.encryption import AesGcmContentCipher
from scripts.migrate import apply_migrations, load_migrations


ROOT = Path(__file__).resolve().parents[1]
USER_ONE = UUID("55555555-5555-4555-8555-555555555555")
USER_TWO = UUID("66666666-6666-4666-8666-666666666666")


def database_url() -> str:
    value = os.environ.get("STAGE2_DISPOSABLE_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("STAGE2_DISPOSABLE_DATABASE_URL is not configured")
    parsed = urlsplit(value)
    if parsed.path != "/orion_stage2_test" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        pytest.fail("text lifecycle requires exact local disposable database")
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


class Verifier:
    def verify_access_token(self, token: str) -> str:
        return str(USER_TWO if token == "two" else USER_ONE)


class AccountAuth:
    def verify_user(self, _token: str) -> UUID:
        return USER_ONE

    def delete_user(self, _user_id: UUID) -> AccountDeletionOutcome:
        return AccountDeletionOutcome.ALREADY_MISSING


def empty_extraction() -> ModelEntryExtraction:
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


class Provider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_next = False
        self.failures_remaining = 0
        self.block_next = False
        self.entered = Event()
        self.release = Event()

    def analyze(
        self, *, redacted_text: str, themes, deterministic_features, entry_date, safety_identifier
    ) -> ModelEntryAnalysis:
        self.calls.append(redacted_text)
        if self.fail_next or self.failures_remaining:
            self.fail_next = False
            self.failures_remaining = max(0, self.failures_remaining - 1)
            raise ProviderUnavailableError("private provider payload")
        if self.block_next:
            self.block_next = False
            self.entered.set()
            if not self.release.wait(timeout=5):
                raise RuntimeError("test provider release timed out")
        return ModelEntryAnalysis.model_validate(
            {
                "quality": {
                    "entry_kind": "personal_reflection",
                    "lived_experience_score": 0.8,
                    "self_reference_score": 0.8,
                    "emotional_information_score": 0.8,
                    "causal_reasoning_score": 0.8,
                    "personal_relevance_score": 0.8,
                    "confidence": 0.9,
                    "eligibility": "accepted",
                    "exclusion_reason_codes": [],
                },
                "signals": [],
                "legacy": empty_extraction(),
            }
        )


def build_cipher() -> AesGcmContentCipher:
    return AesGcmContentCipher(
        encryption_keys={"entry-key": b"e" * 32},
        active_encryption_key_id="entry-key",
        fingerprint_keys={"fingerprint-key": b"f" * 32},
        active_fingerprint_key_id="fingerprint-key",
    )


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    assert response.json()["error_code"] == code


def test_encrypted_draft_text_replay_list_detail_and_retry_lifecycle() -> None:
    value = database_url()
    reset(value)
    with psycopg.connect(value) as connection:
        connection.execute((ROOT / "tests/sql/bootstrap_auth.sql").read_text(), prepare=False)
        connection.execute(
            "INSERT INTO auth.users (id, raw_user_meta_data) VALUES "
            "(%s, '{\"display_name\":\"One\"}'::jsonb), "
            "(%s, '{\"display_name\":\"Two\"}'::jsonb)",
            (USER_ONE, USER_TWO),
        )
        connection.commit()
    apply_migrations(value, load_migrations(ROOT / "migrations"))
    with psycopg.connect(value) as connection:
        connection.execute(
            "UPDATE public.user_profiles SET timezone = 'Asia/Kolkata' WHERE user_id = %s",
            (USER_ONE,),
        )
        connection.commit()

    provider = Provider()
    cipher = build_cipher()
    sqlalchemy_url = value.replace("postgresql://", "postgresql+psycopg://", 1)
    settings = Settings.model_validate(
        {
            "ENVIRONMENT": "test",
            "ENABLE_API_DOCS": False,
            "APP_DATABASE_URL": SecretStr(sqlalchemy_url),
            "WORKER_DATABASE_URL": SecretStr(sqlalchemy_url),
            "CORS_ALLOW_ORIGINS": "https://app.example.test",
            "LOG_FORMAT": "text",
            "RATE_LIMITING_ENABLED": False,
        }
    )
    app = create_app(
        settings=settings,
        database_sessions=build_database_sessions(settings),
        token_verifier=Verifier(),
        account_auth=AccountAuth(),
        extraction_provider=provider,
        content_cipher=cipher,
    )
    app.state.job_service._heartbeat_interval = 0.01
    one = {"Authorization": "Bearer one"}
    two = {"Authorization": "Bearer two"}
    content = "I should call my mentor. " + "😀" * 210
    with TestClient(app) as client:
        empty = client.get("/api/v1/entry/draft", headers=one)
        assert empty.json() == {"content": None, "updated_at": None}
        saved = client.put("/api/v1/entry/draft", headers=one, json={"content": f"  {content}  "})
        assert saved.status_code == 200
        assert saved.json()["content"] == content
        with psycopg.connect(value) as connection:
            draft_id, stored_draft = connection.execute(
                "SELECT id, content_envelope::text FROM public.entry_drafts "
                "WHERE user_id = %s AND status = 'active'",
                (USER_ONE,),
            ).fetchone()
        assert content not in stored_draft
        client.put("/api/v1/entry/draft", headers=one, json={"content": content})
        with psycopg.connect(value) as connection:
            assert connection.execute(
                "SELECT id FROM public.entry_drafts WHERE user_id = %s AND status = 'active'",
                (USER_ONE,),
            ).fetchone() == (draft_id,)
        restored = client.get("/api/v1/entry/draft", headers=one)
        assert restored.json()["content"] == content
        assert client.get("/api/v1/entry/draft", headers=two).json() == {
            "content": None,
            "updated_at": None,
        }
        idempotency_header = client.post(
            "/api/v1/entry",
            headers={**one, "Idempotency-Key": "not-accepted-for-text"},
            json={"content": content},
        )
        assert_error(idempotency_header, 422, "VALIDATION_ERROR")

        created = client.post("/api/v1/entry", headers=one, json={"content": content})
        assert created.status_code == 201
        created_body = created.json()
        entry_id = created_body["id"]
        assert created_body["processing_status"] == "pending"
        assert created_body["classification"] is None
        assert provider.calls == []
        with psycopg.connect(value) as connection:
            assert connection.execute(
                "SELECT count(*), min(status) FROM public.processing_jobs "
                "WHERE entry_id = %s AND job_type = 'entry_processing'",
                (entry_id,),
            ).fetchone() == (1, "pending")
        assert app.state.processing_worker.run_one(
            worker_id="text-worker", uow=app.state.database_sessions.unit_of_work_factory
        ) is True
        completed_body = client.get(f"/api/v1/entries/{entry_id}", headers=one).json()
        assert completed_body["processing_status"] == "completed"
        assert completed_body["classification"] == {
            "theme_config_id": "00000000-0000-0000-0000-000000000801",
            "source": "initial",
            "mode": None,
            "themes": [],
        }
        assert created_body["entry_date"] == str(datetime.now(ZoneInfo("Asia/Kolkata")).date())
        replay = client.post("/api/v1/entry", headers=one, json={"content": content})
        assert replay.status_code == 200
        assert replay.json()["id"] == entry_id
        assert len(provider.calls) == 1

        page = client.get("/api/v1/entries?page=1&page_size=1", headers=one)
        assert page.status_code == 200
        assert page.headers["cache-control"] == "private, no-store"
        assert page.json()["total"] == 1
        assert page.json()["items"][0]["content_preview"] == content[:200]
        assert len(page.json()["items"][0]["content_preview"]) == 200
        detail = client.get(f"/api/v1/entries/{entry_id}", headers=one)
        assert detail.json()["content"] == content
        assert_error(client.get(f"/api/v1/entries/{entry_id}", headers=two), 404, "NOT_FOUND")

        client.put("/api/v1/entry/draft", headers=one, json={"content": "Draft A"})
        before = client.get("/api/v1/entries", headers=one).json()["total"]
        mismatch = client.post("/api/v1/entry", headers=one, json={"content": "Draft B"})
        assert_error(mismatch, 409, "INVALID_STATE")
        assert client.get("/api/v1/entries", headers=one).json()["total"] == before
        with psycopg.connect(value) as connection:
            active_id, active_envelope = connection.execute(
                "SELECT id, content_envelope FROM public.entry_drafts "
                "WHERE user_id = %s AND status = 'active'",
                (USER_ONE,),
            ).fetchone()
            active_envelope["tag"] = "AAAAAAAAAAAAAAAAAAAAAA=="
            connection.execute(
                "UPDATE public.entry_drafts SET content_envelope = %s::jsonb WHERE id = %s",
                (json.dumps(active_envelope), active_id),
            )
            connection.commit()
        assert_error(
            client.get("/api/v1/entry/draft", headers=one),
            503,
            "ENTRY_DRAFT_UNAVAILABLE",
        )
        client.put("/api/v1/entry/draft", headers=one, json={"content": "Draft A"})
        client.delete("/api/v1/entry/draft", headers=one)
        assert client.get("/api/v1/entry/draft", headers=one).json()["content"] is None

        concurrent_text = "One concurrent submission sentence."
        client.put("/api/v1/entry/draft", headers=one, json={"content": concurrent_text})
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(
                client.post, "/api/v1/entry", headers=one, json={"content": concurrent_text}
            )
            second_future = executor.submit(
                client.post, "/api/v1/entry", headers=one, json={"content": concurrent_text}
            )
            first = first_future.result(timeout=5)
            second = second_future.result(timeout=5)
        assert sorted([first.status_code, second.status_code]) == [200, 201]
        assert first.json()["id"] == second.json()["id"]
        assert provider.calls.count(concurrent_text) == 0
        concurrent_id = first.json()["id"]
        with psycopg.connect(value) as connection:
            assert connection.execute(
                "SELECT count(*) FROM public.processing_jobs WHERE entry_id = %s",
                (concurrent_id,),
            ).fetchone() == (1,)
        assert app.state.processing_worker.run_one(
            worker_id="text-worker", uow=app.state.database_sessions.unit_of_work_factory
        ) is True
        assert provider.calls.count(concurrent_text) == 1
        client.put("/api/v1/entry/draft", headers=one, json={"content": " \t\r\n "})
        assert client.get("/api/v1/entry/draft", headers=one).json()["content"] is None

        provider.failures_remaining = 3
        failing_text = "A provider-safe failure sentence."
        client.put("/api/v1/entry/draft", headers=one, json={"content": failing_text})
        failed = client.post("/api/v1/entry", headers=one, json={"content": failing_text})
        assert failed.status_code == 201
        assert failed.json()["processing_status"] == "pending"
        failed_id = UUID(failed.json()["id"])
        for attempt in range(1, 4):
            assert app.state.processing_worker.run_one(
                worker_id="text-worker", uow=app.state.database_sessions.unit_of_work_factory
            ) is True
            with psycopg.connect(value) as connection:
                state = connection.execute(
                    "SELECT status, attempts, last_error_code FROM public.processing_jobs "
                    "WHERE entry_id = %s",
                    (failed_id,),
                ).fetchone()
                assert state == (
                    "pending" if attempt < 3 else "failed",
                    attempt,
                    "PROVIDER_UNAVAILABLE",
                )
                if attempt < 3:
                    connection.execute(
                        "UPDATE public.processing_jobs SET run_after = pg_catalog.now() "
                        "WHERE entry_id = %s",
                        (failed_id,),
                    )
                    connection.commit()
        with psycopg.connect(value) as connection:
            assert connection.execute(
                "SELECT processing_status, processing_error_code FROM public.entries "
                "WHERE id = %s",
                (failed_id,),
            ).fetchone() == ("failed", "PROCESSING_FAILED")
        with ThreadPoolExecutor(max_workers=2) as executor:
            retry_future = executor.submit(
                client.post, f"/api/v1/entries/{failed_id}/retry", headers=one
            )
            concurrent_future = executor.submit(
                client.post, f"/api/v1/entries/{failed_id}/retry", headers=one
            )
            retried = retry_future.result(timeout=5)
            concurrent_retry = concurrent_future.result(timeout=5)
        successful_retry = retried if retried.status_code == 200 else concurrent_retry
        rejected_retry = concurrent_retry if retried.status_code == 200 else retried
        assert successful_retry.json()["processing_status"] == "pending"
        assert_error(rejected_retry, 409, "INVALID_STATE")
        with psycopg.connect(value) as connection:
            assert connection.execute(
                "SELECT status, attempts, claim_token FROM public.processing_jobs "
                "WHERE entry_id = %s",
                (failed_id,),
            ).fetchone() == ("pending", 0, None)
        assert app.state.processing_worker.run_one(
            worker_id="text-worker", uow=app.state.database_sessions.unit_of_work_factory
        ) is True
        assert client.get(
            f"/api/v1/entries/{failed_id}", headers=one
        ).json()["processing_status"] == "completed"
        assert_error(
            client.post(f"/api/v1/entries/{failed_id}/retry", headers=one),
            409,
            "INVALID_STATE",
        )

        client.put("/api/v1/entry/draft", headers=one, json={"content": content})
        distinct = client.post("/api/v1/entry", headers=one, json={"content": content})
        assert distinct.status_code == 201
        assert distinct.json()["id"] != entry_id

        ordered = client.get("/api/v1/entries?page=1&page_size=100", headers=one).json()
        with psycopg.connect(value) as connection:
            expected_ids = [
                str(row[0])
                for row in connection.execute(
                    "SELECT id FROM public.entries WHERE user_id = %s "
                    "ORDER BY entry_date DESC, created_at DESC, id DESC",
                    (USER_ONE,),
                ).fetchall()
            ]
        assert [item["id"] for item in ordered["items"]] == expected_ids

        with psycopg.connect(value) as connection:
            broken_envelope = connection.execute(
                "SELECT content_envelope FROM public.entries WHERE id = %s", (entry_id,)
            ).fetchone()[0]
            broken_envelope["tag"] = "AAAAAAAAAAAAAAAAAAAAAA=="
            connection.execute(
                "UPDATE public.entries SET content_envelope = %s::jsonb WHERE id = %s",
                (json.dumps(broken_envelope), entry_id),
            )
            connection.commit()
        unavailable = client.get(f"/api/v1/entries/{entry_id}", headers=one)
        assert_error(unavailable, 500, "ENTRY_CONTENT_UNAVAILABLE")
        assert_error(
            client.get(f"/api/v1/entries/{entry_id}", headers=two),
            404,
            "NOT_FOUND",
        )
        assert "tag" not in unavailable.text

    with psycopg.connect(value) as connection:
        rows = connection.execute(
            "SELECT id, content_envelope::text FROM public.entries WHERE user_id = %s",
            (USER_ONE,),
        ).fetchall()
        assert rows
        assert all(content not in envelope for _entry_id, envelope in rows)
        assert connection.execute(
            "SELECT count(*) FROM public.entry_drafts WHERE user_id = %s AND content_envelope IS NOT NULL",
            (USER_ONE,),
        ).fetchone() == (0,)
