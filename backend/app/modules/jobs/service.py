from __future__ import annotations

import logging
import time
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from app.modules.jobs.contracts import (
    EntryProcessingCapability,
    JobRepositoryCapability,
    ReflectionProcessingCapability,
)
from app.modules.jobs.failures import classify_failure
from app.modules.jobs.heartbeat import LostJobClaimError, heartbeat_claim
from app.modules.jobs.types import (
    BackfillStatus,
    DispatchResult,
    JobClaim,
    SchedulerStats,
)
from app.modules.processing.repository import StaleAnalysisClaimError
from app.modules.processing.service import AnalysisValidationError
from app.modules.reflection_engine.repository import StaleSynthesisClaimError
from app.modules.reflection_engine.service import SnapshotValidationError
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.observability.logging import safe_log
from app.shared.observability.reflection import QueueObservation, ReflectionTelemetry
from app.shared.security.encryption import ContentCipher


logger = logging.getLogger("orion.processing.jobs")
ALLOWED_FAILURES = frozenset(
    {
        "ENTRY_CONTENT_UNAVAILABLE",
        "INVALID_ANALYSIS",
        "PRIVACY_VALIDATION_FAILED",
        "PROCESSING_FAILED",
        "PROVIDER_UNAVAILABLE",
        "REFLECTION_DISABLED",
        "REFLECTION_ROLLOUT_BLOCKED",
        "REFLECTION_PROVIDER_UNAVAILABLE",
        "INVALID_SYNTHESIS",
        "UNSUPPORTED_JOB_TYPE",
        "WORKER_INTERRUPTED",
    }
)


class JobService:
    def __init__(
        self,
        *,
        repository: JobRepositoryCapability,
        processing: EntryProcessingCapability,
        cipher: ContentCipher,
        reflection: ReflectionProcessingCapability | None = None,
        reflection_engine_enabled: bool = False,
        reflection_scheduler_enabled: bool = False,
        reflection_rollout_mode: Literal["off", "shadow", "publish"] = "off",
        reflection_rollout_user_ids: Collection[UUID] = (),
        backfill_max_queue_depth: int = 1000,
        backfill_max_oldest_pending_seconds: int = 300,
        heartbeat_interval_seconds: float = 30.0,
        telemetry: ReflectionTelemetry | None = None,
    ) -> None:
        self._repository = repository
        self._processing = processing
        self._cipher = cipher
        self._reflection = reflection
        self._reflection_engine_enabled = reflection_engine_enabled
        self._reflection_scheduler_enabled = reflection_scheduler_enabled
        self._reflection_rollout_mode = reflection_rollout_mode
        self._reflection_rollout_user_ids = frozenset(reflection_rollout_user_ids)
        self._backfill_max_queue_depth = backfill_max_queue_depth
        self._backfill_max_oldest_pending_seconds = (
            backfill_max_oldest_pending_seconds
        )
        self._heartbeat_interval = heartbeat_interval_seconds
        self._telemetry = telemetry or ReflectionTelemetry()

    def run_one(self, *, worker_id: str, uow: UnitOfWorkFactory) -> bool:
        with uow.for_worker() as work:
            claim = self._repository.claim(work.session, worker_id=worker_id)
        if claim is None:
            return False
        started = time.monotonic()
        result = self._dispatch(claim=claim, worker_id=worker_id, uow=uow)
        duration_seconds = time.monotonic() - started
        error_code = result.error_code or "NONE"
        self._telemetry.record_job(
            job_type=claim.job_type,
            status=result.outcome,
            error_code=error_code,
            duration_seconds=duration_seconds,
        )
        safe_log(
            logger,
            "processing_job_finished",
            job_id=claim.job_id,
            job_type=claim.job_type,
            attempt=claim.attempts,
            status=result.outcome,
            error_code=error_code,
            duration_ms=round(duration_seconds * 1000),
            terminal_failures=1 if result.outcome == "failed" else 0,
        )
        return True

    def recover_stale(self, *, stale_seconds: int, uow: UnitOfWorkFactory) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)
        with uow.for_worker() as work:
            return self._repository.recover(work.session, stale_before=cutoff)

    def plan_backfill(
        self, *, batch_size: int, uow: UnitOfWorkFactory
    ) -> UUID:
        if not self._reflection_rollout_user_ids:
            raise ValueError("backfill requires a non-empty rollout cohort")
        with uow.for_worker() as work:
            return self._repository.plan_backfill(
                work.session,
                user_ids=self._reflection_rollout_user_ids,
                batch_size=batch_size,
                max_queue_depth=self._backfill_max_queue_depth,
                max_oldest_pending_seconds=(
                    self._backfill_max_oldest_pending_seconds
                ),
            )

    def backfill_status(
        self, *, run_id: UUID, uow: UnitOfWorkFactory
    ) -> BackfillStatus:
        with uow.for_worker() as work:
            return self._repository.backfill_status(work.session, run_id=run_id)

    def run_backfill_batch(
        self, *, run_id: UUID, uow: UnitOfWorkFactory
    ) -> BackfillStatus:
        with uow.for_worker() as work:
            return self._repository.run_backfill_batch(work.session, run_id=run_id)

    def set_backfill_state(
        self,
        *,
        run_id: UUID,
        action: Literal["pause", "resume"],
        uow: UnitOfWorkFactory,
    ) -> BackfillStatus:
        with uow.for_worker() as work:
            return self._repository.set_backfill_state(
                work.session, run_id=run_id, action=action
            )

    def schedule_reflections(
        self,
        *,
        uow: UnitOfWorkFactory,
        now: datetime | None = None,
    ) -> int:
        if not self._reflection_scheduler_enabled:
            return 0
        if (
            self._reflection_rollout_mode == "off"
            or not self._reflection_rollout_user_ids
        ):
            return 0
        scheduled_at = now or datetime.now(timezone.utc)
        with uow.for_worker() as work:
            observed = self._repository.schedule_reflections(
                work.session,
                now=scheduled_at,
                execution_mode=self._reflection_rollout_mode,
                user_ids=self._reflection_rollout_user_ids,
            )
        stats = (
            observed
            if isinstance(observed, SchedulerStats)
            else SchedulerStats(
                checked=int(observed),
                eligible=int(observed),
                enqueued=int(observed),
            )
        )
        self._telemetry.record_scheduler(
            checked=stats.checked,
            eligible=stats.eligible,
            enqueued=stats.enqueued,
        )
        safe_log(
            logger,
            "reflection_scheduler_complete",
            checked=stats.checked,
            eligible=stats.eligible,
            enqueued=stats.enqueued,
        )
        return stats.enqueued

    def observe_queue(self, *, uow: UnitOfWorkFactory) -> None:
        with uow.for_worker() as work:
            statuses = self._repository.queue_observability(work.session)
        self._telemetry.observe_queue(
            tuple(
                QueueObservation(
                    job_type=item.job_type,
                    queue_depth=item.queue_depth,
                    oldest_pending_seconds=item.oldest_pending_seconds,
                )
                for item in statuses
            )
        )
        for item in statuses:
            safe_log(
                logger,
                "processing_queue_observed",
                job_type=item.job_type,
                queue_depth=item.queue_depth,
                oldest_pending_seconds=item.oldest_pending_seconds,
            )

    def _dispatch(
        self, *, claim: JobClaim, worker_id: str, uow: UnitOfWorkFactory
    ) -> DispatchResult:
        try:
            if claim.job_type == "reflection_synthesis":
                if claim.entry_id is not None:
                    raise SnapshotValidationError("synthesis job has an entry")
                if not self._reflection_engine_enabled or self._reflection is None:
                    return self._record_failure(
                        claim=claim,
                        worker_id=worker_id,
                        uow=uow,
                        error_code="REFLECTION_DISABLED",
                        retryable=False,
                    )
                if (
                    self._reflection_rollout_mode == "off"
                    or claim.user_id not in self._reflection_rollout_user_ids
                    or claim.execution_mode != self._reflection_rollout_mode
                ):
                    return self._record_failure(
                        claim=claim,
                        worker_id=worker_id,
                        uow=uow,
                        error_code="REFLECTION_ROLLOUT_BLOCKED",
                        retryable=False,
                    )
                with self._heartbeat(
                    claim=claim,
                    worker_id=worker_id,
                    uow=uow,
                    completion_inside=True,
                ):
                    self._reflection.run_synthesis_job(
                        claim=claim,
                        worker_id=worker_id,
                        uow=uow,
                    )
                return DispatchResult("completed")
            if claim.job_type != "entry_processing" or claim.entry_id is None:
                return self._record_failure(
                    claim=claim,
                    worker_id=worker_id,
                    uow=uow,
                    error_code="UNSUPPORTED_JOB_TYPE",
                    retryable=False,
                )
            with self._heartbeat(claim=claim, worker_id=worker_id, uow=uow):
                with uow.for_worker() as work:
                    payload = self._repository.entry_payload(
                        work.session, claim=claim, worker_id=worker_id
                    )
                if payload is None:
                    raise LostJobClaimError("processing claim is no longer current")
                content = self._cipher.decrypt(
                    payload.envelope,
                    user_id=claim.user_id,
                    record_id=claim.entry_id,
                )
                prepared = self._processing.analyze(
                    user_id=claim.user_id,
                    entry_id=claim.entry_id,
                    entry_date=payload.entry_date,
                    theme_config_id=payload.theme_config_id,
                    content=content,
                    uow=uow,
                )
            self._processing.apply_job_analysis(
                claim=claim,
                worker_id=worker_id,
                theme_config_id=payload.theme_config_id,
                prepared=prepared,
                apply_legacy=not payload.already_materialized,
                uow=uow,
            )
            return DispatchResult("completed")
        except StaleSynthesisClaimError:
            with uow.for_worker() as work:
                self._repository.complete(
                    work.session,
                    claim=claim,
                    worker_id=worker_id,
                )
            return DispatchResult("stale", "WORKER_INTERRUPTED")
        except (LostJobClaimError, StaleAnalysisClaimError):
            return DispatchResult("stale", "WORKER_INTERRUPTED")
        except Exception as exc:
            if isinstance(exc, AnalysisValidationError):
                safe_log(
                    logger,
                    "entry_analysis_validation_failed",
                    entry_id=claim.entry_id,
                    validation_stage=exc.stage,
                )
            error_code, retryable = classify_failure(
                exc,
                synthesis=claim.job_type == "reflection_synthesis",
            )
            return self._record_failure(
                claim=claim,
                worker_id=worker_id,
                uow=uow,
                error_code=error_code,
                retryable=retryable,
            )

    def _record_failure(
        self,
        *,
        claim: JobClaim,
        worker_id: str,
        uow: UnitOfWorkFactory,
        error_code: str,
        retryable: bool,
    ) -> DispatchResult:
        if error_code not in ALLOWED_FAILURES:
            raise ValueError("processing failure code is not allowlisted")
        with uow.for_worker() as work:
            outcome = self._repository.fail(
                work.session,
                claim=claim,
                worker_id=worker_id,
                error_code=error_code,
                retryable=retryable,
            )
        return DispatchResult(outcome, error_code)

    @contextmanager
    def _heartbeat(
        self,
        *,
        claim: JobClaim,
        worker_id: str,
        uow: UnitOfWorkFactory,
        completion_inside: bool = False,
    ) -> Iterator[None]:
        with heartbeat_claim(
            repository=self._repository,
            interval_seconds=self._heartbeat_interval,
            claim=claim,
            worker_id=worker_id,
            uow=uow,
            completion_inside=completion_inside,
        ):
            yield


_classify_failure = classify_failure
