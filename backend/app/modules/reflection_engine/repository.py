from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.jobs.types import JobClaim


class StaleCandidateBasisError(RuntimeError):
    pass


class StaleSynthesisClaimError(RuntimeError):
    pass


class ReflectionEngineRepository:
    def load_synthesis_basis(
        self,
        session: Session,
        *,
        claim: JobClaim,
        worker_id: str,
        basis_days: int = 90,
    ) -> dict[str, object]:
        try:
            payload = session.scalar(
                text(
                    "SELECT public.get_reflection_synthesis_basis("
                    ":job_id, :worker_id, :claim_token, :basis_days)"
                ),
                {
                    "job_id": claim.job_id,
                    "worker_id": worker_id,
                    "claim_token": claim.claim_token,
                    "basis_days": basis_days,
                },
            )
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "P0001":
                raise StaleSynthesisClaimError(
                    "reflection synthesis claim is no longer current"
                ) from exc
            raise
        if not isinstance(payload, dict):
            raise RuntimeError("reflection synthesis basis payload is invalid")
        return payload

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

    def apply_snapshot(
        self,
        session: Session,
        *,
        claim: JobClaim,
        worker_id: str,
        snapshot: dict[str, object],
        candidates: list[dict[str, object]],
        candidate_evidence: list[dict[str, object]],
        insights: list[dict[str, object]],
        snapshot_evidence: list[dict[str, object]],
    ) -> UUID:
        try:
            value = session.scalar(
                text(
                    "SELECT public.apply_reflection_snapshot("
                    ":job_id, :worker_id, :claim_token, "
                    "CAST(:snapshot AS jsonb), CAST(:candidates AS jsonb), "
                    "CAST(:candidate_evidence AS jsonb), CAST(:insights AS jsonb), "
                    "CAST(:snapshot_evidence AS jsonb))"
                ),
                {
                    "job_id": claim.job_id,
                    "worker_id": worker_id,
                    "claim_token": claim.claim_token,
                    "snapshot": json.dumps(snapshot),
                    "candidates": json.dumps(candidates),
                    "candidate_evidence": json.dumps(candidate_evidence),
                    "insights": json.dumps(insights),
                    "snapshot_evidence": json.dumps(snapshot_evidence),
                },
            )
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "P0001":
                raise StaleSynthesisClaimError(
                    "reflection synthesis claim is no longer current"
                ) from exc
            raise
        if not isinstance(value, UUID):
            raise RuntimeError("reflection snapshot apply result is invalid")
        return value
