from fastapi import APIRouter, Depends

from app.shared.auth.dependencies import get_auth_context
from app.shared.http.protected_route import ProtectedAPIRoute


router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(get_auth_context)],
    route_class=ProtectedAPIRoute,
)
