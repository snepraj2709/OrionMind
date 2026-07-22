from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.reflections.schemas import FeedbackResponse
from app.modules.reflections.types import SavedFeedback, SynthesisRequest


class ReflectionResourceNotFoundError(LookupError):
    pass


class ReflectionsRepository:
    EVIDENCE_LIMIT = 12

    def request_synthesis_if_eligible(
        self,
        session: Session,
        *,
        user_id: UUID,
    ) -> SynthesisRequest | None:
        row = session.execute(
            text(
                "SELECT requested_job_id, requested_source_version "
                "FROM public.request_reflection_synthesis_if_eligible("
                ":user_id, pg_catalog.now())"
            ),
            {"user_id": user_id},
        ).mappings().one_or_none()
        if row is None:
            return None
        source_version = int(row["requested_source_version"])
        if source_version <= 0:
            raise RuntimeError("reflection synthesis source version is invalid")
        return SynthesisRequest(
            job_id=UUID(str(row["requested_job_id"])),
            source_version=source_version,
        )

    def load_aggregate(self, session: Session, *, user_id: UUID) -> dict[str, object]:
        payload = session.scalar(
            text(
                "SELECT public.get_reflections_for_owner("
                ":user_id, :evidence_limit)"
            ),
            {"user_id": user_id, "evidence_limit": self.EVIDENCE_LIMIT},
        )
        if not isinstance(payload, dict):
            raise RuntimeError("reflection aggregate payload is invalid")
        return cast(dict[str, object], payload)

    def put_feedback(
        self,
        session: Session,
        *,
        user_id: UUID,
        snapshot_id: UUID,
        insight_id: UUID,
        response: FeedbackResponse,
    ) -> SavedFeedback:
        try:
            row = session.execute(
                text(
                    "SELECT snapshot_id, insight_id, response, updated_at "
                    "FROM public.put_reflection_feedback_for_owner("
                    ":user_id, :snapshot_id, :insight_id, :response)"
                ),
                {
                    "user_id": user_id,
                    "snapshot_id": snapshot_id,
                    "insight_id": insight_id,
                    "response": response,
                },
            ).mappings().one()
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "P0002":
                raise ReflectionResourceNotFoundError from exc
            raise
        return SavedFeedback(
            snapshot_id=UUID(str(row["snapshot_id"])),
            insight_id=UUID(str(row["insight_id"])),
            response=cast(FeedbackResponse, str(row["response"])),
            updated_at=cast(datetime, row["updated_at"]),
        )
