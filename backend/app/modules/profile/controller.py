from __future__ import annotations

from fastapi import Depends, Request, Response, status

from app.modules.profile.schemas import (
    AccountDeletionRequest,
    ProfileResponse,
    ProfileUpdateRequest,
)
from app.modules.profile.service import ProfileService
from app.modules.profile.views import profile_response
from app.shared.auth.context import AuthContext
from app.shared.auth.dependencies import get_auth_context


def get_profile_service(request: Request) -> ProfileService:
    service = getattr(request.app.state, "profile_service", None)
    if not isinstance(service, ProfileService):
        raise RuntimeError("profile service is not configured")
    return service


def read_profile(
    auth: AuthContext = Depends(get_auth_context),
    service: ProfileService = Depends(get_profile_service),
) -> ProfileResponse:
    profile = service.get_profile(
        user_id=auth.user_id,
        unit_of_work_factory=auth.unit_of_work_factory,
    )
    return profile_response(profile)


def update_profile(
    payload: ProfileUpdateRequest,
    auth: AuthContext = Depends(get_auth_context),
    service: ProfileService = Depends(get_profile_service),
) -> ProfileResponse:
    profile = service.update_profile(
        user_id=auth.user_id,
        unit_of_work_factory=auth.unit_of_work_factory,
        changes=payload.model_dump(exclude_unset=True),
    )
    return profile_response(profile)


def delete_account(
    payload: AccountDeletionRequest,
    auth: AuthContext = Depends(get_auth_context),
    service: ProfileService = Depends(get_profile_service),
) -> Response:
    service.delete_account(
        user_id=auth.user_id,
        reauthentication_token=payload.reauthentication_token,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
