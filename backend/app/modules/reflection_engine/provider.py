from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.modules.reflection_engine.prompts import (
    REFLECTION_CRITIC_DEVELOPER_PROMPT,
    REFLECTION_CRITIC_PROMPT_VERSION,
    REFLECTION_SYNTHESIS_DEVELOPER_PROMPT,
    REFLECTION_SYNTHESIS_PROMPT_VERSION,
)
from app.modules.reflection_engine.schemas import (
    ReflectionCriticOutput,
    ReflectionSynthesisOutput,
)
from app.shared.observability.logging import safe_log
from app.shared.observability.reflection import (
    ModelTokenUsage,
    ReflectionTelemetry,
    token_usage,
)


logger = logging.getLogger("orion.reflection.provider")


class ReflectionProviderUnavailableError(RuntimeError):
    pass


class ReflectionProviderResponseError(ValueError):
    pass


class UnavailableReflectionProvider:
    def synthesize(
        self, *, payload: str, safety_identifier: str
    ) -> ReflectionSynthesisOutput:
        raise ReflectionProviderUnavailableError("reflection synthesis is unavailable")

    def critique(
        self, *, payload: str, safety_identifier: str
    ) -> ReflectionCriticOutput:
        raise ReflectionProviderUnavailableError("reflection critic is unavailable")


def _retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    return (
        status in {408, 409, 429}
        or (isinstance(status, int) and status >= 500)
        or type(exc).__name__
        in {
            "APIConnectionError",
            "APITimeoutError",
            "RateLimitError",
            "InternalServerError",
        }
    )


def reflection_provider_failure_is_retryable(
    exc: ReflectionProviderUnavailableError,
) -> bool:
    cause = exc.__cause__
    if cause is None:
        return True
    return _retryable(cause)


class OpenAIReflectionProvider:
    def __init__(
        self,
        client: Any,
        *,
        synthesis_model: str,
        critic_model: str,
        connect_timeout: float,
        response_timeout: float,
        total_timeout: float,
        telemetry: ReflectionTelemetry | None = None,
    ) -> None:
        self._client = client
        self._synthesis_model = synthesis_model
        self._critic_model = critic_model
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

    def synthesize(
        self, *, payload: str, safety_identifier: str
    ) -> ReflectionSynthesisOutput:
        return self._parse(
            role="synthesis",
            model=self._synthesis_model,
            prompt_version=REFLECTION_SYNTHESIS_PROMPT_VERSION,
            instructions=REFLECTION_SYNTHESIS_DEVELOPER_PROMPT,
            payload=payload,
            output_model=ReflectionSynthesisOutput,
            safety_identifier=safety_identifier,
        )

    def critique(
        self, *, payload: str, safety_identifier: str
    ) -> ReflectionCriticOutput:
        return self._parse(
            role="critic",
            model=self._critic_model,
            prompt_version=REFLECTION_CRITIC_PROMPT_VERSION,
            instructions=REFLECTION_CRITIC_DEVELOPER_PROMPT,
            payload=payload,
            output_model=ReflectionCriticOutput,
            safety_identifier=safety_identifier,
        )

    def _parse(
        self,
        *,
        role: str,
        model: str,
        prompt_version: str,
        instructions: str,
        payload: str,
        output_model: Any,
        safety_identifier: str,
    ) -> Any:
        client = self._client.with_options(max_retries=0, timeout=self._timeout)
        started = time.monotonic()
        usage = ModelTokenUsage()
        service_tier = "unknown"
        model_role = "synthesis" if role == "synthesis" else "critic"
        with self._telemetry.model_span(
            role=model_role,
            model_id=model,
            prompt_version=prompt_version,
        ) as span:
            try:
                response = client.responses.parse(
                    model=model,
                    instructions=instructions,
                    input=payload,
                    text_format=output_model,
                    store=False,
                    truncation="disabled",
                    safety_identifier=safety_identifier,
                )
                usage = token_usage(response)
                service_tier = str(
                    getattr(response, "service_tier", None) or "unknown"
                )
                if getattr(response, "status", None) == "incomplete":
                    raise ReflectionProviderResponseError(
                        f"reflection {role} response is incomplete"
                    )
                parsed = getattr(response, "output_parsed", None)
                if parsed is None:
                    raise ReflectionProviderResponseError(
                        f"reflection {role} response is unavailable"
                    )
                result = (
                    parsed
                    if isinstance(parsed, output_model)
                    else output_model.model_validate(parsed)
                )
            except (ReflectionProviderResponseError, ValidationError) as exc:
                self._record_attempt(
                    span=span,
                    role=model_role,
                    model=model,
                    prompt_version=prompt_version,
                    status="invalid",
                    started=started,
                    usage=usage,
                    retry_class="terminal",
                    service_tier=service_tier,
                )
                if isinstance(exc, ValidationError):
                    raise ReflectionProviderResponseError(
                        f"reflection {role} schema is invalid"
                    ) from exc
                raise
            except Exception as exc:
                self._record_attempt(
                    span=span,
                    role=model_role,
                    model=model,
                    prompt_version=prompt_version,
                    status="failed",
                    started=started,
                    usage=usage,
                    retry_class="retryable" if _retryable(exc) else "terminal",
                    service_tier=service_tier,
                )
                raise ReflectionProviderUnavailableError(
                    f"structured reflection {role} failed"
                ) from exc
            self._record_attempt(
                span=span,
                role=model_role,
                model=model,
                prompt_version=prompt_version,
                status="success",
                started=started,
                usage=usage,
                retry_class="none",
                service_tier=service_tier,
            )
        return result

    def _record_attempt(
        self,
        *,
        span: Any,
        role: str,
        model: str,
        prompt_version: str,
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
            cached_input_tokens=usage.cached_input_tokens,
            cache_write_input_tokens=usage.cache_write_input_tokens,
            output_tokens=usage.output_tokens,
            reasoning_output_tokens=usage.reasoning_output_tokens,
            retry_class=retry_class,
            service_tier=service_tier,
        )
        safe_log(
            logger,
            "reflection_model_attempt",
            model_role=role,
            model_id=model,
            prompt_version=prompt_version,
            status=status,
            duration_ms=duration_ms,
            input_tokens=usage.input_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            cache_write_input_tokens=usage.cache_write_input_tokens,
            output_tokens=usage.output_tokens,
            reasoning_output_tokens=usage.reasoning_output_tokens,
            retry_class=retry_class,
            service_tier=service_tier,
        )
