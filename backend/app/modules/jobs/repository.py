from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.jobs.schemas import JobExecutionMode
from app.modules.jobs.types import BackfillStatus, EntryJobPayload, JobClaim


FailureOutcome = Literal["pending", "failed", "stale"]


class JobRepository:
    def schedule_reflections(
        self,
        session: Session,
        *,
        now: datetime,
        execution_mode: Literal["shadow", "publish"],
        user_ids: Collection[UUID],
    ) -> int:
        return int(
            session.scalar(
                text(
                    "SELECT public.schedule_reflection_jobs("
                    ":now, :execution_mode, :user_ids)"
                ),
                {
                    "now": now,
                    "execution_mode": execution_mode,
                    "user_ids": list(user_ids),
                },
            )
            or 0
        )

    def claim(self, session: Session, *, worker_id: str) -> JobClaim | None:
        row = session.execute(
            text("SELECT * FROM public.claim_processing_job(:worker_id)"),
            {"worker_id": worker_id},
        ).mappings().one_or_none()
        if row is None:
            return None
        return JobClaim(
            job_id=row["job_id"],
            user_id=row["user_id"],
            entry_id=row["entry_id"],
            job_type=row["job_type"],
            execution_mode=cast(JobExecutionMode, row["execution_mode"]),
            source_version=str(row["source_version"]),
            claim_token=row["claim_token"],
            attempts=int(row["attempts"]),
        )

    def renew(self, session: Session, *, claim: JobClaim, worker_id: str) -> bool:
        return bool(
            session.scalar(
                text(
                    "SELECT public.renew_processing_job("
                    ":job_id, :worker_id, :claim_token)"
                ),
                {
                    "job_id": claim.job_id,
                    "worker_id": worker_id,
                    "claim_token": claim.claim_token,
                },
            )
        )

    def fail(
        self,
        session: Session,
        *,
        claim: JobClaim,
        worker_id: str,
        error_code: str,
        retryable: bool,
    ) -> FailureOutcome:
        result = str(
            session.scalar(
                text(
                    "SELECT public.fail_processing_job("
                    ":job_id, :worker_id, :claim_token, :error_code, :retryable)"
                ),
                {
                    "job_id": claim.job_id,
                    "worker_id": worker_id,
                    "claim_token": claim.claim_token,
                    "error_code": error_code,
                    "retryable": retryable,
                },
            )
        )
        if result not in {"pending", "failed", "stale"}:
            raise RuntimeError("processing job failure outcome is invalid")
        return cast(FailureOutcome, result)

    def recover(self, session: Session, *, stale_before: datetime) -> int:
        return int(
            session.scalar(
                text("SELECT public.recover_stale_processing_jobs(:stale_before)"),
                {"stale_before": stale_before},
            )
            or 0
        )

    def entry_payload(
        self, session: Session, *, claim: JobClaim, worker_id: str
    ) -> EntryJobPayload | None:
        row = session.execute(
            text(
                "SELECT * FROM public.get_entry_processing_payload("
                ":job_id, :worker_id, :claim_token)"
            ),
            {
                "job_id": claim.job_id,
                "worker_id": worker_id,
                "claim_token": claim.claim_token,
            },
        ).mappings().one_or_none()
        if row is None:
            return None
        envelope = row["content_envelope"]
        if not isinstance(envelope, dict):
            raise RuntimeError("entry content envelope is invalid")
        return EntryJobPayload(
            envelope=envelope,
            theme_config_id=row["theme_config_id"],
            entry_date=row["entry_date"],
            past_import=bool(row["past_import"]),
            already_materialized=bool(row["already_materialized"]),
        )

    def plan_backfill(
        self,
        session: Session,
        *,
        user_ids: Collection[UUID],
        batch_size: int,
        max_queue_depth: int,
        max_oldest_pending_seconds: int,
    ) -> UUID:
        value = session.scalar(
            text(
                "SELECT public.plan_entry_processing_backfill("
                ":user_ids, :batch_size, :max_queue_depth, "
                ":max_oldest_pending_seconds)"
            ),
            {
                "user_ids": list(user_ids),
                "batch_size": batch_size,
                "max_queue_depth": max_queue_depth,
                "max_oldest_pending_seconds": max_oldest_pending_seconds,
            },
        )
        if not isinstance(value, UUID):
            raise RuntimeError("backfill plan result is invalid")
        return value

    def backfill_status(self, session: Session, *, run_id: UUID) -> BackfillStatus:
        value = session.scalar(
            text("SELECT public.get_entry_processing_backfill_status(:run_id)"),
            {"run_id": run_id},
        )
        return _backfill_status(value)

    def run_backfill_batch(self, session: Session, *, run_id: UUID) -> BackfillStatus:
        value = session.scalar(
            text("SELECT public.run_entry_processing_backfill_batch(:run_id)"),
            {"run_id": run_id},
        )
        return _backfill_status(value)

    def set_backfill_state(
        self,
        session: Session,
        *,
        run_id: UUID,
        action: Literal["pause", "resume"],
    ) -> BackfillStatus:
        value = session.scalar(
            text(
                "SELECT public.set_entry_processing_backfill_state("
                ":run_id, :action)"
            ),
            {"run_id": run_id, "action": action},
        )
        return _backfill_status(value)


def _backfill_status(value: object) -> BackfillStatus:
    if not isinstance(value, Mapping):
        raise RuntimeError("backfill status payload is invalid")
    try:
        cursor_raw = value.get("cursor_created_at")
        cursor_created_at = (
            cursor_raw
            if isinstance(cursor_raw, datetime)
            else datetime.fromisoformat(str(cursor_raw))
            if cursor_raw is not None
            else None
        )
        cursor_id_raw = value.get("cursor_entry_id")
        throttle_raw = value.get("throttle_reason")
        status = BackfillStatus(
            run_id=UUID(str(value["run_id"])),
            status=cast(Any, value["status"]),
            planned_count=int(value["planned_count"]),
            enqueued_count=int(value["enqueued_count"]),
            cohort_size=int(value["cohort_size"]),
            batch_size=int(value["batch_size"]),
            queue_depth=int(value["queue_depth"]),
            oldest_pending_seconds=int(value["oldest_pending_seconds"]),
            cursor_created_at=cursor_created_at,
            cursor_entry_id=UUID(str(cursor_id_raw)) if cursor_id_raw else None,
            throttled=bool(value["throttled"]),
            throttle_reason=cast(Any, throttle_raw) if throttle_raw else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("backfill status payload is invalid") from exc
    if status.status not in {"planned", "running", "paused", "completed"}:
        raise RuntimeError("backfill status payload is invalid")
    if status.throttle_reason not in {None, "QUEUE_DEPTH", "OLDEST_PENDING_AGE"}:
        raise RuntimeError("backfill status payload is invalid")
    return status
