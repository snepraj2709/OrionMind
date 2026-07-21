from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.past_imports.types import ImportClaim
from app.modules.processing.schemas import EntryExtraction


class PastImportRepository:
    def claim(self, session: Session, worker_id: str) -> ImportClaim | None:
        row = session.execute(
            text("SELECT * FROM public.claim_past_entry_import(:worker_id)"),
            {"worker_id": worker_id},
        ).mappings().one_or_none()
        if row is None:
            return None
        return ImportClaim(
            import_id=row["import_id"],
            user_id=row["user_id"],
            entry_id=row["entry_id"],
            processing_token=row["processing_token"],
            envelope=row["content_envelope"],
            theme_config_id=row["theme_config_id"],
        )

    def renew(self, session: Session, claim: ImportClaim, worker_id: str) -> bool:
        return bool(
            session.scalar(
                text(
                    "SELECT public.renew_past_entry_import("
                    ":import_id, :worker_id, :processing_token)"
                ),
                {
                    "import_id": claim.import_id,
                    "worker_id": worker_id,
                    "processing_token": claim.processing_token,
                },
            )
        )

    def recover(self, session: Session, stale_before: datetime) -> int:
        return int(
            session.scalar(
                text("SELECT public.recover_stale_past_entry_imports(:stale_before)"),
                {"stale_before": stale_before},
            )
            or 0
        )

    def complete(
        self,
        session: Session,
        *,
        claim: ImportClaim,
        worker_id: str,
        extraction: EntryExtraction,
    ) -> None:
        reflections = []
        for reflection_type in ("filled_energy", "drained_energy", "learned_about_self"):
            item = getattr(extraction.reflection, reflection_type)
            if item is not None:
                reflections.append(
                    {
                        "reflection_type": reflection_type,
                        "activity": item.activity,
                        "confidence_score": item.confidence,
                    }
                )
        session.execute(
            text(
                "SELECT public.apply_past_entry_extraction("
                ":import_id, :worker_id, :token, :config_id, :mode, CAST(:themes AS jsonb), "
                "CAST(:ideas AS jsonb), CAST(:memories AS jsonb), CAST(:reflections AS jsonb))"
            ),
            {
                "import_id": claim.import_id,
                "worker_id": worker_id,
                "token": claim.processing_token,
                "config_id": claim.theme_config_id,
                "mode": extraction.theme.mode,
                "themes": json.dumps([item.model_dump() for item in extraction.theme.themes]),
                "ideas": json.dumps([item.model_dump() for item in extraction.ideas]),
                "memories": json.dumps([item.model_dump() for item in extraction.memories]),
                "reflections": json.dumps(reflections),
            },
        )
