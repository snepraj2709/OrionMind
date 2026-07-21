from app.modules.health.schemas import HealthResponse


async def get_health() -> HealthResponse:
    return HealthResponse()
