from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from fastapi import Request
from multipart import MultipartParser
from multipart.multipart import parse_options_header

from app.shared.exceptions.domain import DomainError


MAX_AUDIO_BYTES = 25 * 1024 * 1024
MAX_MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_AUDIO_SECONDS = 20 * 60
TRANSCRIPTION_TIMEOUT_SECONDS = 120.0
MIME_FAMILIES = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp4": "mp4",
    "audio/x-m4a": "mp4",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
}
FAMILY_EXTENSIONS = {
    "wav": ".wav",
    "mp3": ".mp3",
    "mp4": ".m4a",
    "webm": ".webm",
    "ogg": ".ogg",
}


class Transcriber(Protocol):
    async def transcribe(self, path: Path, mime_type: str) -> str: ...


class OpenAITranscriber:
    def __init__(self, client: Any, *, timeout: float) -> None:
        self._client = client.with_options(max_retries=0, timeout=timeout)

    async def transcribe(self, path: Path, mime_type: str) -> str:
        def call() -> str:
            with path.open("rb") as audio:
                result = self._client.audio.transcriptions.create(
                    model="whisper-1",
                    file=(
                        f"audio{FAMILY_EXTENSIONS[MIME_FAMILIES[mime_type]]}",
                        audio,
                        mime_type,
                    ),
                    response_format="text",
                )
            value = result if isinstance(result, str) else getattr(result, "text", None)
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError("transcription result unavailable")
            return value

        try:
            return await asyncio.to_thread(call)
        except DomainError:
            raise
        except Exception as exc:
            if getattr(exc, "status_code", None) == 429:
                raise DomainError(
                    429,
                    "RATE_LIMITED",
                    "Too many requests. Try again later.",
                    details={"retry_after_seconds": 60},
                    headers={"Retry-After": "60"},
                ) from exc
            raise DomainError(
                502,
                "PROVIDER_UNAVAILABLE",
                "Could not complete this request right now.",
            ) from exc


class UnavailableTranscriber:
    async def transcribe(self, _path: Path, _mime_type: str) -> str:
        raise DomainError(
            503,
            "SERVICE_UNAVAILABLE",
            "This operation is temporarily unavailable.",
            details={"retry_after_seconds": 60},
            headers={"Retry-After": "60"},
        )


@dataclass(frozen=True, slots=True)
class ParsedAudio:
    path: Path
    mime_type: str
    size: int


class _MultipartState:
    def __init__(self, file_object) -> None:
        self.file = file_object
        self.header_name = bytearray()
        self.header_value = bytearray()
        self.headers: dict[bytes, bytes] = {}
        self.parts = 0
        self.audio_parts = 0
        self.current_is_audio = False
        self.mime_type = ""
        self.size = 0

    def part_begin(self) -> None:
        self.parts += 1
        self.headers = {}
        self.current_is_audio = False

    def header_field(self, data: bytes, start: int, end: int) -> None:
        self.header_name.extend(data[start:end])

    def header_value_data(self, data: bytes, start: int, end: int) -> None:
        self.header_value.extend(data[start:end])

    def header_end(self) -> None:
        self.headers[bytes(self.header_name).lower()] = bytes(self.header_value)
        self.header_name.clear()
        self.header_value.clear()

    def headers_finished(self) -> None:
        disposition, options = parse_options_header(self.headers.get(b"content-disposition", b""))
        if disposition != b"form-data" or options.get(b"name") != b"audio" or b"filename" not in options:
            raise ValueError("multipart must contain exactly one audio file")
        self.audio_parts += 1
        if self.audio_parts != 1 or self.parts != 1:
            raise ValueError("multipart must contain exactly one audio file")
        self.current_is_audio = True
        self.mime_type = self.headers.get(b"content-type", b"").decode("ascii", errors="ignore").lower()

    def part_data(self, data: bytes, start: int, end: int) -> None:
        if not self.current_is_audio:
            raise ValueError("undeclared multipart part")
        chunk = data[start:end]
        self.size += len(chunk)
        if self.size > MAX_AUDIO_BYTES:
            raise OverflowError("audio size exceeded")
        self.file.write(chunk)


async def parse_audio_upload(request: Request) -> ParsedAudio:
    content_type = request.headers.get("Content-Type", "")
    media_type, options = parse_options_header(content_type.encode("latin-1"))
    boundary = options.get(b"boundary")
    if media_type != b"multipart/form-data" or not boundary:
        raise DomainError(415, "UNSUPPORTED_AUDIO_FORMAT", "The audio format is not supported.")
    temporary = tempfile.NamedTemporaryFile(prefix="orion-audio-", suffix=".upload", delete=False)
    path = Path(temporary.name)
    state = _MultipartState(temporary)
    parser = MultipartParser(
        boundary,
        {
            "on_part_begin": state.part_begin,
            "on_header_field": state.header_field,
            "on_header_value": state.header_value_data,
            "on_header_end": state.header_end,
            "on_headers_finished": state.headers_finished,
            "on_part_data": state.part_data,
        },
    )
    try:
        transport_size = 0
        async for chunk in request.stream():
            transport_size += len(chunk)
            if transport_size > MAX_AUDIO_BYTES + MAX_MULTIPART_OVERHEAD_BYTES:
                raise OverflowError("multipart transport size exceeded")
            parser.write(chunk)
        parser.finalize()
        temporary.flush()
        temporary.close()
        if state.parts != 1 or state.audio_parts != 1 or state.size == 0:
            raise ValueError("multipart must contain exactly one nonempty audio file")
        if state.mime_type not in MIME_FAMILIES:
            raise DomainError(415, "UNSUPPORTED_AUDIO_FORMAT", "The audio format is not supported.")
        return ParsedAudio(path=path, mime_type=state.mime_type, size=state.size)
    except OverflowError as exc:
        temporary.close()
        path.unlink(missing_ok=True)
        raise DomainError(413, "AUDIO_LIMIT_EXCEEDED", "The audio file exceeds the allowed limit.") from exc
    except DomainError:
        temporary.close()
        path.unlink(missing_ok=True)
        raise
    except BaseException as exc:
        temporary.close()
        path.unlink(missing_ok=True)
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise DomainError(422, "VALIDATION_ERROR", "The request is invalid.") from exc


def validate_signature(path: Path, mime_type: str) -> None:
    with path.open("rb") as audio:
        header = audio.read(16)
    family = MIME_FAMILIES[mime_type]
    actual = None
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        actual = "wav"
    elif header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0):
        actual = "mp3"
    elif len(header) >= 12 and header[4:8] == b"ftyp":
        actual = "mp4"
    elif header.startswith(b"\x1aE\xdf\xa3"):
        actual = "webm"
    elif header.startswith(b"OggS"):
        actual = "ogg"
    if actual != family:
        raise DomainError(415, "UNSUPPORTED_AUDIO_FORMAT", "The audio format is not supported.")


async def validate_decodable_audio(path: Path) -> None:
    probe = await _run_process(
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration:stream=codec_type",
        "-of", "json",
        str(path),
        timeout=15,
    )
    try:
        payload = json.loads(probe)
        has_audio = any(item.get("codec_type") == "audio" for item in payload.get("streams", []))
        reported_duration = _positive_duration(payload.get("format", {}).get("duration"))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DomainError(415, "UNSUPPORTED_AUDIO_FORMAT", "The audio format is not supported.") from exc
    if not has_audio:
        raise DomainError(415, "UNSUPPORTED_AUDIO_FORMAT", "The audio format is not supported.")
    if reported_duration is not None and reported_duration > MAX_AUDIO_SECONDS:
        raise DomainError(413, "AUDIO_LIMIT_EXCEEDED", "The audio file exceeds the allowed limit.")
    decoded = await _run_process(
        "ffmpeg",
        "-v", "error",
        "-i", str(path),
        "-map", "0:a:0",
        "-f", "null", "-",
        "-progress", "pipe:1",
        "-nostats",
        timeout=60,
    )
    decoded_duration = _decoded_duration(decoded)
    if decoded_duration is None:
        raise DomainError(415, "UNSUPPORTED_AUDIO_FORMAT", "The audio format is not supported.")
    if decoded_duration > MAX_AUDIO_SECONDS:
        raise DomainError(413, "AUDIO_LIMIT_EXCEEDED", "The audio file exceeds the allowed limit.")


def _positive_duration(value: object) -> float | None:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def _decoded_duration(progress: str) -> float | None:
    values = []
    for line in progress.splitlines():
        if line.startswith("out_time_us="):
            try:
                values.append(int(line.removeprefix("out_time_us=")) / 1_000_000)
            except ValueError:
                continue
    return max(values) if values and max(values) > 0 else None


async def _run_process(*args: str, timeout: float) -> str:
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except BaseException:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        raise
    if process.returncode != 0:
        raise DomainError(415, "UNSUPPORTED_AUDIO_FORMAT", "The audio format is not supported.")
    return stdout.decode("utf-8", errors="strict")


def remove_audio(path: Path | None) -> None:
    if path is not None:
        path.unlink(missing_ok=True)
