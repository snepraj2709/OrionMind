from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Query, Request, Response

from app.modules.entries.schemas import (
    EntryDetail,
    EntryDraftResponse,
    EntryDraftUpdate,
    EntryPage,
    TextEntryCreate,
)
from app.modules.entries.service import EntryService
from app.modules.entries.views import draft_response, entry_detail_response, entry_page_response
from app.shared.auth.context import AuthContext
from app.shared.auth.dependencies import get_auth_context
from app.shared.exceptions.domain import DomainError


def get_entry_service(request: Request) -> EntryService:
    service = getattr(request.app.state, "entry_service", None)
    if not isinstance(service, EntryService):
        raise RuntimeError("entry service is not configured")
    return service


def get_draft(
    auth: AuthContext = Depends(get_auth_context),
    service: EntryService = Depends(get_entry_service),
) -> EntryDraftResponse:
    return draft_response(
        *service.get_draft(user_id=auth.user_id, uow=auth.unit_of_work_factory)
    )


def save_draft(
    payload: EntryDraftUpdate,
    auth: AuthContext = Depends(get_auth_context),
    service: EntryService = Depends(get_entry_service),
) -> EntryDraftResponse:
    return draft_response(
        *service.save_draft(
            user_id=auth.user_id,
            content=payload.content,
            uow=auth.unit_of_work_factory,
        )
    )


def discard_draft(
    auth: AuthContext = Depends(get_auth_context),
    service: EntryService = Depends(get_entry_service),
) -> EntryDraftResponse:
    return draft_response(
        *service.discard_draft(user_id=auth.user_id, uow=auth.unit_of_work_factory)
    )


def create_text_entry(
    payload: TextEntryCreate,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    service: EntryService = Depends(get_entry_service),
) -> EntryDetail:
    if request.headers.get("Idempotency-Key") is not None:
        raise DomainError(
            status_code=422,
            error_code="VALIDATION_ERROR",
            message="The request is invalid.",
        )
    operation = service.submit_text(
        user_id=auth.user_id,
        content=payload.content,
        uow=auth.unit_of_work_factory,
    )
    response.status_code = operation.status_code
    return entry_detail_response(operation)


def list_entries(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context),
    service: EntryService = Depends(get_entry_service),
) -> EntryPage:
    result = service.list_entries(
        user_id=auth.user_id,
        page=page,
        page_size=page_size,
        uow=auth.unit_of_work_factory,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return entry_page_response(result)


def get_entry_detail(
    entry_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    service: EntryService = Depends(get_entry_service),
) -> EntryDetail:
    return entry_detail_response(
        service.get_detail(
            user_id=auth.user_id,
            entry_id=entry_id,
            uow=auth.unit_of_work_factory,
        )
    )


def retry_entry(
    entry_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    service: EntryService = Depends(get_entry_service),
) -> EntryDetail:
    return entry_detail_response(
        service.retry(
            user_id=auth.user_id,
            entry_id=entry_id,
            uow=auth.unit_of_work_factory,
        )
    )
