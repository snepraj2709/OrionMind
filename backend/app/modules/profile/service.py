from __future__ import annotations

from uuid import UUID

from app.modules.profile.repository import ProfileRepository
from app.modules.profile.types import AccountAuthGateway, ProfileData
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.exceptions.domain import DomainError


class ProfileService:
    def __init__(
        self,
        *,
        repository: ProfileRepository,
        account_auth: AccountAuthGateway,
    ) -> None:
        self._repository = repository
        self._account_auth = account_auth

    def get_profile(self, *, user_id: UUID, unit_of_work_factory: UnitOfWorkFactory) -> ProfileData:
        with unit_of_work_factory.for_user(user_id) as work:
            profile = self._repository.get(work.session, user_id)
        if profile is None:
            raise RuntimeError("profile bootstrap invariant failed")
        return profile

    def update_profile(
        self,
        *,
        user_id: UUID,
        unit_of_work_factory: UnitOfWorkFactory,
        changes: dict[str, str],
    ) -> ProfileData:
        with unit_of_work_factory.for_user(user_id) as work:
            profile = self._repository.update(work.session, user_id, changes)
        if profile is None:
            raise RuntimeError("profile bootstrap invariant failed")
        return profile

    def delete_account(self, *, user_id: UUID, reauthentication_token: str) -> None:
        try:
            proof_user_id = self._account_auth.verify_user(reauthentication_token)
        except Exception as exc:
            raise DomainError(
                status_code=401,
                error_code="REAUTHENTICATION_REQUIRED",
                message="Fresh reauthentication is required to delete your account.",
            ) from exc
        if proof_user_id != user_id:
            raise DomainError(
                status_code=401,
                error_code="REAUTHENTICATION_REQUIRED",
                message="Fresh reauthentication is required to delete your account.",
            )
        try:
            self._account_auth.delete_user(user_id)
        except Exception as exc:
            raise DomainError(
                status_code=503,
                error_code="ACCOUNT_DELETION_UNAVAILABLE",
                message="Account deletion is temporarily unavailable. Your account remains active.",
                headers={"Retry-After": "30"},
            ) from exc
