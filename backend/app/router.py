from fastapi import APIRouter, Depends

from app.modules.entries.routes import router as entries_router
from app.modules.profile.routes import router as profile_router
from app.modules.reflections.routes import router as reflections_router
from app.modules.review.routes import router as review_router
from app.shared.auth.dependencies import get_auth_context
from app.shared.http.protected_route import ProtectedAPIRoute


router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(get_auth_context)],
    route_class=ProtectedAPIRoute,
)
router.include_router(profile_router)
router.include_router(entries_router)
router.include_router(review_router)
router.include_router(reflections_router)
