from __future__ import annotations

import json
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.jobs.types import JobClaim
from app.modules.processing.schemas import Eligibility, LoopRole, NeedTag, SignalType, ThemeKey
from app.modules.reflection_engine.schemas import CandidateStatus, PatternType, UnitFloat


class _StrictStoredModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PersistedCandidateSignal(_StrictStoredModel):
    id: UUID
    user_id: UUID
    entry_id: UUID
    entry_user_id: UUID
    analysis_id: UUID
    analysis_user_id: UUID
    analysis_entry_id: UUID
    analysis_source_version: int = Field(gt=0)
    analysis_eligibility: Eligibility
    entry_date: date
    signal_type: SignalType
    normalized_label_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_envelope: dict[str, object]
    entry_content_envelope: dict[str, object]
    themes: list[ThemeKey] = Field(max_length=3)
    need_tags: list[NeedTag] = Field(max_length=4)
    loop_role: LoopRole | None
    confidence: UnitFloat
    source_start: int = Field(ge=0)
    source_end: int = Field(gt=0)
    occurred_on: date
    duplicate_cluster_key: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )

    def domain_values(self) -> dict[str, object]:
        return self.model_dump(
            mode="python",
            exclude={"payload_envelope", "entry_content_envelope"},
        )


class PersistedPreviousCandidate(_StrictStoredModel):
    id: UUID
    pattern_type: PatternType
    canonical_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: CandidateStatus
    score: UnitFloat
    version: int = Field(ge=1)
    first_seen_at: datetime
    last_seen_at: datetime
    last_source_version: int = Field(ge=0)
    rejected_at: datetime | None
    rejected_source_version: int | None = Field(default=None, ge=0)
    payload_envelope: dict[str, object]

    def domain_values(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"payload_envelope"})


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

    def complete_shadow(
        self,
        session: Session,
        *,
        claim: JobClaim,
        worker_id: str,
        candidate_count: int,
        selected_count: int,
        provider_called: bool,
    ) -> UUID:
        try:
            value = session.scalar(
                text(
                    "SELECT public.complete_reflection_shadow("
                    ":job_id, :worker_id, :claim_token, :candidate_count, "
                    ":selected_count, :provider_called)"
                ),
                {
                    "job_id": claim.job_id,
                    "worker_id": worker_id,
                    "claim_token": claim.claim_token,
                    "candidate_count": candidate_count,
                    "selected_count": selected_count,
                    "provider_called": provider_called,
                },
            )
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "P0001":
                raise StaleSynthesisClaimError(
                    "reflection shadow claim is no longer current"
                ) from exc
            raise
        if not isinstance(value, UUID):
            raise RuntimeError("reflection shadow completion result is invalid")
        return value
