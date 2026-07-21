from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
from pathlib import Path
from uuid import UUID


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.shared.config.settings import get_settings


logger = logging.getLogger("orion.processing.worker_entrypoint")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the shared Orion processing worker.",
        allow_abbrev=False,
    )
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument(
        "--backfill-plan",
        action="store_true",
        help="create one persisted backfill plan for the configured rollout cohort and exit",
    )
    operation.add_argument(
        "--backfill-action",
        choices=("status", "batch", "pause", "resume"),
        help="inspect or advance one persisted backfill run and exit",
    )
    parser.add_argument(
        "--backfill-run-id",
        type=UUID,
        help="persisted backfill run used by --backfill-action",
    )
    parser.add_argument(
        "--backfill-batch-size",
        type=int,
        default=100,
        choices=range(1, 101),
        metavar="1..100",
        help="batch size captured by a new --backfill-plan",
    )
    args = parser.parse_args(argv)
    if args.backfill_action and args.backfill_run_id is None:
        parser.error("--backfill-action requires --backfill-run-id")
    if args.backfill_run_id is not None and not args.backfill_action:
        parser.error("--backfill-run-id requires --backfill-action")
    return args


def main() -> None:
    args = parse_args()
    settings = get_settings()
    application = create_app(settings=settings)
    sessions = application.state.database_sessions
    worker = application.state.processing_worker
    worker_id = f"processing-{socket.gethostname()[:50]}-{os.getpid()}"
    try:
        if args.backfill_plan:
            run_id = worker.plan_backfill(
                batch_size=args.backfill_batch_size,
                uow=sessions.unit_of_work_factory,
            )
            logger.info("processing_backfill_planned run_id=%s", run_id)
            return
        if args.backfill_action:
            if args.backfill_action == "status":
                status = worker.backfill_status(
                    run_id=args.backfill_run_id,
                    uow=sessions.unit_of_work_factory,
                )
            elif args.backfill_action == "batch":
                status = worker.run_backfill_batch(
                    run_id=args.backfill_run_id,
                    uow=sessions.unit_of_work_factory,
                )
            else:
                status = worker.set_backfill_state(
                    run_id=args.backfill_run_id,
                    action=args.backfill_action,
                    uow=sessions.unit_of_work_factory,
                )
            logger.info(
                "processing_backfill_status run_id=%s status=%s planned=%d "
                "enqueued=%d queue_depth=%d oldest_pending_seconds=%d "
                "throttled=%s throttle_reason=%s",
                status.run_id,
                status.status,
                status.planned_count,
                status.enqueued_count,
                status.queue_depth,
                status.oldest_pending_seconds,
                status.throttled,
                status.throttle_reason or "NONE",
            )
            return
        worker.run(worker_id=worker_id, uow=sessions.unit_of_work_factory)
    finally:
        sessions.dispose()
        tracer_provider = getattr(application.state, "tracer_provider", None)
        if tracer_provider is not None:
            tracer_provider.shutdown()


if __name__ == "__main__":
    main()
