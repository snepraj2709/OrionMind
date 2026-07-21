from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.entries.types import PastEntryAcceptedData
from app.modules.past_imports.repository import PastImportRepository


class PastImportService:
    """Historical-import domain persistence; execution belongs to the shared worker."""

    def __init__(self, *, repository: PastImportRepository) -> None:
        self._repository = repository

    def queue(
        self,
        session: Session,
        *,
        user_id: UUID,
        entry_id: UUID,
        envelope: dict,
        entry_date: date,
        config_id: UUID,
        fingerprint_key_id: str,
        fingerprint: str,
    ) -> PastEntryAcceptedData:
        return self._repository.queue(
            session,
            user_id=user_id,
            entry_id=entry_id,
            envelope=envelope,
            entry_date=entry_date,
            config_id=config_id,
            fingerprint_key_id=fingerprint_key_id,
            fingerprint=fingerprint,
        )
