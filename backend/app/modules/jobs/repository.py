from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.jobs.types import EntryJobPayload, JobClaim


FailureOutcome = Literal["pending", "failed", "stale"]


class JobRepository:
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

    def enqueue_backfill(
        self,
        session: Session,
        *,
        batch_size: int = 100,
        run_after: datetime | None = None,
    ) -> int:
        return int(
            session.scalar(
                text(
                    "SELECT public.enqueue_entry_processing_backfill("
                    ":batch_size, COALESCE(:run_after, pg_catalog.now() + "
                    "pg_catalog.make_interval(mins => 5)))"
                ),
                {"batch_size": batch_size, "run_after": run_after},
            )
            or 0
        )
