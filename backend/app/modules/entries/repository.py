from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from psycopg.errors import RaiseException

from app.modules.entries.types import (
    CandidateData,
    ClassificationData,
    DraftData,
    EntryData,
    ReflectionData,
    SubmissionClaim,
    ThemeData,
    VoiceClaim,
)


class MissingMatchingDraftError(RuntimeError):
    pass


class EntryRepository:
    def lock_draft_owner(self, session: Session, user_id: UUID) -> None:
        session.execute(
            text(
                "SELECT pg_catalog.pg_advisory_xact_lock("
                "pg_catalog.hashtextextended('orion-draft:' || CAST(:user_id AS text), 0))"
            ),
            {"user_id": user_id},
        )

    def active_draft(self, session: Session, user_id: UUID) -> DraftData | None:
        row = session.execute(
            text(
                "SELECT id, content_envelope, updated_at FROM public.entry_drafts "
                "WHERE user_id = :user_id AND status = 'active'"
            ),
            {"user_id": user_id},
        ).mappings().one_or_none()
        if row is None:
            return None
        return DraftData(id=row["id"], envelope=row["content_envelope"], updated_at=row["updated_at"])

    def save_draft(
        self,
        session: Session,
        *,
        user_id: UUID,
        draft_id: UUID,
        envelope: dict,
        fingerprint_key_id: str,
        fingerprint: str,
    ) -> UUID:
        return session.scalar(
            text(
                "SELECT public.save_entry_draft_for_owner("
                ":user_id, :draft_id, CAST(:envelope AS jsonb), :key_id, :fingerprint)"
            ),
            {
                "user_id": user_id,
                "draft_id": draft_id,
                "envelope": json.dumps(envelope),
                "key_id": fingerprint_key_id,
                "fingerprint": fingerprint,
            },
        )

    def discard_draft(self, session: Session, user_id: UUID) -> bool:
        return bool(
            session.scalar(
                text("SELECT public.discard_entry_draft_for_owner(:user_id)"),
                {"user_id": user_id},
            )
        )

    def profile_timezone(self, session: Session, user_id: UUID) -> str:
        value = session.scalar(
            text("SELECT timezone FROM public.user_profiles WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        if value is None:
            raise RuntimeError("profile bootstrap invariant failed")
        return str(value)

    def fixed_config_id(self, session: Session) -> UUID:
        value = session.scalar(
            text("SELECT id FROM public.theme_configs WHERE config_key = 'default_8'")
        )
        if value is None:
            raise RuntimeError("fixed theme config invariant failed")
        return value

    def submit_text(
        self,
        session: Session,
        *,
        user_id: UUID,
        entry_id: UUID,
        envelope: dict,
        fingerprint_key_id: str,
        fingerprint: str,
        entry_date: date,
        theme_config_id: UUID,
        processing_token: UUID,
    ) -> SubmissionClaim:
        try:
            result = session.scalar(
                text(
                    "SELECT public.submit_text_entry_from_draft_for_owner("
                    ":user_id, :entry_id, CAST(:envelope AS jsonb), :key_id, :fingerprint, "
                    ":entry_date, :config_id, :processing_token)"
                ),
                {
                    "user_id": user_id,
                    "entry_id": entry_id,
                    "envelope": json.dumps(envelope),
                    "key_id": fingerprint_key_id,
                    "fingerprint": fingerprint,
                    "entry_date": entry_date,
                    "config_id": theme_config_id,
                    "processing_token": processing_token,
                },
            )
        except DBAPIError as exc:
            if isinstance(exc.orig, RaiseException):
                raise MissingMatchingDraftError from exc
            raise
        return SubmissionClaim(
            entry_id=UUID(str(result["entry_id"])),
            processing_token=(
                UUID(str(result["processing_token"])) if result.get("processing_token") else None
            ),
            created=bool(result["created"]),
            reclaimed=bool(result["reclaimed"]),
        )

    def entry(self, session: Session, user_id: UUID, entry_id: UUID) -> EntryData | None:
        row = session.execute(
            text(
                "SELECT id, content_envelope, input_type, entry_date, original_theme_config_id, "
                "processing_status, processing_error_code, created_at FROM public.entries "
                "WHERE id = :entry_id AND user_id = :user_id"
            ),
            {"entry_id": entry_id, "user_id": user_id},
        ).mappings().one_or_none()
        return _entry(row) if row is not None else None

    def entry_detail(self, session: Session, user_id: UUID, entry_id: UUID) -> EntryData | None:
        entry = self.entry(session, user_id, entry_id)
        if entry is None:
            return None
        classification_rows = session.execute(
            text(
                "SELECT c.theme_config_id, c.source, c.mode, t.theme_key, t.name, "
                "t.color_hex, et.tier, et.score FROM public.entry_classifications c "
                "LEFT JOIN public.entry_themes et ON et.classification_id = c.id "
                "LEFT JOIN public.themes t ON t.id = et.theme_id "
                "WHERE c.entry_id = :entry_id AND c.user_id = :user_id "
                "ORDER BY CASE et.tier WHEN 'primary' THEN 1 WHEN 'secondary' THEN 2 ELSE 3 END"
            ),
            {"entry_id": entry_id, "user_id": user_id},
        ).mappings().all()
        classification = None
        if classification_rows:
            first = classification_rows[0]
            classification = ClassificationData(
                theme_config_id=first["theme_config_id"],
                source=first["source"],
                mode=first["mode"],
                themes=tuple(
                    ThemeData(
                        key=row["theme_key"],
                        name=row["name"],
                        color_hex=row["color_hex"],
                        tier=row["tier"],
                        score=float(row["score"]),
                    )
                    for row in classification_rows
                    if row["theme_key"] is not None
                ),
            )
        ideas = self._candidates(session, "ideas", user_id, entry_id)
        memories = self._candidates(session, "extracted_memories", user_id, entry_id)
        reflection_rows = session.execute(
            text(
                "SELECT r.id, r.reflection_type, r.activity, r.confidence_score, r.status, "
                "r.entry_id, e.entry_date, r.created_at, r.decided_at FROM public.reflections r "
                "JOIN public.entries e ON e.id = r.entry_id AND e.user_id = r.user_id "
                "WHERE r.entry_id = :entry_id AND r.user_id = :user_id "
                "ORDER BY r.created_at, r.id"
            ),
            {"entry_id": entry_id, "user_id": user_id},
        ).mappings().all()
        reflections = tuple(
            ReflectionData(
                id=row["id"],
                reflection_type=row["reflection_type"],
                activity=row["activity"],
                confidence_score=float(row["confidence_score"]),
                status=row["status"],
                entry_id=row["entry_id"],
                entry_date=row["entry_date"],
                created_at=row["created_at"],
                decided_at=row["decided_at"],
            )
            for row in reflection_rows
        )
        return EntryData(
            **{field: getattr(entry, field) for field in (
                "id", "envelope", "input_type", "entry_date", "original_theme_config_id",
                "processing_status", "processing_error_code", "created_at"
            )},
            classification=classification,
            ideas=ideas,
            memories=memories,
            reflections=reflections,
        )

    def _candidates(
        self, session: Session, table: str, user_id: UUID, entry_id: UUID
    ) -> tuple[CandidateData, ...]:
        if table not in {"ideas", "extracted_memories"}:
            raise ValueError("unsupported candidate table")
        rows = session.execute(
            text(
                f"SELECT c.id, c.content, c.status, c.entry_id, e.entry_date, c.created_at, "
                f"c.decided_at FROM public.{table} c JOIN public.entries e "
                "ON e.id = c.entry_id AND e.user_id = c.user_id "
                "WHERE c.entry_id = :entry_id AND c.user_id = :user_id "
                "ORDER BY c.created_at, c.id"
            ),
            {"entry_id": entry_id, "user_id": user_id},
        ).mappings().all()
        return tuple(CandidateData(**dict(row)) for row in rows)

    def list_entries(
        self, session: Session, user_id: UUID, *, page: int, page_size: int
    ) -> tuple[tuple[EntryData, ...], int, dict[UUID, tuple[ThemeData, ...]]]:
        total = int(
            session.scalar(
                text("SELECT count(*) FROM public.entries WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            or 0
        )
        rows = session.execute(
            text(
                "SELECT id, content_envelope, input_type, entry_date, original_theme_config_id, "
                "processing_status, processing_error_code, created_at FROM public.entries "
                "WHERE user_id = :user_id ORDER BY entry_date DESC, created_at DESC, id DESC "
                "LIMIT :limit OFFSET :offset"
            ),
            {"user_id": user_id, "limit": page_size, "offset": (page - 1) * page_size},
        ).mappings().all()
        entries = tuple(_entry(row) for row in rows)
        ids = [entry.id for entry in entries if entry.processing_status == "completed"]
        themes: dict[UUID, list[ThemeData]] = {entry_id: [] for entry_id in ids}
        if ids:
            theme_rows = session.execute(
                text(
                    "SELECT c.entry_id, t.theme_key, t.name, t.color_hex, et.tier "
                    "FROM public.entry_classifications c "
                    "JOIN public.entry_themes et ON et.classification_id = c.id "
                    "JOIN public.themes t ON t.id = et.theme_id "
                    "WHERE c.entry_id = ANY(CAST(:ids AS uuid[])) AND c.user_id = :user_id "
                    "AND c.source = 'initial' "
                    "ORDER BY c.entry_id, CASE et.tier WHEN 'primary' THEN 1 "
                    "WHEN 'secondary' THEN 2 ELSE 3 END"
                ),
                {"ids": ids, "user_id": user_id},
            ).mappings().all()
            for row in theme_rows:
                themes[row["entry_id"]].append(
                    ThemeData(
                        key=row["theme_key"],
                        name=row["name"],
                        color_hex=row["color_hex"],
                        tier=row["tier"],
                    )
                )
        return entries, total, {key: tuple(value) for key, value in themes.items()}

    def retry_failed(self, session: Session, user_id: UUID, entry_id: UUID) -> bool:
        return bool(
            session.scalar(
                text(
                    "SELECT public.retry_entry_processing_for_owner("
                    ":user_id, :entry_id)"
                ),
                {"user_id": user_id, "entry_id": entry_id},
            )
        )

    def create_voice(
        self,
        session: Session,
        *,
        user_id: UUID,
        entry_id: UUID,
        envelope: dict,
        entry_date: date,
        config_id: UUID,
        idempotency_key: str,
        processing_token: UUID,
        claim_token: UUID,
    ) -> None:
        session.execute(
            text(
                "SELECT public.create_voice_entry_for_owner("
                ":user_id, :entry_id, CAST(:envelope AS jsonb), :entry_date, :config_id, "
                ":idempotency_key, :processing_token, :claim_token)"
            ),
            {
                "user_id": user_id,
                "entry_id": entry_id,
                "envelope": json.dumps(envelope),
                "entry_date": entry_date,
                "config_id": config_id,
                "idempotency_key": idempotency_key,
                "processing_token": processing_token,
                "claim_token": claim_token,
            },
        )

    def claim_voice_action(
        self,
        session: Session,
        *,
        user_id: UUID,
        idempotency_key: str,
        effective_date: date,
        claim_token: UUID,
    ) -> VoiceClaim:
        result = session.scalar(
            text(
                "SELECT public.claim_voice_action_for_owner("
                ":user_id, :idempotency_key, :effective_date, :claim_token)"
            ),
            {
                "user_id": user_id,
                "idempotency_key": idempotency_key,
                "effective_date": effective_date,
                "claim_token": claim_token,
            },
        )
        return VoiceClaim(
            outcome=str(result["outcome"]),
            claim_token=UUID(str(result["claim_token"])) if result.get("claim_token") else None,
            entry_id=UUID(str(result["entry_id"])) if result.get("entry_id") else None,
        )

    def release_voice_action(
        self, session: Session, *, user_id: UUID, idempotency_key: str, claim_token: UUID
    ) -> bool:
        return bool(
            session.scalar(
                text(
                    "SELECT public.release_voice_action_for_owner("
                    ":user_id, :idempotency_key, :claim_token)"
                ),
                {
                    "user_id": user_id,
                    "idempotency_key": idempotency_key,
                    "claim_token": claim_token,
                },
            )
        )

def _entry(row: RowMapping) -> EntryData:
    return EntryData(
        id=row["id"],
        envelope=row["content_envelope"],
        input_type=row["input_type"],
        entry_date=row["entry_date"],
        original_theme_config_id=row["original_theme_config_id"],
        processing_status=row["processing_status"],
        processing_error_code=row["processing_error_code"],
        created_at=row["created_at"],
    )
