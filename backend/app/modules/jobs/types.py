from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from app.modules.jobs.schemas import JobExecutionMode, JobType


@dataclass(frozen=True, slots=True)
class JobClaim:
    job_id: UUID
    user_id: UUID
    entry_id: UUID | None
    job_type: JobType
    execution_mode: JobExecutionMode
    source_version: str
    claim_token: UUID
    attempts: int


@dataclass(frozen=True, slots=True)
class EntryJobPayload:
    envelope: dict
    theme_config_id: UUID
    entry_date: date
    past_import: bool
    already_materialized: bool


@dataclass(frozen=True, slots=True)
class DispatchResult:
    outcome: Literal["completed", "pending", "failed", "stale"]
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class BackfillStatus:
    run_id: UUID
    status: Literal["planned", "running", "paused", "completed"]
    planned_count: int
    enqueued_count: int
    cohort_size: int
    batch_size: int
    queue_depth: int
    oldest_pending_seconds: int
    cursor_created_at: datetime | None
    cursor_entry_id: UUID | None
    throttled: bool
    throttle_reason: Literal["QUEUE_DEPTH", "OLDEST_PENDING_AGE"] | None


@dataclass(frozen=True, slots=True)
class SchedulerStats:
    checked: int
    eligible: int
    enqueued: int


@dataclass(frozen=True, slots=True)
class QueueStatus:
    job_type: JobType
    queue_depth: int
    oldest_pending_seconds: int
