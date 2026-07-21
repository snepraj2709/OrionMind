from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from psycopg import sql
from sqlalchemy import text

from app.main import create_app
from app.modules.entries import audio
from app.modules.processing.provider import ProviderUnavailableError
from app.modules.processing.schemas import ModelEntryExtraction
from app.modules.profile.types import AccountDeletionOutcome
from app.shared.config import Settings
from app.shared.database.session import build_database_sessions
from app.shared.security.encryption import AesGcmContentCipher
from scripts.migrate import apply_migrations, load_migrations


ROOT = Path(__file__).resolve().parents[1]
USER_ONE = UUID("77777777-7777-4777-8777-777777777777")
USER_TWO = UUID("88888888-8888-4888-8888-888888888888")


def database_url() -> str:
    value = os.environ.get("STAGE2_DISPOSABLE_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("STAGE2_DISPOSABLE_DATABASE_URL is not configured")
    parsed = urlsplit(value)
    if parsed.path != "/orion_stage2_test" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        pytest.fail("voice/past lifecycle requires exact local disposable database")
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


class Provider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_next = False

    def extract(self, *, content: str, themes) -> ModelEntryExtraction:
        self.calls.append(content)
        if self.fail_next:
            self.fail_next = False
            raise ProviderUnavailableError("private provider failure")
        candidate = content.startswith("Past candidate")
        return ModelEntryExtraction.model_validate(
            {
                "ideas": [{"source_segment_id": "segment_0001"}] if candidate else [],
                "memories": [],
                "theme": {"mode": None, "themes": []},
                "reflection": {
                    "filled_energy": None,
                    "drained_energy": None,
                    "learned_about_self": None,
                },
            }
        )


class Transcriber:
    def __init__(self) -> None:
        self.calls = 0
        self.fail_next = False

    async def transcribe(self, path: Path, mime_type: str) -> str:
        self.calls += 1
        assert path.exists()
        assert mime_type == "audio/wav"
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("private transcription failure")
        return "  Voice transcript should remain encrypted.  "


def build_cipher() -> AesGcmContentCipher:
    return AesGcmContentCipher(
        encryption_keys={"entry-key": b"e" * 32},
        active_encryption_key_id="entry-key",
        fingerprint_keys={"fingerprint-key": b"f" * 32},
        active_fingerprint_key_id="fingerprint-key",
    )


def make_wav(path: Path) -> bytes:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330:duration=0.08",
            "-y",
            str(path),
        ],
        check=True,
        timeout=15,
    )
    return path.read_bytes()


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    assert response.json()["error_code"] == code


def test_voice_and_past_import_lifecycle_and_worker_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = database_url()
    reset(value)
    with psycopg.connect(value) as connection:
        connection.execute((ROOT / "tests/sql/bootstrap_auth.sql").read_text(), prepare=False)
        connection.execute(
            "INSERT INTO auth.users (id, created_at) VALUES (%s, pg_catalog.now()), "
            "(%s, pg_catalog.now())",
            (USER_ONE, USER_TWO),
        )
        connection.commit()
    apply_migrations(value, load_migrations(ROOT / "migrations"))

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
            "REQUEST_TIMEOUT_SECONDS": 30,
        }
    )
    provider = Provider()
    transcriber = Transcriber()
    cipher = build_cipher()
    sessions = build_database_sessions(settings)
    app = create_app(
        settings=settings,
        database_sessions=sessions,
        token_verifier=Verifier(),
        account_auth=AccountAuth(),
        extraction_provider=provider,
        content_cipher=cipher,
        transcriber=transcriber,
    )
    app.state.job_service._heartbeat_interval = 0.01
    monkeypatch.setattr(audio.tempfile, "tempdir", str(tmp_path))
    wav = make_wav(tmp_path / "fixture.wav")
    headers = {"Authorization": "Bearer one", "Idempotency-Key": "voice-action-1"}

    with TestClient(app) as client:
        missing_key = client.post(
            "/api/v1/entries/voice",
            headers={"Authorization": "Bearer one"},
            files={"audio": ("secret-name.wav", wav, "audio/wav")},
        )
        assert_error(missing_key, 422, "VALIDATION_ERROR")
        created = client.post(
            "/api/v1/entries/voice",
            headers=headers,
            files={"audio": ("secret-name.wav", wav, "audio/wav")},
        )
        assert created.status_code == 201
        voice_id = UUID(created.json()["id"])
        assert created.json()["content"] == "Voice transcript should remain encrypted."
        assert created.json()["input_type"] == "audio"
        assert created.json()["processing_status"] == "pending"
        assert transcriber.calls == 1
        assert provider.calls == []
        assert not list(tmp_path.glob("orion-audio-*"))

        assert app.state.processing_worker.run_one(
            worker_id="shared-worker", uow=sessions.unit_of_work_factory
        ) is True
        assert client.get(
            f"/api/v1/entries/{voice_id}", headers={"Authorization": "Bearer one"}
        ).json()["processing_status"] == "completed"

        replay = client.post(
            "/api/v1/entries/voice",
            headers=headers,
            content=b"this is deliberately not multipart",
        )
        assert replay.status_code == 200
        assert replay.json()["id"] == str(voice_id)
        assert transcriber.calls == 1

        received = False
        sent: list[dict] = []

        async def forbidden_receive():
            nonlocal received
            received = True
            raise AssertionError("replay consumed an ASGI body event")

        async def capture_send(message):
            sent.append(message)

        asyncio.run(
            app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": "/api/v1/entries/voice",
                    "raw_path": b"/api/v1/entries/voice",
                    "query_string": b"",
                    "root_path": "",
                    "headers": [
                        (b"authorization", b"Bearer one"),
                        (b"idempotency-key", b"voice-action-1"),
                        (b"content-type", b"application/octet-stream"),
                    ],
                    "client": ("test", 1),
                    "server": ("test", 80),
                    "state": {},
                },
                forbidden_receive,
                capture_send,
            )
        )
        assert received is False
        assert next(message["status"] for message in sent if message["type"] == "http.response.start") == 200

        tomorrow = datetime.now(ZoneInfo("UTC")).date() + timedelta(days=1)
        assert_error(
            client.post(
                f"/api/v1/entries/voice?entry_date={tomorrow.isoformat()}",
                headers=headers,
                content=b"unconsumed",
            ),
            422,
            "VALIDATION_ERROR",
        )
        yesterday = datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)
        assert_error(
            client.post(
                f"/api/v1/entries/voice?entry_date={yesterday.isoformat()}",
                headers=headers,
                content=b"unconsumed",
            ),
            409,
            "INVALID_STATE",
        )

        second = client.post(
            "/api/v1/entries/voice",
            headers={**headers, "Idempotency-Key": "voice-action-2"},
            files={"audio": ("another.wav", wav, "audio/wav")},
        )
        assert second.status_code == 201
        assert second.json()["id"] != str(voice_id)
        assert second.json()["processing_status"] == "pending"
        assert transcriber.calls == 2
        assert app.state.processing_worker.run_one(
            worker_id="shared-worker", uow=sessions.unit_of_work_factory
        ) is True

        mismatch = client.post(
            "/api/v1/entries/voice",
            headers={**headers, "Idempotency-Key": "voice-mismatch"},
            files={"audio": ("fake.mp3", wav, "audio/mpeg")},
        )
        assert_error(mismatch, 415, "UNSUPPORTED_AUDIO_FORMAT")
        duplicate = client.post(
            "/api/v1/entries/voice",
            headers={**headers, "Idempotency-Key": "voice-duplicate"},
            files=[
                ("audio", ("one.wav", wav, "audio/wav")),
                ("audio", ("two.wav", wav, "audio/wav")),
            ],
        )
        assert_error(duplicate, 422, "VALIDATION_ERROR")
        undeclared = client.post(
            "/api/v1/entries/voice",
            headers={**headers, "Idempotency-Key": "voice-extra"},
            files=[
                ("audio", ("one.wav", wav, "audio/wav")),
                ("metadata", (None, "private")),
            ],
        )
        assert_error(undeclared, 422, "VALIDATION_ERROR")
        incomplete = client.post(
            "/api/v1/entries/voice",
            headers={
                **headers,
                "Idempotency-Key": "voice-incomplete",
                "Content-Type": "multipart/form-data; boundary=broken",
            },
            content=b"--broken\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"x.wav\"\r\nContent-Type: audio/wav\r\n\r\nRIFF",
        )
        assert_error(incomplete, 415, "UNSUPPORTED_AUDIO_FORMAT")
        assert not list(tmp_path.glob("orion-audio-*"))

        transcriber.fail_next = True
        transcription_failure = client.post(
            "/api/v1/entries/voice",
            headers={**headers, "Idempotency-Key": "voice-transcriber-failure"},
            files={"audio": ("secret.wav", wav, "audio/wav")},
        )
        assert_error(transcription_failure, 502, "PROVIDER_UNAVAILABLE")
        assert not list(tmp_path.glob("orion-audio-*"))

        provider.fail_next = True
        provider_failure = client.post(
            "/api/v1/entries/voice",
            headers={**headers, "Idempotency-Key": "voice-provider-failure"},
            files={"audio": ("secret.wav", wav, "audio/wav")},
        )
        assert provider_failure.status_code == 201
        assert provider_failure.json()["processing_status"] == "pending"
        failed_voice_id = UUID(provider_failure.json()["id"])
        calls_before_retry = transcriber.calls
        assert app.state.processing_worker.run_one(
            worker_id="shared-worker", uow=sessions.unit_of_work_factory
        ) is True
        with psycopg.connect(value) as connection:
            assert connection.execute(
                "SELECT status, attempts FROM public.processing_jobs WHERE entry_id = %s",
                (failed_voice_id,),
            ).fetchone() == ("pending", 1)
            connection.execute(
                "UPDATE public.processing_jobs SET run_after = pg_catalog.now() "
                "WHERE entry_id = %s",
                (failed_voice_id,),
            )
            connection.commit()
        assert app.state.processing_worker.run_one(
            worker_id="shared-worker", uow=sessions.unit_of_work_factory
        ) is True
        retried = client.get(
            f"/api/v1/entries/{failed_voice_id}",
            headers={"Authorization": "Bearer one"},
        )
        assert retried.json()["processing_status"] == "completed"
        assert transcriber.calls == calls_before_retry
        assert not list(tmp_path.glob("orion-audio-*"))

        today = datetime.now(ZoneInfo("UTC")).date()
        earliest = today.replace(year=today.year - 10)
        past_content = "Past candidate: I should call my mentor."
        provider_calls_before = len(provider.calls)
        accepted = client.post(
            "/api/v1/past-entries",
            headers={"Authorization": "Bearer one"},
            json={"entry_date": earliest.isoformat(), "content": f"  {past_content}  "},
        )
        assert accepted.status_code == 202
        assert accepted.headers["location"] == accepted.json()["status_url"]
        assert accepted.headers["cache-control"] == "private, no-store"
        assert accepted.json()["processing_status"] == "pending"
        assert len(provider.calls) == provider_calls_before
        past_id = UUID(accepted.json()["entry_id"])
        duplicate_past = client.post(
            "/api/v1/past-entries",
            headers={"Authorization": "Bearer one"},
            json={"entry_date": earliest.isoformat(), "content": past_content},
        )
        assert_error(duplicate_past, 409, "PAST_ENTRY_DUPLICATE")
        other_owner = client.post(
            "/api/v1/past-entries",
            headers={"Authorization": "Bearer two"},
            json={"entry_date": earliest.isoformat(), "content": past_content},
        )
        assert other_owner.status_code == 202
        assert_error(
            client.post(
                "/api/v1/past-entries",
                headers={"Authorization": "Bearer one"},
                json={"entry_date": (earliest - timedelta(days=1)).isoformat(), "content": "old"},
            ),
            422,
            "VALIDATION_ERROR",
        )
        assert_error(
            client.post(
                "/api/v1/past-entries",
                headers={"Authorization": "Bearer one"},
                json={"entry_date": today.isoformat(), "content": "   ", "extra": "forbidden"},
            ),
            422,
            "VALIDATION_ERROR",
        )

        assert app.state.processing_worker.run_one(
            worker_id="shared-worker", uow=sessions.unit_of_work_factory
        ) is True
        detail = client.get(
            f"/api/v1/entries/{past_id}", headers={"Authorization": "Bearer one"}
        )
        assert detail.status_code == 200
        assert detail.json()["processing_status"] == "completed"
        assert detail.json()["ideas"][0]["status"] == "approved"

    with psycopg.connect(value) as connection:
        stored = connection.execute(
            "SELECT content_envelope::text FROM public.entries WHERE id = %s", (voice_id,)
        ).fetchone()[0]
        assert "Voice transcript" not in stored
        assert wav[:32].hex() not in stored
        assert connection.execute(
            "SELECT status, decision_source FROM public.ideas WHERE entry_id = %s", (past_id,)
        ).fetchone() == ("approved", "past_import_auto")
        completed_import_id, completed_token = connection.execute(
            "SELECT id, completed_processing_token FROM public.past_entry_imports WHERE entry_id = %s",
            (past_id,),
        ).fetchone()
        assert completed_token is not None
        assert connection.execute(
            "SELECT status, claim_token FROM public.processing_jobs WHERE entry_id = %s",
            (past_id,),
        ).fetchone() == ("completed", completed_token)
        assert connection.execute(
            "SELECT count(*) FROM public.past_entry_imports WHERE user_id = %s", (USER_TWO,)
        ).fetchone() == (1,)

    # The other owner's historical entry uses the same queue and mirrors audit state.
    assert app.state.processing_worker.run_one(
        worker_id="shared-worker", uow=sessions.unit_of_work_factory
    ) is True
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT count(*) FROM public.processing_jobs WHERE status = 'pending'"
        ).fetchone() == (0,)

    with TestClient(app) as client:
        startup_item = client.post(
            "/api/v1/past-entries",
            headers={"Authorization": "Bearer one"},
            json={
                "entry_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
                "content": "Past candidate for startup recovery.",
            },
        )
        assert startup_item.status_code == 202
    startup_entry_id = UUID(startup_item.json()["entry_id"])
    with sessions.unit_of_work_factory.for_worker() as work:
        startup_claim = app.state.job_service._repository.claim(
            work.session, worker_id="interrupted-worker"
        )
    assert startup_claim is not None
    assert startup_claim.entry_id == startup_entry_id
    with psycopg.connect(value) as connection:
        connection.execute(
            "UPDATE public.processing_jobs SET heartbeat_at = pg_catalog.now() - interval '1 hour' "
            "WHERE id = %s",
            (startup_claim.job_id,),
        )
        connection.execute(
            "UPDATE public.past_entry_imports SET heartbeat_at = pg_catalog.now() - interval '1 hour' "
            "WHERE entry_id = %s",
            (startup_entry_id,),
        )
        connection.commit()
    # Web startup performs readiness only; generalized recovery belongs to the worker.
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT status FROM public.processing_jobs WHERE id = %s",
            (startup_claim.job_id,),
        ).fetchone() == ("running",)
    assert app.state.processing_worker.recover_stale(
        uow=sessions.unit_of_work_factory
    ) == 1
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT status, attempts, last_error_code FROM public.past_entry_imports "
            "WHERE entry_id = %s",
            (startup_entry_id,),
        ).fetchone() == ("pending", 1, "WORKER_INTERRUPTED")

    # Authenticated users and workers cannot bypass their narrow capabilities.
    with psycopg.connect(value) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with connection.transaction():
                connection.execute("SET LOCAL ROLE authenticated")
                connection.execute("SELECT public.claim_processing_job('browser')")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with connection.transaction():
                connection.execute("SET LOCAL ROLE orion_worker")
                connection.execute("SELECT * FROM public.past_entry_imports")


def test_leap_safe_ten_year_shift() -> None:
    from app.modules.entries.service import _shift_ten_years

    assert _shift_ten_years(datetime(2024, 2, 29).date()) == datetime(2014, 2, 28).date()
