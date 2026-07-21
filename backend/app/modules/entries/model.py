from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base


class EntryDraft(Base):
    __tablename__ = "entry_drafts"
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    content_envelope: Mapped[dict | None] = mapped_column(JSONB)
    fingerprint_key_id: Mapped[str] = mapped_column(String, nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Entry(Base):
    __tablename__ = "entries"
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    content_envelope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    input_type: Mapped[str] = mapped_column(String, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    original_theme_config_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("theme_configs.id"), nullable=False
    )
    processing_status: Mapped[str] = mapped_column(String, nullable=False)
    processing_error_code: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
