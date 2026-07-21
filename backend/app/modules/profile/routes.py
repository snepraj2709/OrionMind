from fastapi import APIRouter

from app.modules.profile.controller import delete_account, read_profile, update_profile
from app.modules.profile.schemas import ProfileResponse
from app.shared.http.protected_route import ProtectedAPIRoute


router = APIRouter(route_class=ProtectedAPIRoute)
router.add_api_route("/profile", read_profile, methods=["GET"], response_model=ProfileResponse)
router.add_api_route("/profile", update_profile, methods=["PATCH"], response_model=ProfileResponse)
router.add_api_route("/account", delete_account, methods=["DELETE"], status_code=204)
