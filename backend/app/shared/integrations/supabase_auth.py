from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.profile.types import AccountDeletionOutcome
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


def _field(source: Any, name: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _is_missing_identity(exc: Exception) -> bool:
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    code = str(getattr(exc, "code", "")).lower()
    return status == 404 or code in {"user_not_found", "not_found"}


class SupabaseAccountAuthGateway:
    def __init__(self, verification_client: Any, administration_client: Any) -> None:
        self._verification_client = verification_client
        self._administration_client = administration_client

    def verify_user(self, proof_token: str) -> UUID:
        response = self._verification_client.auth.get_user(proof_token)
        return UUID(str(_field(_field(response, "user"), "id", "")))

    def delete_user(self, user_id: UUID) -> AccountDeletionOutcome:
        try:
            self._administration_client.auth.admin.delete_user(str(user_id))
        except Exception as exc:
            if _is_missing_identity(exc):
                return AccountDeletionOutcome.ALREADY_MISSING
            raise
        return AccountDeletionOutcome.DELETED


class UnavailableAccountAuthGateway:
    def verify_user(self, _proof_token: str) -> UUID:
        raise RuntimeError("account auth is unavailable")

    def delete_user(self, _user_id: UUID) -> AccountDeletionOutcome:
        raise RuntimeError("account auth is unavailable")
