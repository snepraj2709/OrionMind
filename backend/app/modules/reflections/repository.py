from __future__ import annotations

from typing import Literal, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.reflections.types import RecalculationRequest


class ReflectionsRepository:
    EVIDENCE_LIMIT = 12

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
        aggregate = cast(dict[str, object], payload)
        current_basis = session.scalar(
            text(
                "SELECT public.get_reflection_recalculation_basis_for_owner("
                ":user_id, pg_catalog.now())"
            ),
            {"user_id": user_id},
        )
        if not isinstance(current_basis, dict):
            raise RuntimeError("reflection current basis payload is invalid")
        aggregate["current_basis"] = current_basis
        snapshot = aggregate.get("snapshot")
        if not isinstance(snapshot, dict) or snapshot.get("id") is None:
            return aggregate
        rows = session.execute(
            text(
                "SELECT insight.id AS insight_id, "
                "CASE review.user_feedback ->> 'verdict' "
                "WHEN 'resonates' THEN 'resonates' "
                "WHEN 'partly_true' THEN 'partly' "
                "WHEN 'not_true' THEN 'rejected' END AS response, "
                "review.updated_at "
                "FROM public.reflection_snapshot_insights AS insight "
                "JOIN public.reflection_snapshots AS snapshot "
                "ON snapshot.id = insight.snapshot_id "
                "AND snapshot.user_id = insight.user_id "
                "JOIN public.review_items AS review "
                "ON review.pattern_candidate_id = insight.candidate_id "
                "AND review.user_id = insight.user_id "
                "WHERE insight.user_id = :user_id "
                "AND insight.snapshot_id = :snapshot_id "
                "AND snapshot.user_id = :user_id "
                "AND review.user_id = :user_id "
                "AND review.scope = 'pattern' "
                "AND review.user_feedback IS NOT NULL"
            ),
            {"user_id": user_id, "snapshot_id": snapshot["id"]},
        ).mappings().all()
        feedback = aggregate.get("feedback")
        if not isinstance(feedback, list):
            raise RuntimeError("reflection feedback payload is invalid")
        merged = {
            str(item["insight_id"]): dict(item)
            for item in feedback
            if isinstance(item, dict) and item.get("insight_id") is not None
        }
        for row in rows:
            response = row["response"]
            if response is not None:
                merged[str(row["insight_id"])] = {
                    "insight_id": str(row["insight_id"]),
                    "response": str(response),
                    "updated_at": row["updated_at"],
                }
        aggregate["feedback"] = list(merged.values())
        return aggregate

    def request_recalculation(
        self,
        session: Session,
        *,
        user_id: UUID,
    ) -> RecalculationRequest:
        row = session.execute(
            text(
                "SELECT request_outcome, requested_job_id, "
                "requested_source_version, valid_entry_count, "
                "distinct_entry_dates, reflective_word_count "
                "FROM public.request_reflection_recalculation_for_owner("
                ":user_id, pg_catalog.now())"
            ),
            {"user_id": user_id},
        ).mappings().one()
        outcome = str(row["request_outcome"])
        if outcome not in {
            "accepted",
            "already_current",
            "not_eligible",
            "unavailable",
        }:
            raise RuntimeError("reflection recalculation outcome is invalid")
        return RecalculationRequest(
            outcome=cast(
                Literal[
                    "accepted",
                    "already_current",
                    "not_eligible",
                    "unavailable",
                ],
                outcome,
            ),
            job_id=(
                UUID(str(row["requested_job_id"]))
                if row["requested_job_id"] is not None
                else None
            ),
            source_version=int(row["requested_source_version"]),
            valid_entry_count=int(row["valid_entry_count"]),
            distinct_entry_dates=int(row["distinct_entry_dates"]),
            reflective_word_count=int(row["reflective_word_count"]),
        )
