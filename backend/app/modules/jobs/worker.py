from __future__ import annotations

import logging
import signal
import time
from threading import Event

from app.modules.jobs.service import JobService
from app.shared.database.unit_of_work import UnitOfWorkFactory


logger = logging.getLogger("orion.processing.worker")


class ProcessingWorker:
    def __init__(
        self,
        *,
        service: JobService,
        poll_seconds: float,
        stale_seconds: int,
        recovery_interval_seconds: float,
    ) -> None:
        self._service = service
        self._poll_seconds = poll_seconds
        self._stale_seconds = stale_seconds
        self._recovery_interval = recovery_interval_seconds

    def run_one(self, *, worker_id: str, uow: UnitOfWorkFactory) -> bool:
        return self._service.run_one(worker_id=worker_id, uow=uow)

    def recover_stale(self, *, uow: UnitOfWorkFactory) -> int:
        return self._service.recover_stale(stale_seconds=self._stale_seconds, uow=uow)

    def enqueue_backfill(self, *, batch_size: int, uow: UnitOfWorkFactory) -> int:
        return self._service.enqueue_backfill(batch_size=batch_size, uow=uow)

    def run(self, *, worker_id: str, uow: UnitOfWorkFactory) -> None:
        stop = Event()

        def request_stop(_signal_number, _frame) -> None:
            stop.set()

        previous_term = signal.signal(signal.SIGTERM, request_stop)
        previous_int = signal.signal(signal.SIGINT, request_stop)
        last_recovery = 0.0
        try:
            while not stop.is_set():
                now = time.monotonic()
                if now - last_recovery >= self._recovery_interval:
                    try:
                        recovered = self.recover_stale(uow=uow)
                        logger.info("processing_recovery_complete recovered=%d", recovered)
                    except Exception:
                        logger.error("processing_recovery_failed")
                    last_recovery = now
                try:
                    processed = self.run_one(worker_id=worker_id, uow=uow)
                except Exception:
                    logger.error("processing_attempt_failed")
                    processed = False
                if not processed:
                    stop.wait(self._poll_seconds)
        finally:
            signal.signal(signal.SIGTERM, previous_term)
            signal.signal(signal.SIGINT, previous_int)
