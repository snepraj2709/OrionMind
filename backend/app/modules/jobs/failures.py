from __future__ import annotations

from app.modules.processing.provider import (
    ProviderResponseError,
    ProviderUnavailableError,
    provider_failure_is_retryable,
)
from app.modules.processing.service import (
    AnalysisValidationError,
    PrivacyValidationError,
)
from app.modules.reflection_engine.provider import (
    ReflectionProviderResponseError,
    ReflectionProviderUnavailableError,
    reflection_provider_failure_is_retryable,
)
from app.modules.reflection_engine.service import SnapshotValidationError
from app.shared.security.encryption import ContentUnavailableError


def classify_failure(
    exc: Exception,
    *,
    synthesis: bool = False,
) -> tuple[str, bool]:
    if isinstance(exc, ContentUnavailableError):
        return "ENTRY_CONTENT_UNAVAILABLE", False
    if isinstance(exc, ProviderUnavailableError):
        return "PROVIDER_UNAVAILABLE", provider_failure_is_retryable(exc)
    if isinstance(exc, ReflectionProviderUnavailableError):
        return (
            "REFLECTION_PROVIDER_UNAVAILABLE",
            reflection_provider_failure_is_retryable(exc),
        )
    if isinstance(exc, ReflectionProviderResponseError | SnapshotValidationError):
        return "INVALID_SYNTHESIS", False
    if synthesis and isinstance(exc, ValueError):
        return "INVALID_SYNTHESIS", False
    if isinstance(exc, ProviderResponseError | AnalysisValidationError):
        return "INVALID_ANALYSIS", False
    if isinstance(exc, PrivacyValidationError):
        return "PRIVACY_VALIDATION_FAILED", False
    if isinstance(exc, ValueError):
        return "INVALID_ANALYSIS", False
    return "PROCESSING_FAILED", False
