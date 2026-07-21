from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.shared.auth.context import AuthContext
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.exceptions.domain import UnauthorizedError


class TokenVerifier(Protocol):
    def verify_access_token(self, access_token: str) -> str: ...


@dataclass(slots=True)
class AuthenticationService:
    verifier: TokenVerifier
    unit_of_work_factory: UnitOfWorkFactory

    def authenticate(self, authorization_header: str | None) -> AuthContext:
        token = self._extract_bearer(authorization_header)
        try:
            raw_user_id = self.verifier.verify_access_token(token)
            user_id = UUID(str(raw_user_id))
        except UnauthorizedError:
            raise
        except Exception as exc:
            raise UnauthorizedError() from exc
        return AuthContext(
            user_id=user_id,
            access_token=token,
            unit_of_work_factory=self.unit_of_work_factory,
        )

    @staticmethod
    def _extract_bearer(value: str | None) -> str:
        if value is None:
            raise UnauthorizedError()
        scheme, separator, token = value.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token or token != token.strip():
            raise UnauthorizedError()
        return token
