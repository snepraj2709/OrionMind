from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute

from app.shared.auth.service import AuthenticationService
from app.shared.exceptions.domain import DomainError
from app.shared.http.rate_limits import ProcessRateLimiter, request_class


class ProtectedAPIRoute(APIRoute):
    """Authenticate a matched product route before FastAPI consumes its body."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def authenticated_handler(request: Request) -> Response:
            service = getattr(request.app.state, "authentication_service", None)
            if not isinstance(service, AuthenticationService):
                raise RuntimeError("authentication service is not configured")
            request.state.auth_context = service.authenticate(
                request.headers.get("Authorization")
            )
            classification = request_class(request)
            limiter = getattr(request.app.state, "rate_limiter", None)
            if classification is not None:
                if not isinstance(limiter, ProcessRateLimiter):
                    raise RuntimeError("rate limiter is not configured")
                rule, scope = classification
                retry_after = limiter.check(rule, scope)
                if retry_after is not None:
                    raise DomainError(
                        429,
                        "RATE_LIMITED",
                        "Too many requests. Try again later.",
                        details={"retry_after_seconds": retry_after},
                        headers={"Retry-After": str(retry_after)},
                    )
            return await original(request)

        return authenticated_handler
