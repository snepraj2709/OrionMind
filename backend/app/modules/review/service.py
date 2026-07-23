from __future__ import annotations

from collections.abc import Collection
from typing import cast
from uuid import UUID

from app.modules.reflections.repository import ReflectionsRepository
from app.modules.reflections.schemas import FeedbackResponse
from app.modules.review.repository import (
    ReviewItemNotFoundError,
    ReviewItemStaleError,
    ReviewRepository,
    ReviewRepositoryDataError,
)
from app.modules.review.schemas import (
    PatternReviewItem,
    ReviewFeedbackRequest,
    ReviewItem,
    ReviewItemsResponse,
    ReviewListQuery,
)
from app.modules.review.types import PatternVerdict
from app.modules.review.views import review_items_response
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.exceptions.domain import DomainError


NO_STORE_HEADERS = {"Cache-Control": "private, no-store"}
UNAVAILABLE_HEADERS = {**NO_STORE_HEADERS, "Retry-After": "60"}


class ReviewService:
    def __init__(
        self,
        *,
        repository: ReviewRepository,
        recalculation_repository: ReflectionsRepository,
        enabled: bool,
        allowed_user_ids: Collection[UUID],
    ) -> None:
        self._repository = repository
        self._recalculation_repository = recalculation_repository
        self._enabled = enabled
        self._allowed_user_ids = frozenset(allowed_user_ids)

    def list_items(
        self,
        *,
        user_id: UUID,
        query: ReviewListQuery,
        uow: UnitOfWorkFactory,
    ) -> ReviewItemsResponse:
        self._require_enabled(user_id)
        try:
            with uow.for_user(user_id) as work:
                total = self._repository.count_items(
                    work.session,
                    user_id=user_id,
                    scope=query.scope,
                    category=query.category,
                    status=query.status,
                )
                items = self._repository.list_items(
                    work.session,
                    user_id=user_id,
                    scope=query.scope,
                    category=query.category,
                    status=query.status,
                    page=query.page,
                    page_size=query.page_size,
                )
        except ReviewRepositoryDataError as exc:
            raise DomainError(
                500,
                "REVIEW_DATA_UNAVAILABLE",
                "Review data is temporarily unavailable.",
                headers=NO_STORE_HEADERS,
            ) from exc
        return review_items_response(items=items, query=query, total=total)

    def save_feedback(
        self,
        *,
        user_id: UUID,
        item_id: UUID,
        payload: ReviewFeedbackRequest,
        uow: UnitOfWorkFactory,
    ) -> ReviewItem:
        self._require_enabled(user_id)
        try:
            with uow.for_user(user_id) as work:
                existing = self._repository.get_by_owner(
                    work.session,
                    user_id=user_id,
                    item_id=item_id,
                )
                if existing is None:
                    raise ReviewItemNotFoundError
                try:
                    payload.decision_for_scope(existing.scope)
                except ValueError as exc:
                    raise DomainError(
                        422,
                        "VALIDATION_ERROR",
                        "The request is invalid.",
                        headers=NO_STORE_HEADERS,
                    ) from exc
                saved = self._repository.put_feedback(
                    work.session,
                    user_id=user_id,
                    item_id=item_id,
                    verdict=payload.verdict,
                    corrected_statement=payload.corrected_statement,
                    note=payload.note,
                )
                item = self._repository.get_by_owner(
                    work.session,
                    user_id=user_id,
                    item_id=item_id,
                )
                if item is None:
                    raise ReviewItemStaleError
        except ReviewItemNotFoundError as exc:
            raise DomainError(
                404,
                "REVIEW_ITEM_NOT_FOUND",
                "The review item was not found.",
                headers=NO_STORE_HEADERS,
            ) from exc
        except ReviewItemStaleError as exc:
            raise DomainError(
                409,
                "REVIEW_ITEM_STALE",
                "The review item can no longer accept feedback.",
                headers=NO_STORE_HEADERS,
            ) from exc
        except ReviewRepositoryDataError as exc:
            raise DomainError(
                500,
                "REVIEW_DATA_UNAVAILABLE",
                "Review data is temporarily unavailable.",
                headers=NO_STORE_HEADERS,
            ) from exc

        if saved.changed:
            self._request_recalculation(user_id=user_id, uow=uow)
        return item

    def save_legacy_pattern_feedback(
        self,
        *,
        user_id: UUID,
        snapshot_id: UUID,
        insight_id: UUID,
        response: FeedbackResponse,
        uow: UnitOfWorkFactory,
    ) -> PatternReviewItem:
        self._require_enabled(user_id)
        try:
            with uow.for_user(user_id) as work:
                item_id = self._repository.pattern_item_id_for_snapshot_insight(
                    work.session,
                    user_id=user_id,
                    snapshot_id=snapshot_id,
                    insight_id=insight_id,
                )
        except ReviewRepositoryDataError as exc:
            raise DomainError(
                500,
                "REVIEW_DATA_UNAVAILABLE",
                "Review data is temporarily unavailable.",
                headers=NO_STORE_HEADERS,
            ) from exc
        if item_id is None:
            raise DomainError(
                404,
                "NOT_FOUND",
                "The requested resource was not found.",
                headers=NO_STORE_HEADERS,
            )
        verdict = {
            "resonates": "resonates",
            "partly": "partly_true",
            "rejected": "not_true",
        }[response]
        try:
            item = self.save_feedback(
                user_id=user_id,
                item_id=item_id,
                payload=ReviewFeedbackRequest(
                    verdict=cast(PatternVerdict, verdict)
                ),
                uow=uow,
            )
        except DomainError as exc:
            if exc.error_code not in {
                "REVIEW_ITEM_NOT_FOUND",
                "REVIEW_ITEM_STALE",
            }:
                raise
            raise DomainError(
                404,
                "NOT_FOUND",
                "The requested resource was not found.",
                headers=NO_STORE_HEADERS,
            ) from exc
        if not isinstance(item, PatternReviewItem):
            raise DomainError(
                404,
                "NOT_FOUND",
                "The requested resource was not found.",
                headers=NO_STORE_HEADERS,
            )
        return item

    def _request_recalculation(
        self,
        *,
        user_id: UUID,
        uow: UnitOfWorkFactory,
    ) -> None:
        try:
            with uow.for_user(user_id) as work:
                result = self._recalculation_repository.request_recalculation(
                    work.session,
                    user_id=user_id,
                )
            if result.outcome == "unavailable":
                raise RuntimeError("reflection recalculation was not accepted")
        except Exception as exc:
            raise DomainError(
                503,
                "REFLECTION_RECALCULATION_UNAVAILABLE",
                "Reflection recalculation is temporarily unavailable.",
                headers=UNAVAILABLE_HEADERS,
            ) from exc

    def _require_enabled(self, user_id: UUID) -> None:
        if not self._enabled or user_id not in self._allowed_user_ids:
            raise DomainError(
                503,
                "SERVICE_UNAVAILABLE",
                "The service is temporarily unavailable.",
                headers=UNAVAILABLE_HEADERS,
            )
