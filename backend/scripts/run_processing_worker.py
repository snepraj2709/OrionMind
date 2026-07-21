from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.shared.config.settings import get_settings


logger = logging.getLogger("orion.processing.worker_entrypoint")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the shared Orion processing worker.")
    parser.add_argument(
        "--backfill-batch",
        type=int,
        default=0,
        choices=range(0, 101),
        metavar="0..100",
        help="enqueue one idempotent batch of already-materialized legacy entries and exit",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    application = create_app(settings=settings)
    sessions = application.state.database_sessions
    worker = application.state.processing_worker
    worker_id = f"processing-{socket.gethostname()[:50]}-{os.getpid()}"
    try:
        if args.backfill_batch:
            enqueued = worker.enqueue_backfill(
                batch_size=args.backfill_batch,
                uow=sessions.unit_of_work_factory,
            )
            logger.info("processing_backfill_enqueued count=%d", enqueued)
            return
        worker.run(worker_id=worker_id, uow=sessions.unit_of_work_factory)
    finally:
        sessions.dispose()
        tracer_provider = getattr(application.state, "tracer_provider", None)
        if tracer_provider is not None:
            tracer_provider.shutdown()


if __name__ == "__main__":
    main()
