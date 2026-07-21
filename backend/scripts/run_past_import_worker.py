from __future__ import annotations

import logging
import os
import signal
import socket
import time
from threading import Event

from app.main import create_app
from app.shared.config.settings import get_settings


logger = logging.getLogger("orion.past_import_worker")


def main() -> None:
    settings = get_settings()
    application = create_app(settings=settings)
    sessions = application.state.database_sessions
    worker = application.state.past_import_worker
    stop = Event()

    def request_stop(_signal_number, _frame) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    worker_id = f"past-import-{socket.gethostname()[:50]}-{os.getpid()}"
    last_recovery = 0.0
    try:
        while not stop.is_set():
            now = time.monotonic()
            if now - last_recovery >= settings.PAST_IMPORT_RECOVERY_INTERVAL_SECONDS:
                try:
                    recovered = worker.recover_stale(
                        stale_seconds=settings.PAST_IMPORT_STALE_SECONDS,
                        uow=sessions.unit_of_work_factory,
                    )
                    logger.info("past_import_recovery_complete recovered=%d", recovered)
                except Exception:
                    logger.error("past_import_recovery_failed")
                last_recovery = now
            try:
                processed = worker.run_one(
                    worker_id=worker_id,
                    uow=sessions.unit_of_work_factory,
                )
            except Exception:
                logger.error("past_import_attempt_failed")
                processed = False
            if not processed:
                stop.wait(settings.PAST_IMPORT_POLL_SECONDS)
    finally:
        sessions.dispose()
        tracer_provider = getattr(application.state, "tracer_provider", None)
        if tracer_provider is not None:
            tracer_provider.shutdown()


if __name__ == "__main__":
    main()
