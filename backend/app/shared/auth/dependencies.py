from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.shared.auth.context import AuthContext
from app.shared.exceptions.domain import UnauthorizedError


bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="bearerAuth",
    description="Supabase access token; never a service-role key.",
)


async def get_auth_context(
    request: Request,
    _credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthContext:
    context = getattr(request.state, "auth_context", None)
    if not isinstance(context, AuthContext):
        raise UnauthorizedError()
    return context
