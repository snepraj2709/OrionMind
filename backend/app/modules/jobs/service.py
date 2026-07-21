from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from threading import Event, Thread

from app.modules.jobs.repository import JobRepository
from app.modules.jobs.types import DispatchResult, JobClaim
from app.modules.processing.provider import (
    ProviderUnavailableError,
    provider_failure_is_retryable,
)
from app.modules.processing.service import ProcessingService
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.security.encryption import ContentCipher, ContentUnavailableError


logger = logging.getLogger("orion.processing.jobs")
ALLOWED_FAILURES = frozenset(
    {
        "ENTRY_CONTENT_UNAVAILABLE",
        "INVALID_EXTRACTION",
        "PROCESSING_FAILED",
        "PROVIDER_UNAVAILABLE",
        "UNSUPPORTED_JOB_TYPE",
        "WORKER_INTERRUPTED",
    }
)


class LostJobClaimError(RuntimeError):
    pass


class JobService:
    def __init__(
        self,
        *,
        repository: JobRepository,
        processing: ProcessingService,
        cipher: ContentCipher,
        heartbeat_interval_seconds: float = 30.0,
    ) -> None:
        self._repository = repository
        self._processing = processing
        self._cipher = cipher
        self._heartbeat_interval = heartbeat_interval_seconds

    def run_one(self, *, worker_id: str, uow: UnitOfWorkFactory) -> bool:
        with uow.for_worker() as work:
            claim = self._repository.claim(work.session, worker_id=worker_id)
        if claim is None:
            return False
        result = self._dispatch(claim=claim, worker_id=worker_id, uow=uow)
        logger.info(
            "processing_job_finished job_id=%s job_type=%s attempt=%d outcome=%s error_code=%s",
            claim.job_id,
            claim.job_type,
            claim.attempts,
            result.outcome,
            result.error_code or "NONE",
        )
        return True

    def recover_stale(self, *, stale_seconds: int, uow: UnitOfWorkFactory) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)
        with uow.for_worker() as work:
            return self._repository.recover(work.session, stale_before=cutoff)

    def enqueue_backfill(
        self, *, batch_size: int, uow: UnitOfWorkFactory, run_after: datetime | None = None
    ) -> int:
        with uow.for_worker() as work:
            return self._repository.enqueue_backfill(
                work.session, batch_size=batch_size, run_after=run_after
            )

    def _dispatch(
        self, *, claim: JobClaim, worker_id: str, uow: UnitOfWorkFactory
    ) -> DispatchResult:
        try:
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
                if payload.already_materialized:
                    extraction = None
                else:
                    content = self._cipher.decrypt(
                        payload.envelope,
                        user_id=claim.user_id,
                        record_id=claim.entry_id,
                    )
                    extraction = self._processing.extract(
                        user_id=claim.user_id,
                        theme_config_id=payload.theme_config_id,
                        content=content,
                        uow=uow,
                    )
            if payload.already_materialized:
                with uow.for_worker() as work:
                    completed = self._repository.complete_materialized(
                        work.session, claim=claim, worker_id=worker_id
                    )
                if not completed:
                    raise LostJobClaimError("processing claim is no longer current")
            else:
                assert extraction is not None
                self._processing.apply_job_extraction(
                    claim=claim,
                    worker_id=worker_id,
                    theme_config_id=payload.theme_config_id,
                    extraction=extraction,
                    uow=uow,
                )
            return DispatchResult("completed")
        except LostJobClaimError:
            return DispatchResult("stale", "WORKER_INTERRUPTED")
        except Exception as exc:
            error_code, retryable = _classify_failure(exc)
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
        self, *, claim: JobClaim, worker_id: str, uow: UnitOfWorkFactory
    ) -> Iterator[None]:
        stopped = Event()
        lost = Event()

        def renew() -> bool:
            with uow.for_worker() as work:
                return self._repository.renew(
                    work.session, claim=claim, worker_id=worker_id
                )

        if not renew():
            raise LostJobClaimError("processing claim is no longer current")

        def heartbeat() -> None:
            while not stopped.wait(self._heartbeat_interval):
                try:
                    if not renew():
                        lost.set()
                        return
                except Exception:
                    lost.set()
                    return

        thread = Thread(target=heartbeat, name="orion-processing-heartbeat", daemon=True)
        thread.start()
        try:
            yield
            if lost.is_set() or not renew():
                raise LostJobClaimError("processing claim is no longer current")
        finally:
            stopped.set()
            thread.join(timeout=max(1.0, self._heartbeat_interval + 1.0))


def _classify_failure(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, ContentUnavailableError):
        return "ENTRY_CONTENT_UNAVAILABLE", False
    if isinstance(exc, ProviderUnavailableError):
        return "PROVIDER_UNAVAILABLE", provider_failure_is_retryable(exc)
    if isinstance(exc, ValueError):
        return "INVALID_EXTRACTION", False
    return "PROCESSING_FAILED", False
