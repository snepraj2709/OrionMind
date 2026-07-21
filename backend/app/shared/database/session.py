from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.shared.config.settings import Settings
from app.shared.database.unit_of_work import UnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class DatabaseSessions:
    application_engine: Engine | None
    worker_engine: Engine | None
    application: sessionmaker[Session] | None
    worker: sessionmaker[Session] | None

    @property
    def unit_of_work_factory(self) -> UnitOfWorkFactory:
        return UnitOfWorkFactory(self.application, self.worker)

    def dispose(self) -> None:
        if self.application_engine is not None:
            self.application_engine.dispose()
        if self.worker_engine is not None and self.worker_engine is not self.application_engine:
            self.worker_engine.dispose()


def _build_engine(url: str, settings: Settings) -> Engine | None:
    if not url.strip():
        return None
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_recycle=settings.DATABASE_POOL_RECYCLE_SECONDS,
    )


def build_database_sessions(settings: Settings) -> DatabaseSessions:
    app_engine = _build_engine(settings.APP_DATABASE_URL.get_secret_value(), settings)
    worker_engine = _build_engine(settings.WORKER_DATABASE_URL.get_secret_value(), settings)
    return DatabaseSessions(
        application_engine=app_engine,
        worker_engine=worker_engine,
        application=sessionmaker(app_engine, expire_on_commit=False) if app_engine else None,
        worker=sessionmaker(worker_engine, expire_on_commit=False) if worker_engine else None,
    )
