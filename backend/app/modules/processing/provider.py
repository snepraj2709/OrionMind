from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import httpx
from pydantic import ValidationError

from app.modules.processing.prompts import (
    ENTRY_ANALYSIS_DEVELOPER_PROMPT,
    ENTRY_ANALYSIS_PROMPT_VERSION,
    build_entry_analysis_input,
)
from app.modules.processing.schemas import (
    DeterministicQualityFeatures,
    ModelEntryAnalysis,
)
from app.modules.processing.source_segments import create_source_segments
from app.modules.processing.types import ThemeDefinition
from app.shared.observability.logging import safe_log
from app.shared.observability.reflection import ReflectionTelemetry, token_counts


logger = logging.getLogger("orion.processing.provider")


class ProviderUnavailableError(RuntimeError):
    pass


class ProviderResponseError(ValueError):
    pass


class UnavailableEntryAnalysisProvider:
    def analyze(
        self,
        *,
        redacted_text: str,
        themes: tuple[ThemeDefinition, ...],
        deterministic_features: DeterministicQualityFeatures,
        entry_date: date,
        safety_identifier: str,
    ) -> ModelEntryAnalysis:
        raise ProviderUnavailableError("structured entry analysis is unavailable")


def _retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    return status in {408, 409, 429} or (isinstance(status, int) and status >= 500) or type(
        exc
    ).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "RateLimitError",
        "InternalServerError",
    }


def provider_failure_is_retryable(exc: ProviderUnavailableError) -> bool:
    cause = exc.__cause__
    if cause is None:
        return True
    return _retryable(cause)


class OpenAIEntryAnalysisProvider:
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

    def analyze(
        self,
        *,
        redacted_text: str,
        themes: tuple[ThemeDefinition, ...],
        deterministic_features: DeterministicQualityFeatures,
        entry_date: date,
        safety_identifier: str,
    ) -> ModelEntryAnalysis:
        segments = create_source_segments(redacted_text)
        payload = build_entry_analysis_input(
            redacted_text=redacted_text,
            themes=themes,
            segments=segments,
            deterministic_features=deterministic_features,
            entry_date=entry_date,
        )
        client = self._client.with_options(max_retries=0, timeout=self._timeout)
        started = time.monotonic()
        input_tokens = 0
        output_tokens = 0
        with self._telemetry.model_span(
            role="entry_analysis",
            model_id=self._model,
            prompt_version=ENTRY_ANALYSIS_PROMPT_VERSION,
        ) as span:
            try:
                response = client.responses.parse(
                    model=self._model,
                    instructions=ENTRY_ANALYSIS_DEVELOPER_PROMPT,
                    input=payload,
                    text_format=ModelEntryAnalysis,
                    store=False,
                    truncation="disabled",
                    safety_identifier=safety_identifier,
                )
                input_tokens, output_tokens = token_counts(response)
                if getattr(response, "status", None) == "incomplete":
                    raise ProviderResponseError("entry analysis response is incomplete")
                parsed = getattr(response, "output_parsed", None)
                if parsed is None:
                    raise ProviderResponseError("entry analysis response is unavailable")
                result = (
                    parsed
                    if isinstance(parsed, ModelEntryAnalysis)
                    else ModelEntryAnalysis.model_validate(parsed)
                )
            except (ProviderResponseError, ValidationError) as exc:
                self._record_attempt(
                    span=span,
                    status="invalid",
                    started=started,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    retry_class="terminal",
                )
                if isinstance(exc, ValidationError):
                    raise ProviderResponseError("entry analysis schema is invalid") from exc
                raise
            except Exception as exc:
                self._record_attempt(
                    span=span,
                    status="failed",
                    started=started,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    retry_class="retryable" if _retryable(exc) else "terminal",
                )
                raise ProviderUnavailableError("structured entry analysis failed") from exc
            self._record_attempt(
                span=span,
                status="success",
                started=started,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                retry_class="none",
            )
        return result

    def _record_attempt(
        self,
        *,
        span: Any,
        status: str,
        started: float,
        input_tokens: int,
        output_tokens: int,
        retry_class: str,
    ) -> None:
        duration_ms = round((time.monotonic() - started) * 1000)
        self._telemetry.finish_model_span(
            span,
            status=status,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            retry_class=retry_class,
        )
        safe_log(
            logger,
            "entry_analysis_attempt",
            model_role="entry_analysis",
            model_id=self._model,
            prompt_version=ENTRY_ANALYSIS_PROMPT_VERSION,
            status=status,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            retry_class=retry_class,
        )
