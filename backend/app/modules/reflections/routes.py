from fastapi import APIRouter

from app.modules.reflections.controller import (
    put_reflection_feedback,
    read_reflections,
    recalculate_reflections,
)
from app.modules.reflections.schemas import (
    FeedbackResult,
    RecalculationResponse,
    ReflectionResponse,
)
from app.shared.http.protected_route import ProtectedAPIRoute


router = APIRouter(route_class=ProtectedAPIRoute)
router.add_api_route(
    "/reflections",
    read_reflections,
    methods=["GET"],
    response_model=ReflectionResponse,
)
router.add_api_route(
    "/reflections/recalculate",
    recalculate_reflections,
    methods=["POST"],
    response_model=RecalculationResponse,
    status_code=202,
)
router.add_api_route(
    "/reflections/{snapshot_id}/insights/{insight_id}/feedback",
    put_reflection_feedback,
    methods=["PUT"],
    response_model=FeedbackResult,
)
