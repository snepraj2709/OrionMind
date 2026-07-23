from fastapi import APIRouter

from app.modules.review.controller import (
    list_review_items,
    submit_review_feedback,
)
from app.modules.review.schemas import ReviewItem, ReviewItemsResponse
from app.shared.http.protected_route import ProtectedAPIRoute


router = APIRouter(route_class=ProtectedAPIRoute)
router.add_api_route(
    "/review/items",
    list_review_items,
    methods=["GET"],
    response_model=ReviewItemsResponse,
)
router.add_api_route(
    "/review/items/{review_item_id}/feedback",
    submit_review_feedback,
    methods=["POST"],
    response_model=ReviewItem,
)
