from __future__ import annotations

from collections.abc import Collection
from datetime import date, datetime
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.jobs.types import (
    BackfillStatus,
    EntryJobPayload,
    JobClaim,
    QueueStatus,
    SchedulerStats,
)
from app.modules.processing.types import PreparedEntryAnalysis
from app.shared.database.unit_of_work import UnitOfWorkFactory


class JobRepositoryCapability(Protocol):
    def schedule_reflections(
        self,
        session: Session,
        *,
        now: datetime,
        execution_mode: Literal["shadow", "publish"],
        user_ids: Collection[UUID],
    ) -> SchedulerStats: ...

    def queue_observability(self, session: Session) -> tuple[QueueStatus, ...]: ...

    def claim(self, session: Session, *, worker_id: str) -> JobClaim | None: ...

    def renew(
        self,
        session: Session,
        *,
        claim: JobClaim,
        worker_id: str,
    ) -> bool: ...

    def complete(
        self,
        session: Session,
        *,
        claim: JobClaim,
        worker_id: str,
    ) -> bool: ...

    def fail(
        self,
        session: Session,
        *,
        claim: JobClaim,
        worker_id: str,
        error_code: str,
        retryable: bool,
    ) -> Literal["pending", "failed", "stale"]: ...

    def recover(self, session: Session, *, stale_before: datetime) -> int: ...

    def entry_payload(
        self,
        session: Session,
        *,
        claim: JobClaim,
        worker_id: str,
    ) -> EntryJobPayload | None: ...

    def plan_backfill(
        self,
        session: Session,
        *,
        user_ids: Collection[UUID],
        batch_size: int,
        max_queue_depth: int,
        max_oldest_pending_seconds: int,
    ) -> UUID: ...
    def backfill_status(self, session: Session, *, run_id: UUID) -> BackfillStatus: ...

    def run_backfill_batch(
        self,
        session: Session,
        *,
        run_id: UUID,
    ) -> BackfillStatus: ...

    def set_backfill_state(
        self,
        session: Session,
        *,
        run_id: UUID,
        action: Literal["pause", "resume"],
    ) -> BackfillStatus: ...


class EntryProcessingCapability(Protocol):
    def analyze(
        self,
        *,
        user_id: UUID,
        entry_id: UUID,
        entry_date: date,
        theme_config_id: UUID,
        content: str,
        uow: UnitOfWorkFactory,
    ) -> PreparedEntryAnalysis: ...

    def apply_job_analysis(
        self,
        *,
        claim: JobClaim,
        worker_id: str,
        theme_config_id: UUID,
        prepared: PreparedEntryAnalysis,
        apply_legacy: bool,
        uow: UnitOfWorkFactory,
    ) -> int: ...


class ReflectionProcessingCapability(Protocol):
    def run_synthesis_job(
        self,
        *,
        claim: JobClaim,
        worker_id: str,
        uow: UnitOfWorkFactory,
    ) -> UUID: ...
