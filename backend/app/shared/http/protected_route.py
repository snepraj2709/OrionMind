from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute

from app.shared.auth.service import AuthenticationService


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
            return await original(request)

        return authenticated_handler
