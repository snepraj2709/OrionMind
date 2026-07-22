from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event, Thread

from app.modules.jobs.contracts import JobRepositoryCapability
from app.modules.jobs.types import JobClaim
from app.shared.database.unit_of_work import UnitOfWorkFactory


class LostJobClaimError(RuntimeError):
    pass


@contextmanager
def heartbeat_claim(
    *,
    repository: JobRepositoryCapability,
    interval_seconds: float,
    claim: JobClaim,
    worker_id: str,
    uow: UnitOfWorkFactory,
    completion_inside: bool = False,
) -> Iterator[None]:
    stopped = Event()
    lost = Event()

    def renew() -> bool:
        with uow.for_worker() as work:
            renewed = repository.renew(
                work.session,
                claim=claim,
                worker_id=worker_id,
            )
        return renewed

    if not renew():
        raise LostJobClaimError("processing claim is no longer current")

    def heartbeat() -> None:
        while not stopped.wait(interval_seconds):
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
        if not completion_inside and (lost.is_set() or not renew()):
            raise LostJobClaimError("processing claim is no longer current")
    finally:
        stopped.set()
        thread.join(timeout=max(1.0, interval_seconds + 1.0))
