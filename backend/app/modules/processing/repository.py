from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.jobs.types import JobClaim
from app.modules.processing.quality import QualityHistory
from app.modules.processing.schemas import EntryExtraction


class StaleAnalysisClaimError(RuntimeError):
    pass


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

    def recent_quality_history(
        self,
        session: Session,
        *,
        user_id: UUID,
        entry_id: UUID,
        entry_date: date,
    ) -> tuple[QualityHistory, ...]:
        rows = session.execute(
            text(
                "SELECT duplicate_cluster_key, ngram_sketch, eligibility "
                "FROM public.get_entry_quality_history("
                ":user_id, :entry_id, :entry_date)"
            ),
            {
                "user_id": user_id,
                "entry_id": entry_id,
                "entry_date": entry_date,
            },
        ).all()
        return tuple(
            QualityHistory(
                duplicate_cluster_key=(str(row[0]) if row[0] is not None else None),
                ngram_sketch=tuple(str(value) for value in row[1]),
                eligibility=str(row[2]),  # type: ignore[arg-type]
            )
            for row in rows
        )

    def apply_combined_job_analysis(
        self,
        session: Session,
        *,
        claim: JobClaim,
        worker_id: str,
        theme_config_id: UUID,
        extraction: EntryExtraction,
        analysis: dict[str, object],
        signals: tuple[dict[str, object], ...],
        apply_legacy: bool,
    ) -> int:
        try:
            source_version = int(
                session.scalar(
                    text(
                        "SELECT public.apply_combined_entry_processing_job("
                        ":job_id, :worker_id, :claim_token, :config_id, :mode, "
                        "CAST(:themes AS jsonb), CAST(:ideas AS jsonb), "
                        "CAST(:memories AS jsonb), CAST(:reflections AS jsonb), "
                        "CAST(:analysis AS jsonb), CAST(:signals AS jsonb), :apply_legacy)"
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
                        "ideas": json.dumps(
                            [item.model_dump() for item in extraction.ideas]
                        ),
                        "memories": json.dumps(
                            [item.model_dump() for item in extraction.memories]
                        ),
                        "reflections": json.dumps(_reflection_rows(extraction)),
                        "analysis": json.dumps(analysis),
                        "signals": json.dumps(signals),
                        "apply_legacy": apply_legacy,
                    },
                )
            )
            if signals:
                models = {str(item["embedding_model"]) for item in signals}
                if len(models) != 1:
                    raise ValueError("signal embedding models are inconsistent")
                stored = int(
                    session.scalar(
                        text(
                            "SELECT public.store_entry_signal_embeddings("
                            ":job_id, :claim_token, CAST(:embeddings AS jsonb), :model_id)"
                        ),
                        {
                            "job_id": claim.job_id,
                            "claim_token": claim.claim_token,
                            "embeddings": json.dumps(
                                [
                                    {
                                        "signal_id": item["id"],
                                        "values": item["embedding"],
                                    }
                                    for item in signals
                                ]
                            ),
                            "model_id": models.pop(),
                        },
                    )
                )
                if stored != len(signals):
                    raise RuntimeError("signal embedding persistence is incomplete")
            return source_version
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "P0001":
                raise StaleAnalysisClaimError("processing claim is no longer current") from exc
            raise


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
