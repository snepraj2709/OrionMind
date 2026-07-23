from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Query, Request, Response
from pydantic import ValidationError

from app.modules.review.schemas import (
    REVIEW_PAGE_SIZE_DEFAULT,
    REVIEW_PAGE_SIZE_MAX,
    ReviewCategoryFilter,
    ReviewFeedbackRequest,
    ReviewItem,
    ReviewItemsResponse,
    ReviewListQuery,
)
from app.modules.review.service import NO_STORE_HEADERS, ReviewService
from app.modules.review.types import ReviewScope, ReviewStatus
from app.shared.auth.context import AuthContext
from app.shared.auth.dependencies import get_auth_context
from app.shared.exceptions.domain import DomainError


_LIST_QUERY_FIELDS = frozenset({"scope", "category", "status", "page", "page_size"})


def get_review_service(request: Request) -> ReviewService:
    service = getattr(request.app.state, "review_service", None)
    if not isinstance(service, ReviewService):
        raise RuntimeError("review service is not configured")
    return service


def list_review_items(
    request: Request,
    response: Response,
    scope: ReviewScope = Query(...),
    category: ReviewCategoryFilter = Query("all"),
    status: ReviewStatus = Query("pending"),
    page: int = Query(1, ge=1),
    page_size: int = Query(
        REVIEW_PAGE_SIZE_DEFAULT,
        ge=1,
        le=REVIEW_PAGE_SIZE_MAX,
    ),
    auth: AuthContext = Depends(get_auth_context),
    service: ReviewService = Depends(get_review_service),
) -> ReviewItemsResponse:
    response.headers.update(NO_STORE_HEADERS)
    if set(request.query_params) - _LIST_QUERY_FIELDS or any(
        len(request.query_params.getlist(field)) != 1
        for field in request.query_params
    ):
        raise DomainError(
            422,
            "VALIDATION_ERROR",
            "The request is invalid.",
            headers=NO_STORE_HEADERS,
        )
    try:
        query = ReviewListQuery(
            scope=scope,
            category=category,
            status=status,
            page=page,
            page_size=page_size,
        )
    except ValidationError as exc:
        raise DomainError(
            422,
            "VALIDATION_ERROR",
            "The request is invalid.",
            headers=NO_STORE_HEADERS,
        ) from exc
    return service.list_items(
        user_id=auth.user_id,
        query=query,
        uow=auth.unit_of_work_factory,
    )


def submit_review_feedback(
    review_item_id: UUID,
    payload: ReviewFeedbackRequest,
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    service: ReviewService = Depends(get_review_service),
) -> ReviewItem:
    response.headers.update(NO_STORE_HEADERS)
    return service.save_feedback(
        user_id=auth.user_id,
        item_id=review_item_id,
        payload=payload,
        uow=auth.unit_of_work_factory,
    )
