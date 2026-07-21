from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import Request, Response

from app.modules.entries import audio
from app.modules.entries.controller import create_voice_entry
from app.modules.entries.types import VoicePreparation
from app.shared.auth.context import AuthContext
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.exceptions.domain import DomainError


FORMATS = (
    ("wav", "audio/wav"),
    ("mp3", "audio/mpeg"),
    ("m4a", "audio/mp4"),
    ("webm", "audio/webm"),
    ("ogg", "audio/ogg"),
)


def make_audio(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.08",
            "-y",
            str(path),
        ],
        check=True,
        timeout=15,
    )


@pytest.mark.parametrize(("suffix", "mime_type"), FORMATS)
def test_every_supported_genuine_container_is_signature_checked_and_decodable(
    tmp_path: Path, suffix: str, mime_type: str
) -> None:
    path = tmp_path / f"sample.{suffix}"
    make_audio(path)
    audio.validate_signature(path, mime_type)
    asyncio.run(audio.validate_decodable_audio(path))


@pytest.mark.parametrize(
    ("payload", "mime_type"),
    [
        (b"", "audio/wav"),
        (b"RIFF\x00\x00\x00\x00WAVE", "audio/mpeg"),
        (b"ID3", "audio/mpeg"),
        (b"not audio", "audio/ogg"),
    ],
)
def test_empty_mismatch_malformed_truncated_and_header_only_are_rejected(
    tmp_path: Path, payload: bytes, mime_type: str
) -> None:
    path = tmp_path / "input"
    path.write_bytes(payload)
    if payload == b"ID3":
        audio.validate_signature(path, mime_type)
        with pytest.raises(DomainError) as failure:
            asyncio.run(audio.validate_decodable_audio(path))
    else:
        with pytest.raises(DomainError) as failure:
            audio.validate_signature(path, mime_type)
    assert failure.value.status_code == 415
    assert failure.value.error_code == "UNSUPPORTED_AUDIO_FORMAT"


def test_unsupported_declared_mime_is_not_in_frozen_allowlist() -> None:
    assert set(audio.MIME_FAMILIES) == {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp4",
        "audio/x-m4a",
        "audio/webm",
        "audio/ogg",
    }


def test_exact_and_over_duration_boundaries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "audio.wav"
    path.write_bytes(b"content is not inspected by this subprocess seam")
    calls = 0

    async def exact(*_args: str, timeout: float) -> str:
        nonlocal calls
        calls += 1
        if _args[0] == "ffprobe":
            return '{"format":{"duration":"1200"},"streams":[{"codec_type":"audio"}]}'
        return "out_time_us=1200000000\nprogress=end\n"

    monkeypatch.setattr(audio, "_run_process", exact)
    asyncio.run(audio.validate_decodable_audio(path))
    assert calls == 2

    async def over(*_args: str, timeout: float) -> str:
        return '{"format":{"duration":"1200.001"},"streams":[{"codec_type":"audio"}]}'

    monkeypatch.setattr(audio, "_run_process", over)
    with pytest.raises(DomainError) as failure:
        asyncio.run(audio.validate_decodable_audio(path))
    assert failure.value.status_code == 413
    assert failure.value.error_code == "AUDIO_LIMIT_EXCEEDED"


def test_decoded_duration_defeats_forged_short_container_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "audio"
    path.write_bytes(b"ignored")

    async def result(*args: str, timeout: float) -> str:
        if args[0] == "ffprobe":
            return '{"format":{"duration":"1"},"streams":[{"codec_type":"audio"}]}'
        return "out_time_us=1200001000\nprogress=end\n"

    monkeypatch.setattr(audio, "_run_process", result)
    with pytest.raises(DomainError) as failure:
        asyncio.run(audio.validate_decodable_audio(path))
    assert failure.value.status_code == 413
    assert failure.value.error_code == "AUDIO_LIMIT_EXCEEDED"


def test_missing_container_duration_is_accepted_only_with_positive_decoded_duration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "audio"
    path.write_bytes(b"ignored")

    async def result(*args: str, timeout: float) -> str:
        if args[0] == "ffprobe":
            return '{"format":{},"streams":[{"codec_type":"audio"}]}'
        return "out_time_us=750000\nprogress=end\n"

    monkeypatch.setattr(audio, "_run_process", result)
    asyncio.run(audio.validate_decodable_audio(path))


@pytest.mark.parametrize(
    "probe",
    [
        '{}',
        '{"format":{},"streams":[{"codec_type":"audio"}]}',
        '{"format":{"duration":"0"},"streams":[{"codec_type":"audio"}]}',
        '{"format":{"duration":"4"},"streams":[{"codec_type":"video"}]}',
    ],
)
def test_forged_or_missing_duration_and_missing_audio_stream_are_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, probe: str
) -> None:
    path = tmp_path / "audio"
    path.write_bytes(b"ignored")

    async def result(*_args: str, timeout: float) -> str:
        return probe

    monkeypatch.setattr(audio, "_run_process", result)
    with pytest.raises(DomainError) as failure:
        asyncio.run(audio.validate_decodable_audio(path))
    assert failure.value.status_code == 415


def test_subprocess_timeout_terminates_and_awaits_owned_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Process:
        returncode = None
        terminated = False
        killed = False
        waited = False

        async def communicate(self):
            await asyncio.sleep(60)

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> int:
            self.returncode = -15
            self.waited = True
            return self.returncode

    process = Process()

    async def create(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(audio._run_process("ffprobe", timeout=0.001))
    assert process.terminated is True
    assert process.waited is True


def test_size_enforcement_is_incremental_at_exact_boundary(tmp_path: Path) -> None:
    path = tmp_path / "upload"
    with path.open("wb") as destination:
        state = audio._MultipartState(destination)
        state.current_is_audio = True
        chunk = b"a" * (1024 * 1024)
        for _ in range(25):
            state.part_data(chunk, 0, len(chunk))
        assert state.size == audio.MAX_AUDIO_BYTES
        with pytest.raises(OverflowError):
            state.part_data(b"x", 0, 1)


def test_remove_audio_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "owned.upload"
    path.write_bytes(b"private bytes")
    audio.remove_audio(path)
    audio.remove_audio(path)
    assert not path.exists()


def test_whisper_transcription_is_single_attempt_bounded_and_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "audio.wav"
    path.write_bytes(b"private audio")

    class Transcriptions:
        calls = 0

        def create(self, **kwargs):
            self.calls += 1
            assert kwargs["model"] == "whisper-1"
            return SimpleNamespace(text="safe transcript")

    class Client:
        def __init__(self):
            self.transcriptions = Transcriptions()
            self.audio = SimpleNamespace(transcriptions=self.transcriptions)
            self.options = None

        def with_options(self, **kwargs):
            self.options = kwargs
            return self

    client = Client()
    transcriber = audio.OpenAITranscriber(client, timeout=120)
    assert asyncio.run(transcriber.transcribe(path, "audio/wav")) == "safe transcript"
    assert client.transcriptions.calls == 1
    assert client.options == {"max_retries": 0, "timeout": 120}


def test_transcription_rate_limit_and_unavailable_have_canonical_retry_headers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "audio.wav"
    path.write_bytes(b"private audio")

    class RateFailure(Exception):
        status_code = 429

    class Calls:
        def create(self, **_kwargs):
            raise RateFailure("private provider payload")

    class Client:
        audio = SimpleNamespace(transcriptions=Calls())

        def with_options(self, **_kwargs):
            return self

    with pytest.raises(DomainError) as rate_limited:
        asyncio.run(audio.OpenAITranscriber(Client(), timeout=120).transcribe(path, "audio/wav"))
    assert rate_limited.value.status_code == 429
    assert rate_limited.value.error_code == "RATE_LIMITED"
    assert rate_limited.value.headers == {"Retry-After": "60"}

    with pytest.raises(DomainError) as unavailable:
        asyncio.run(audio.UnavailableTranscriber().transcribe(path, "audio/wav"))
    assert unavailable.value.status_code == 503
    assert unavailable.value.headers == {"Retry-After": "60"}


def test_cancelled_multipart_stream_removes_route_owned_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(audio.tempfile, "tempdir", str(tmp_path))
    events = 0

    async def receive():
        nonlocal events
        events += 1
        if events == 1:
            return {
                "type": "http.request",
                "body": (
                    b"--boundary\r\nContent-Disposition: form-data; name=\"audio\"; "
                    b"filename=\"private.wav\"\r\nContent-Type: audio/wav\r\n\r\nRIFF"
                ),
                "more_body": True,
            }
        raise asyncio.CancelledError

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/entries/voice",
            "headers": [(b"content-type", b"multipart/form-data; boundary=boundary")],
        },
        receive=receive,
    )
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(audio.parse_audio_upload(request))
    assert not list(tmp_path.glob("orion-audio-*"))


@pytest.mark.parametrize("failure", [asyncio.CancelledError(), RuntimeError("persistence failed")])
def test_controller_cancellation_and_persistence_failure_abandon_claim_and_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: BaseException
) -> None:
    path = tmp_path / "owned.upload"
    path.write_bytes(b"route-owned audio")
    claim_token = UUID("99999999-9999-4999-8999-999999999999")
    user_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

    class Service:
        abandoned = False

        def prepare_voice(self, **_kwargs):
            return VoicePreparation(
                effective_date=__import__("datetime").date.today(),
                claim_token=claim_token,
                replay=None,
            )

        def create_voice(self, **_kwargs):
            raise failure

        def abandon_voice(self, **_kwargs):
            self.abandoned = True

    class Transcriber:
        async def transcribe(self, _path, _mime):
            return "safe transcript"

    service = Service()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/entries/voice",
            "headers": [(b"idempotency-key", b"action")],
            "app": SimpleNamespace(state=SimpleNamespace(transcriber=Transcriber())),
        }
    )
    monkeypatch.setattr(
        "app.modules.entries.controller.parse_audio_upload",
        lambda _request: _async_result(audio.ParsedAudio(path, "audio/wav", path.stat().st_size)),
    )
    monkeypatch.setattr("app.modules.entries.controller.validate_signature", lambda *_args: None)
    monkeypatch.setattr(
        "app.modules.entries.controller.validate_decodable_audio", lambda *_args: _async_result(None)
    )
    operation = create_voice_entry(
        request=request,
        response=Response(),
        entry_date=None,
        auth=AuthContext(user_id, "token", UnitOfWorkFactory(None, None)),
        service=service,
    )
    if isinstance(failure, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(operation)
    else:
        with pytest.raises(DomainError) as mapped:
            asyncio.run(operation)
        assert mapped.value.status_code == 502
    assert service.abandoned is True
    assert not path.exists()


async def _async_result(value):
    return value
