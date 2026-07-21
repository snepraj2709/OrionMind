from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.modules.reflection_engine.prompts import (
    REFLECTION_CRITIC_DEVELOPER_PROMPT,
    REFLECTION_SYNTHESIS_DEVELOPER_PROMPT,
)
from app.modules.reflection_engine.schemas import (
    ReflectionCriticOutput,
    ReflectionSynthesisOutput,
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


def _retryable(exc: Exception) -> bool:
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
    ) -> None:
        self._client = client
        self._synthesis_model = synthesis_model
        self._critic_model = critic_model
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
        instructions: str,
        payload: str,
        output_model: Any,
        safety_identifier: str,
    ):
        client = self._client.with_options(max_retries=0, timeout=self._timeout)
        started = time.monotonic()
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
            logger.info(
                "reflection_model_attempt role=%s model=%s outcome=invalid duration_ms=%d",
                role,
                model,
                round((time.monotonic() - started) * 1000),
            )
            if isinstance(exc, ValidationError):
                raise ReflectionProviderResponseError(
                    f"reflection {role} schema is invalid"
                ) from exc
            raise
        except Exception as exc:
            logger.info(
                "reflection_model_attempt role=%s model=%s outcome=failure error_class=%s duration_ms=%d",
                role,
                model,
                type(exc).__name__,
                round((time.monotonic() - started) * 1000),
            )
            raise ReflectionProviderUnavailableError(
                f"structured reflection {role} failed"
            ) from exc
        logger.info(
            "reflection_model_attempt role=%s model=%s outcome=success duration_ms=%d",
            role,
            model,
            round((time.monotonic() - started) * 1000),
        )
        return result
