from fastapi import APIRouter

from app.modules.health.controller import get_health
from app.modules.health.schemas import HealthResponse


router = APIRouter()
router.add_api_route(
    "/health",
    get_health,
    methods=["GET"],
    response_model=HealthResponse,
    tags=["Operations"],
    operation_id="getHealth",
)
