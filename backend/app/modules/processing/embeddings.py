from __future__ import annotations

import logging
import math
import time
from typing import Any

import httpx

from app.modules.processing.provider import (
    ProviderResponseError,
    ProviderUnavailableError,
    _retryable,
)
from app.shared.observability.logging import safe_log
from app.shared.observability.reflection import ModelTokenUsage, ReflectionTelemetry


logger = logging.getLogger("orion.processing.embeddings")

EMBEDDING_DIMENSIONS = 1536
EMBEDDING_PROMPT_VERSION = "signal-embedding-v1"
MAX_EMBEDDING_BATCH = 128


class UnavailableSignalEmbeddingProvider:
    def embed(
        self,
        *,
        texts: tuple[str, ...],
        safety_identifier: str,
    ) -> tuple[tuple[float, ...], ...]:
        del texts, safety_identifier
        raise ProviderUnavailableError("signal embeddings are unavailable")


class OpenAISignalEmbeddingProvider:
    def __init__(
        self,
        client: Any,
        *,
        model: str,
        connect_timeout: float,
        response_timeout: float,
        total_timeout: float,
        telemetry: ReflectionTelemetry | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._telemetry = telemetry or ReflectionTelemetry()
        bounded_response = min(response_timeout, total_timeout)
        bounded_connect = min(connect_timeout, total_timeout)
        self._timeout = httpx.Timeout(
            total_timeout,
            connect=bounded_connect,
            read=bounded_response,
            write=bounded_response,
            pool=bounded_connect,
        )

    def embed(
        self,
        *,
        texts: tuple[str, ...],
        safety_identifier: str,
    ) -> tuple[tuple[float, ...], ...]:
        del safety_identifier  # Embeddings API has no safety_identifier parameter.
        if not texts:
            return ()
        if len(texts) > MAX_EMBEDDING_BATCH or any(not text.strip() for text in texts):
            raise ProviderResponseError("signal embedding input is invalid")
        client = self._client.with_options(max_retries=0, timeout=self._timeout)
        started = time.monotonic()
        usage = ModelTokenUsage()
        service_tier = "default"
        with self._telemetry.model_span(
            role="embedding",
            model_id=self._model,
            prompt_version=EMBEDDING_PROMPT_VERSION,
        ) as span:
            try:
                response = client.embeddings.create(
                    model=self._model,
                    input=list(texts),
                    dimensions=EMBEDDING_DIMENSIONS,
                    encoding_format="float",
                )
                raw_usage = getattr(response, "usage", None)
                usage = ModelTokenUsage(
                    input_tokens=_nonnegative_int(
                        getattr(raw_usage, "prompt_tokens", 0)
                    )
                )
                vectors = _validated_vectors(response, expected=len(texts))
            except ProviderResponseError:
                self._record_attempt(
                    span=span,
                    status="invalid",
                    started=started,
                    usage=usage,
                    retry_class="terminal",
                    service_tier=service_tier,
                )
                raise
            except Exception as exc:
                self._record_attempt(
                    span=span,
                    status="failed",
                    started=started,
                    usage=usage,
                    retry_class="retryable" if _retryable(exc) else "terminal",
                    service_tier=service_tier,
                )
                raise ProviderUnavailableError("signal embedding failed") from exc
            self._record_attempt(
                span=span,
                status="success",
                started=started,
                usage=usage,
                retry_class="none",
                service_tier=service_tier,
            )
        return vectors

    def _record_attempt(
        self,
        *,
        span: Any,
        status: str,
        started: float,
        usage: ModelTokenUsage,
        retry_class: str,
        service_tier: str,
    ) -> None:
        duration_ms = round((time.monotonic() - started) * 1000)
        self._telemetry.finish_model_span(
            span,
            status=status,
            duration_ms=duration_ms,
            input_tokens=usage.input_tokens,
            cached_input_tokens=0,
            cache_write_input_tokens=0,
            output_tokens=0,
            reasoning_output_tokens=0,
            retry_class=retry_class,
            service_tier=service_tier,
        )
        safe_log(
            logger,
            "signal_embedding_attempt",
            model_role="embedding",
            model_id=self._model,
            prompt_version=EMBEDDING_PROMPT_VERSION,
            status=status,
            duration_ms=duration_ms,
            input_tokens=usage.input_tokens,
            cached_input_tokens=0,
            cache_write_input_tokens=0,
            output_tokens=0,
            reasoning_output_tokens=0,
            retry_class=retry_class,
            service_tier=service_tier,
        )


def _validated_vectors(
    response: Any, *, expected: int
) -> tuple[tuple[float, ...], ...]:
    data = getattr(response, "data", None)
    if not isinstance(data, list) or len(data) != expected:
        raise ProviderResponseError("signal embedding response count is invalid")
    ordered: list[tuple[float, ...] | None] = [None] * expected
    for fallback_index, item in enumerate(data):
        index = getattr(item, "index", fallback_index)
        raw = getattr(item, "embedding", None)
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < expected
            or ordered[index] is not None
            or not isinstance(raw, list)
            or len(raw) != EMBEDDING_DIMENSIONS
            or any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                for value in raw
            )
        ):
            raise ProviderResponseError("signal embedding response is invalid")
        vector = tuple(float(value) for value in raw)
        if any(not math.isfinite(value) for value in vector):
            raise ProviderResponseError("signal embedding contains a non-finite value")
        ordered[index] = vector
    if any(item is None for item in ordered):
        raise ProviderResponseError("signal embedding response order is invalid")
    return tuple(item for item in ordered if item is not None)


def _nonnegative_int(value: object) -> int:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else 0
    )
