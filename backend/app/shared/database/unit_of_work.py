from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Literal, Protocol, Self
from uuid import UUID

from sqlalchemy.orm import Session, SessionTransaction

from app.shared.database.rls import install_user_rls_context, install_worker_role


class UnitOfWork(Protocol):
    session: Session

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]: ...


class SqlAlchemyUnitOfWork:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        user_id: UUID | None = None,
        worker: bool = False,
    ) -> None:
        if user_id is not None and worker:
            raise ValueError("a unit of work cannot be both user and worker scoped")
        self._session_factory = session_factory
        self._user_id = user_id
        self._worker = worker
        self.session: Session
        self._transaction: SessionTransaction | None = None

    def __enter__(self) -> Self:
        self.session = self._session_factory()
        self._transaction = self.session.begin()
        self._transaction.__enter__()
        try:
            if self._user_id is not None:
                install_user_rls_context(self.session, self._user_id)
            elif self._worker:
                install_worker_role(self.session)
        except BaseException:
            self._transaction.__exit__(*__import__("sys").exc_info())
            self.session.close()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            assert self._transaction is not None
            self._transaction.__exit__(exc_type, exc, traceback)
            return False
        finally:
            self.session.close()


class UnitOfWorkFactory:
    def __init__(
        self,
        application_session_factory: Callable[[], Session] | None,
        worker_session_factory: Callable[[], Session] | None,
    ) -> None:
        self._application = application_session_factory
        self._worker = worker_session_factory

    def for_user(self, user_id: UUID) -> SqlAlchemyUnitOfWork:
        if self._application is None:
            raise RuntimeError("application database is not configured")
        return SqlAlchemyUnitOfWork(self._application, user_id=user_id)

    def for_worker(self) -> SqlAlchemyUnitOfWork:
        if self._worker is None:
            raise RuntimeError("worker database is not configured")
        return SqlAlchemyUnitOfWork(self._worker, worker=True)
