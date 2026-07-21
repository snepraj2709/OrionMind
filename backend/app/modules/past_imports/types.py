from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ImportClaim:
    import_id: UUID
    user_id: UUID
    entry_id: UUID
    processing_token: UUID
    envelope: dict
    theme_config_id: UUID
