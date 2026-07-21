from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.processing.schemas import EntryExtraction


class ProcessingRepository:
    def fixed_themes(self, session: Session, config_id: UUID) -> tuple[tuple[str, str], ...]:
        rows = session.execute(
            text(
                "SELECT theme_key, name FROM public.themes "
                "WHERE theme_config_id = :config_id ORDER BY sort_order"
            ),
            {"config_id": config_id},
        ).all()
        return tuple((str(row[0]), str(row[1])) for row in rows)

    def apply_extraction(
        self,
        session: Session,
        *,
        user_id: UUID,
        entry_id: UUID,
        processing_token: UUID,
        theme_config_id: UUID,
        extraction: EntryExtraction,
        past_import: bool,
    ) -> None:
        session.execute(
            text(
                "SELECT public.apply_entry_extraction_for_owner("
                ":user_id, :entry_id, :processing_token, :config_id, :mode, "
                "CAST(:themes AS jsonb), CAST(:ideas AS jsonb), CAST(:memories AS jsonb), "
                "CAST(:reflections AS jsonb), :past_import)"
            ),
            {
                "user_id": user_id,
                "entry_id": entry_id,
                "processing_token": processing_token,
                "config_id": theme_config_id,
                "mode": extraction.theme.mode,
                "themes": json.dumps([item.model_dump() for item in extraction.theme.themes]),
                "ideas": json.dumps([item.model_dump() for item in extraction.ideas]),
                "memories": json.dumps([item.model_dump() for item in extraction.memories]),
                "reflections": json.dumps(_reflection_rows(extraction)),
                "past_import": past_import,
            },
        )

    def mark_failed(
        self,
        session: Session,
        *,
        user_id: UUID,
        entry_id: UUID,
        processing_token: UUID,
        error_code: str,
    ) -> bool:
        return bool(
            session.scalar(
                text(
                    "SELECT public.mark_entry_processing_failed_for_owner("
                    ":user_id, :entry_id, :processing_token, :error_code)"
                ),
                {
                    "user_id": user_id,
                    "entry_id": entry_id,
                    "processing_token": processing_token,
                    "error_code": error_code,
                },
            )
        )


def _reflection_rows(extraction: EntryExtraction) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for reflection_type in ("filled_energy", "drained_energy", "learned_about_self"):
        item = getattr(extraction.reflection, reflection_type)
        if item is not None:
            rows.append(
                {
                    "reflection_type": reflection_type,
                    "activity": item.activity,
                    "confidence_score": item.confidence,
                }
            )
    return rows
