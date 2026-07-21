from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from threading import Event, Thread

from app.modules.past_imports.repository import PastImportRepository
from app.modules.past_imports.types import ImportClaim
from app.modules.processing.service import materialize_extraction
from app.modules.processing.types import ExtractionProvider, ThemeDefinition
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.security.encryption import ContentCipher


FIXED_THEMES = tuple(
    ThemeDefinition(key=key, name=name)
    for key, name in (
        ("career", "Career"),
        ("money", "Money"),
        ("health", "Health"),
        ("love_life", "Love Life"),
        ("family_friends", "Family & Friends"),
        ("personal_growth", "Personal Growth"),
        ("fun_recreation", "Fun & Recreation"),
        ("home_lifestyle", "Home & Lifestyle"),
    )
)


class PastImportWorker:
    def __init__(
        self,
        *,
        repository: PastImportRepository,
        provider: ExtractionProvider,
        cipher: ContentCipher,
        reflection_threshold: float,
        heartbeat_interval_seconds: float = 30.0,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._cipher = cipher
        self._threshold = reflection_threshold
        self._heartbeat_interval = heartbeat_interval_seconds

    def run_one(self, *, worker_id: str, uow: UnitOfWorkFactory) -> bool:
        with uow.for_worker() as work:
            claim = self._repository.claim(work.session, worker_id)
        if claim is None:
            return False
        with self._heartbeat(claim=claim, worker_id=worker_id, uow=uow):
            content = self._cipher.decrypt(
                claim.envelope, user_id=claim.user_id, record_id=claim.entry_id
            )
            bounded_content = content[:50_000]
            model = self._provider.extract(content=bounded_content, themes=FIXED_THEMES)
            extraction = materialize_extraction(
                model,
                content=bounded_content,
                allowed_keys={item.key for item in FIXED_THEMES},
                reflection_threshold=self._threshold,
            )
        with uow.for_worker() as work:
            self._repository.complete(
                work.session, claim=claim, worker_id=worker_id, extraction=extraction
            )
        return True

    def recover_stale(self, *, stale_seconds: int, uow: UnitOfWorkFactory) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)
        with uow.for_worker() as work:
            return self._repository.recover(work.session, cutoff)

    @contextmanager
    def _heartbeat(
        self, *, claim: ImportClaim, worker_id: str, uow: UnitOfWorkFactory
    ) -> Iterator[None]:
        stopped = Event()
        lost = Event()

        def renew() -> bool:
            with uow.for_worker() as work:
                return self._repository.renew(work.session, claim, worker_id)

        if not renew():
            raise RuntimeError("past import claim is no longer current")

        def heartbeat() -> None:
            while not stopped.wait(self._heartbeat_interval):
                try:
                    if not renew():
                        lost.set()
                        return
                except Exception:
                    lost.set()
                    return

        thread = Thread(target=heartbeat, name="orion-past-import-heartbeat", daemon=True)
        thread.start()
        try:
            yield
            if lost.is_set() or not renew():
                raise RuntimeError("past import claim is no longer current")
        finally:
            stopped.set()
            thread.join(timeout=max(1.0, self._heartbeat_interval + 1.0))
