from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.modules.processing.prompts import build_extraction_messages
from app.modules.processing.schemas import ModelEntryExtraction
from app.modules.processing.source_segments import create_source_segments
from app.modules.processing.types import ThemeDefinition


logger = logging.getLogger("orion.processing.provider")


class ProviderUnavailableError(RuntimeError):
    pass


class UnavailableExtractionProvider:
    def extract(self, *, content: str, themes: tuple[ThemeDefinition, ...]) -> ModelEntryExtraction:
        raise ProviderUnavailableError("structured extraction is unavailable")


def _retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    return status in {408, 409, 429} or (isinstance(status, int) and status >= 500) or type(exc).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "RateLimitError",
        "InternalServerError",
    }


class OpenAIExtractionProvider:
    def __init__(
        self,
        client: Any,
        *,
        primary_model: str,
        fallback_model: str,
        connect_timeout: float,
        response_timeout: float,
        total_timeout: float,
    ) -> None:
        self._client = client
        self._models = (primary_model, fallback_model)
        self._timeout = httpx.Timeout(
            response_timeout,
            connect=connect_timeout,
            read=response_timeout,
            write=response_timeout,
            pool=connect_timeout,
        )
        self._total_timeout = total_timeout

    def extract(
        self,
        *,
        content: str,
        themes: tuple[ThemeDefinition, ...],
    ) -> ModelEntryExtraction:
        segments = create_source_segments(content)
        if not any(segment.selectable for segment in segments):
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
        messages = build_extraction_messages(content=content, themes=themes, segments=segments)
        client = self._client.with_options(max_retries=0, timeout=self._timeout)
        deadline = time.monotonic() + self._total_timeout
        for index, model in enumerate(self._models):
            if time.monotonic() >= deadline:
                raise ProviderUnavailableError("structured extraction deadline exceeded")
            role = "primary" if index == 0 else "fallback"
            started = time.monotonic()
            try:
                completion = client.beta.chat.completions.parse(
                    model=model,
                    messages=messages,
                    response_format=ModelEntryExtraction,
                )
                parsed = completion.choices[0].message.parsed
                result = (
                    parsed
                    if isinstance(parsed, ModelEntryExtraction)
                    else ModelEntryExtraction.model_validate(parsed)
                )
            except Exception as exc:
                logger.info(
                    "extraction_attempt role=%s outcome=failure error_class=%s duration_ms=%d",
                    role,
                    type(exc).__name__,
                    round((time.monotonic() - started) * 1000),
                )
                if index == 0 and _retryable(exc):
                    continue
                raise ProviderUnavailableError("structured extraction failed") from exc
            logger.info(
                "extraction_attempt role=%s outcome=success duration_ms=%d",
                role,
                round((time.monotonic() - started) * 1000),
            )
            return result
        raise ProviderUnavailableError("structured extraction failed")
