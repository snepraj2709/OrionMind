from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.entries.types import PastEntryAcceptedData


class PastImportRepository:
    """Persists the historical-import audit row and its shared queue job atomically."""

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
        session.execute(
            text(
                "SELECT public.queue_past_entry_for_owner("
                ":user_id, :entry_id, CAST(:envelope AS jsonb), :entry_date, :config_id, "
                ":key_id, :fingerprint)"
            ),
            {
                "user_id": user_id,
                "entry_id": entry_id,
                "envelope": json.dumps(envelope),
                "entry_date": entry_date,
                "config_id": config_id,
                "key_id": fingerprint_key_id,
                "fingerprint": fingerprint,
            },
        )
        return PastEntryAcceptedData(entry_id=entry_id, entry_date=entry_date)
