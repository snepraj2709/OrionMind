from __future__ import annotations

import asyncio
from datetime import date
from uuid import UUID

from fastapi import Depends, Query, Request, Response

from app.modules.entries.schemas import (
    EntryDetail,
    EntryDraftResponse,
    EntryDraftUpdate,
    EntryPage,
    PastEntryAccepted,
    PastEntryCreate,
    TextEntryCreate,
)
from app.modules.entries.audio import (
    parse_audio_upload,
    remove_audio,
    validate_decodable_audio,
    validate_signature,
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


def create_past_entry(
    payload: PastEntryCreate,
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    service: EntryService = Depends(get_entry_service),
) -> PastEntryAccepted:
    accepted = service.create_past(
        user_id=auth.user_id,
        entry_date=payload.entry_date,
        content=payload.content,
        uow=auth.unit_of_work_factory,
    )
    status_url = f"/api/v1/entries/{accepted.entry_id}"
    response.headers["Location"] = status_url
    response.headers["Cache-Control"] = "private, no-store"
    return PastEntryAccepted(
        entry_id=accepted.entry_id,
        entry_date=accepted.entry_date,
        status_url=status_url,
    )


async def create_voice_entry(
    request: Request,
    response: Response,
    entry_date: date | None = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    service: EntryService = Depends(get_entry_service),
) -> EntryDetail:
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key is None:
        raise DomainError(422, "VALIDATION_ERROR", "The request is invalid.")
    preparation = await asyncio.to_thread(
        service.prepare_voice,
        user_id=auth.user_id,
        idempotency_key=idempotency_key,
        requested_date=entry_date,
        uow=auth.unit_of_work_factory,
    )
    if preparation.replay is not None:
        response.status_code = 200
        return entry_detail_response(preparation.replay)
    assert preparation.claim_token is not None
    parsed = None
    try:
        parsed = await parse_audio_upload(request)
        validate_signature(parsed.path, parsed.mime_type)
        await validate_decodable_audio(parsed.path)
        transcriber = getattr(request.app.state, "transcriber", None)
        if transcriber is None or not hasattr(transcriber, "transcribe"):
            raise RuntimeError("transcriber is not configured")
        transcript = await transcriber.transcribe(parsed.path, parsed.mime_type)
        if not isinstance(transcript, str) or not transcript.strip():
            raise DomainError(415, "UNSUPPORTED_AUDIO_FORMAT", "The audio format is not supported.")
        operation = await asyncio.to_thread(
            service.create_voice,
            user_id=auth.user_id,
            idempotency_key=idempotency_key,
            effective_date=preparation.effective_date,
            claim_token=preparation.claim_token,
            transcript=transcript,
            uow=auth.unit_of_work_factory,
        )
        response.status_code = operation.status_code
        return entry_detail_response(operation)
    except DomainError:
        await asyncio.to_thread(
            service.abandon_voice,
            user_id=auth.user_id,
            idempotency_key=idempotency_key,
            claim_token=preparation.claim_token,
            uow=auth.unit_of_work_factory,
        )
        raise
    except BaseException as exc:
        await asyncio.to_thread(
            service.abandon_voice,
            user_id=auth.user_id,
            idempotency_key=idempotency_key,
            claim_token=preparation.claim_token,
            uow=auth.unit_of_work_factory,
        )
        if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
            raise
        raise DomainError(
            502,
            "PROVIDER_UNAVAILABLE",
            "Could not complete this request right now.",
        ) from exc
    finally:
        remove_audio(parsed.path if parsed is not None else None)
