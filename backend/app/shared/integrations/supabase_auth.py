from __future__ import annotations

from typing import Any

from app.shared.exceptions.domain import UnauthorizedError


class SupabaseTokenVerifier:
    def __init__(self, client: Any) -> None:
        self._client = client

    def verify_access_token(self, access_token: str) -> str:
        try:
            result = self._client.auth.get_user(access_token)
            user = getattr(result, "user", None)
            user_id = getattr(user, "id", None)
            if not user_id:
                raise UnauthorizedError()
            return str(user_id)
        except UnauthorizedError:
            raise
        except Exception as exc:
            raise UnauthorizedError() from exc


class UnavailableTokenVerifier:
    def verify_access_token(self, _access_token: str) -> str:
        raise UnauthorizedError()
