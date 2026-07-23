from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Query, Request, Response

from app.modules.reflections.schemas import (
    FeedbackRequest,
    FeedbackResult,
    RecalculationResponse,
    ReflectionRange,
    ReflectionResponse,
)
from app.modules.reflections.service import NO_STORE_HEADERS, ReflectionsService
from app.modules.reflections.types import FeedbackCommand, ReflectionQuery
from app.shared.auth.context import AuthContext
from app.shared.auth.dependencies import get_auth_context


def get_reflections_service(request: Request) -> ReflectionsService:
    service = getattr(request.app.state, "reflections_service", None)
    if not isinstance(service, ReflectionsService):
        raise RuntimeError("reflections service is not configured")
    return service


def read_reflections(
    request: Request,
    response: Response,
    range: ReflectionRange = Query(...),
    auth: AuthContext = Depends(get_auth_context),
    service: ReflectionsService = Depends(get_reflections_service),
) -> ReflectionResponse:
    response.headers.update(NO_STORE_HEADERS)
    if set(request.query_params) != {"range"}:
        from app.shared.exceptions.domain import DomainError

        raise DomainError(
            422,
            "VALIDATION_ERROR",
            "The request is invalid.",
            headers=NO_STORE_HEADERS,
        )
    return service.read(
        query=ReflectionQuery(user_id=auth.user_id, range=range),
        uow=auth.unit_of_work_factory,
    )


async def recalculate_reflections(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    service: ReflectionsService = Depends(get_reflections_service),
) -> RecalculationResponse:
    response.headers.update(NO_STORE_HEADERS)
    if await request.body():
        from app.shared.exceptions.domain import DomainError

        raise DomainError(
            422,
            "VALIDATION_ERROR",
            "The request is invalid.",
            headers=NO_STORE_HEADERS,
        )
    return service.request_recalculation(
        user_id=auth.user_id,
        uow=auth.unit_of_work_factory,
    )


def put_reflection_feedback(
    snapshot_id: UUID,
    insight_id: UUID,
    payload: FeedbackRequest,
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    service: ReflectionsService = Depends(get_reflections_service),
) -> FeedbackResult:
    response.headers.update(NO_STORE_HEADERS)
    return service.save_feedback(
        command=FeedbackCommand(
            user_id=auth.user_id,
            snapshot_id=snapshot_id,
            insight_id=insight_id,
            response=payload.response,
        ),
        uow=auth.unit_of_work_factory,
    )
