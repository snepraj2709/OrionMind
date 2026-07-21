from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


class StaleCandidateBasisError(RuntimeError):
    pass


class ReflectionEngineRepository:
    def load_candidate_basis(
        self,
        session: Session,
        *,
        user_id: UUID,
        source_version: int,
        basis_days: int = 90,
    ) -> dict[str, object]:
        payload = session.scalar(
            text(
                "SELECT public.get_reflection_candidate_basis("
                ":user_id, :source_version, :basis_days)"
            ),
            {
                "user_id": user_id,
                "source_version": source_version,
                "basis_days": basis_days,
            },
        )
        if not isinstance(payload, dict):
            raise RuntimeError("candidate basis payload is invalid")
        return payload

    def apply_candidates(
        self,
        session: Session,
        *,
        user_id: UUID,
        source_version: int,
        candidates: list[dict[str, object]],
        evidence: list[dict[str, object]],
    ) -> int:
        try:
            return int(
                session.scalar(
                    text(
                        "SELECT public.apply_deterministic_reflection_candidates("
                        ":user_id, :source_version, CAST(:candidates AS jsonb), "
                        "CAST(:evidence AS jsonb))"
                    ),
                    {
                        "user_id": user_id,
                        "source_version": source_version,
                        "candidates": json.dumps(candidates),
                        "evidence": json.dumps(evidence),
                    },
                )
            )
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "P0001":
                raise StaleCandidateBasisError(
                    "reflection candidate basis is no longer current"
                ) from exc
            raise
