from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DomainError(Exception):
    status_code: int
    error_code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


class UnauthorizedError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            status_code=401,
            error_code="UNAUTHORIZED",
            message="Authentication is required.",
        )


class ServiceUnavailableError(DomainError):
    def __init__(self, *, retry_after: int = 60) -> None:
        super().__init__(
            status_code=503,
            error_code="SERVICE_UNAVAILABLE",
            message="The service is temporarily unavailable.",
            headers={"Retry-After": str(retry_after)},
        )
