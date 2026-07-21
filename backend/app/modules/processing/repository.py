from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.jobs.types import JobClaim
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

    def load_pii_vault_for_update(
        self, session: Session, *, user_id: UUID
    ) -> tuple[dict | None, int]:
        row = session.execute(
            text(
                "SELECT mapping_envelope, mapping_version "
                "FROM public.get_user_pii_vault_for_update(:user_id)"
            ),
            {"user_id": user_id},
        ).one_or_none()
        if row is None:
            return None, 0
        envelope = row[0]
        if not isinstance(envelope, dict):
            raise RuntimeError("PII vault envelope is invalid")
        return envelope, int(row[1])

    def save_pii_vault(
        self,
        session: Session,
        *,
        user_id: UUID,
        mapping_envelope: dict,
        expected_version: int,
    ) -> int:
        return int(
            session.scalar(
                text(
                    "SELECT public.save_user_pii_vault("
                    ":user_id, CAST(:mapping_envelope AS jsonb), :expected_version)"
                ),
                {
                    "user_id": user_id,
                    "mapping_envelope": json.dumps(mapping_envelope),
                    "expected_version": expected_version,
                },
            )
        )

    def apply_job_extraction(
        self,
        session: Session,
        *,
        claim: JobClaim,
        worker_id: str,
        theme_config_id: UUID,
        extraction: EntryExtraction,
    ) -> None:
        session.execute(
            text(
                "SELECT public.apply_legacy_entry_processing_job("
                ":job_id, :worker_id, :claim_token, :config_id, :mode, "
                "CAST(:themes AS jsonb), CAST(:ideas AS jsonb), "
                "CAST(:memories AS jsonb), CAST(:reflections AS jsonb))"
            ),
            {
                "job_id": claim.job_id,
                "worker_id": worker_id,
                "claim_token": claim.claim_token,
                "config_id": theme_config_id,
                "mode": extraction.theme.mode,
                "themes": json.dumps(
                    [item.model_dump() for item in extraction.theme.themes]
                ),
                "ideas": json.dumps([item.model_dump() for item in extraction.ideas]),
                "memories": json.dumps(
                    [item.model_dump() for item in extraction.memories]
                ),
                "reflections": json.dumps(_reflection_rows(extraction)),
            },
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
