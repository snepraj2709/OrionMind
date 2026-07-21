from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.shared.database.unit_of_work import UnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class AuthContext:
    user_id: UUID
    access_token: str = field(repr=False)
    unit_of_work_factory: UnitOfWorkFactory = field(repr=False)
