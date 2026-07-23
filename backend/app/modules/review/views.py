from __future__ import annotations

from collections.abc import Sequence

from app.modules.review.schemas import (
    ReviewItem,
    ReviewItemsResponse,
    ReviewListQuery,
    ReviewPagination,
)


def review_items_response(
    *,
    items: Sequence[ReviewItem],
    query: ReviewListQuery,
    total: int,
) -> ReviewItemsResponse:
    return ReviewItemsResponse(
        items=list(items),
        pagination=ReviewPagination(
            page=query.page,
            page_size=query.page_size,
            total=total,
        ),
    )
