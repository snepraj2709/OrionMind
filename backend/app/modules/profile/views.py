from app.modules.profile.schemas import ProfileResponse
from app.modules.profile.types import ProfileData


def profile_response(profile: ProfileData) -> ProfileResponse:
    return ProfileResponse(display_name=profile.display_name, timezone=profile.timezone)
