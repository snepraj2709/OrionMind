from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.modules.jobs.schemas import JobType


@dataclass(frozen=True, slots=True)
class JobClaim:
    job_id: UUID
    user_id: UUID
    entry_id: UUID | None
    job_type: JobType
    source_version: str
    claim_token: UUID
    attempts: int


@dataclass(frozen=True, slots=True)
class EntryJobPayload:
    envelope: dict
    theme_config_id: UUID
    past_import: bool
    already_materialized: bool


@dataclass(frozen=True, slots=True)
class DispatchResult:
    outcome: Literal["completed", "pending", "failed", "stale"]
    error_code: str | None = None
