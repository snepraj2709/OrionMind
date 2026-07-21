from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.profile.model import UserProfile
from app.modules.profile.types import ProfileData


class ProfileRepository:
    def get(self, session: Session, user_id: UUID) -> ProfileData | None:
        row = session.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
        return self._to_data(row)

    def update(
        self,
        session: Session,
        user_id: UUID,
        changes: Mapping[str, Any],
    ) -> ProfileData | None:
        row = session.scalar(
            select(UserProfile)
            .where(UserProfile.user_id == user_id)
            .with_for_update()
        )
        if row is None:
            return None
        for name in ("display_name", "timezone"):
            if name in changes:
                setattr(row, name, changes[name])
        session.flush()
        return self._to_data(row)

    @staticmethod
    def _to_data(row: UserProfile | None) -> ProfileData | None:
        if row is None:
            return None
        return ProfileData(display_name=row.display_name, timezone=row.timezone)
