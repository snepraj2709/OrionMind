from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from app.modules.review.schemas import (
    REVIEW_PAGE_SIZE_MAX,
    EntryInsightFeedback,
    EntryInsightReviewItem,
    PatternFeedback,
    PatternReviewItem,
    ReviewItem,
)
from app.modules.review.types import (
    EntryInsightCategory,
    EntryInsightType,
    EntryInsightVerdict,
    InferenceLevel,
    PatternCategory,
    PatternType,
    PatternVerdict,
    ReviewCategoryFilter,
    ReviewItemCategory,
    ReviewItemRecord,
    ReviewItemType,
    ReviewScope,
    ReviewStatus,
    ReviewVerdict,
    SavedReviewFeedback,
    category_allowed_for_scope,
)
from app.shared.security.encryption import (
    ContentCipher,
    ContentUnavailableError,
    EnvelopePurpose,
    ReflectionFingerprintPurpose,
)


class ReviewRepositoryDataError(RuntimeError):
    pass


class ReviewItemNotFoundError(LookupError):
    pass


class ReviewItemStaleError(RuntimeError):
    pass


class ReviewRepository:
    _COLUMNS = (
        "id, user_id, entry_id, entry_signal_id, pattern_candidate_id, scope, "
        "item_type, category, statement_envelope, source_quote_envelope, "
        "source_entry_ids, source_dates, inference_level, model_confidence, "
        "review_status, user_feedback, corrected_statement_envelope, "
        "feedback_note_envelope, evidence_weight, reflection_eligible, metadata, "
        "created_at, updated_at"
    )

    def __init__(self, *, cipher: ContentCipher) -> None:
        self._cipher = cipher

    def count_items(
        self,
        session: Session,
        *,
        user_id: UUID,
        scope: ReviewScope,
        category: ReviewCategoryFilter,
        status: ReviewStatus,
    ) -> int:
        parameters = self._parameters(
            user_id=user_id,
            scope=scope,
            category=category,
            status=status,
        )
        return int(
            session.scalar(
                text(
                    "SELECT count(*) FROM public.review_items "
                    "WHERE user_id = :user_id AND scope = :scope "
                    "AND review_status = :status "
                    "AND (:category = 'all' OR category = :category)"
                ),
                parameters,
            )
            or 0
        )

    def list_items(
        self,
        session: Session,
        *,
        user_id: UUID,
        scope: ReviewScope,
        category: ReviewCategoryFilter,
        status: ReviewStatus,
        page: int,
        page_size: int,
    ) -> tuple[ReviewItem, ...]:
        self._validate_page(page=page, page_size=page_size)
        parameters = self._parameters(
            user_id=user_id,
            scope=scope,
            category=category,
            status=status,
        )
        parameters.update(
            {
                "limit": page_size,
                "offset": (page - 1) * page_size,
            }
        )
        rows = session.execute(
            text(
                "SELECT "
                + self._COLUMNS
                + " FROM public.review_items "
                "WHERE user_id = :user_id AND scope = :scope "
                "AND review_status = :status "
                "AND (:category = 'all' OR category = :category) "
                "ORDER BY created_at DESC, id DESC "
                "LIMIT :limit OFFSET :offset"
            ),
            parameters,
        ).mappings().all()
        return self._decode_rows(rows)

    def get_by_owner(
        self,
        session: Session,
        *,
        user_id: UUID,
        item_id: UUID,
    ) -> ReviewItem | None:
        row = session.execute(
            text(
                "SELECT "
                + self._COLUMNS
                + " FROM public.review_items "
                "WHERE user_id = :user_id AND id = :item_id"
            ),
            {"user_id": user_id, "item_id": item_id},
        ).mappings().one_or_none()
        if row is None:
            return None
        try:
            return self._decode_item(self._record(row))
        except (ContentUnavailableError, KeyError, TypeError, ValueError) as exc:
            raise ReviewRepositoryDataError("review item data is unavailable") from exc

    def pattern_item_id_for_snapshot_insight(
        self,
        session: Session,
        *,
        user_id: UUID,
        snapshot_id: UUID,
        insight_id: UUID,
    ) -> UUID | None:
        value = session.scalar(
            text(
                "SELECT review.id "
                "FROM public.reflection_snapshot_insights AS insight "
                "JOIN public.reflection_snapshots AS snapshot "
                "ON snapshot.id = insight.snapshot_id "
                "AND snapshot.user_id = insight.user_id "
                "JOIN public.review_items AS review "
                "ON review.pattern_candidate_id = insight.candidate_id "
                "AND review.user_id = insight.user_id "
                "WHERE insight.id = :insight_id "
                "AND insight.snapshot_id = :snapshot_id "
                "AND insight.user_id = :user_id "
                "AND snapshot.id = :snapshot_id "
                "AND snapshot.user_id = :user_id "
                "AND review.user_id = :user_id "
                "AND review.scope = 'pattern'"
            ),
            {
                "user_id": user_id,
                "snapshot_id": snapshot_id,
                "insight_id": insight_id,
            },
        )
        return UUID(str(value)) if value is not None else None

    def put_feedback(
        self,
        session: Session,
        *,
        user_id: UUID,
        item_id: UUID,
        verdict: ReviewVerdict,
        corrected_statement: str | None,
        note: str | None,
    ) -> SavedReviewFeedback:
        (
            corrected_envelope,
            corrected_fingerprint,
            corrected_compatible_fingerprints,
        ) = self._feedback_value(
            corrected_statement,
            user_id=user_id,
            item_id=item_id,
            envelope_purpose="review_item_corrected_statement",
            fingerprint_purpose="review_feedback_correction",
        )
        (
            note_envelope,
            note_fingerprint,
            note_compatible_fingerprints,
        ) = self._feedback_value(
            note,
            user_id=user_id,
            item_id=item_id,
            envelope_purpose="review_item_feedback_note",
            fingerprint_purpose="review_feedback_note",
        )
        try:
            row = session.execute(
                text(
                    "SELECT item_id, changed, source_version, updated_at "
                    "FROM public.put_review_feedback_for_owner("
                    ":user_id, :item_id, :verdict, "
                    "CAST(:corrected_envelope AS jsonb), :corrected_fingerprint, "
                    "CAST(:corrected_compatible_fingerprints AS text[]), "
                    "CAST(:note_envelope AS jsonb), :note_fingerprint, "
                    "CAST(:note_compatible_fingerprints AS text[]))"
                ),
                {
                    "user_id": user_id,
                    "item_id": item_id,
                    "verdict": verdict,
                    "corrected_envelope": (
                        json.dumps(corrected_envelope)
                        if corrected_envelope is not None
                        else None
                    ),
                    "corrected_fingerprint": corrected_fingerprint,
                    "corrected_compatible_fingerprints": list(
                        corrected_compatible_fingerprints
                    ),
                    "note_envelope": (
                        json.dumps(note_envelope) if note_envelope is not None else None
                    ),
                    "note_fingerprint": note_fingerprint,
                    "note_compatible_fingerprints": list(
                        note_compatible_fingerprints
                    ),
                },
            ).mappings().one()
        except DBAPIError as exc:
            sqlstate = getattr(exc.orig, "sqlstate", None)
            if sqlstate == "P0002":
                raise ReviewItemNotFoundError from exc
            if sqlstate == "P0003":
                raise ReviewItemStaleError from exc
            raise
        return SavedReviewFeedback(
            item_id=UUID(str(row["item_id"])),
            changed=bool(row["changed"]),
            source_version=int(row["source_version"]),
            updated_at=cast(datetime, row["updated_at"]),
        )

    def _feedback_value(
        self,
        value: str | None,
        *,
        user_id: UUID,
        item_id: UUID,
        envelope_purpose: EnvelopePurpose,
        fingerprint_purpose: ReflectionFingerprintPurpose,
    ) -> tuple[dict[str, object] | None, str, tuple[str, ...]]:
        if value is None:
            return None, "", ("",)
        keyed_fingerprints = self._cipher.reflection_fingerprints(
            value,
            user_id=user_id,
            purpose=fingerprint_purpose,
        )
        fingerprints = tuple(
            f"{key_id}:{digest}" for key_id, digest in keyed_fingerprints
        )
        return (
            self._cipher.encrypt_json(
                value,
                user_id=user_id,
                record_id=item_id,
                purpose=envelope_purpose,
            ),
            fingerprints[0],
            fingerprints,
        )

    @staticmethod
    def _parameters(
        *,
        user_id: UUID,
        scope: ReviewScope,
        category: ReviewCategoryFilter,
        status: ReviewStatus,
    ) -> dict[str, object]:
        if not category_allowed_for_scope(scope=scope, category=category):
            raise ValueError("category is not valid for the selected scope")
        return {
            "user_id": user_id,
            "scope": scope,
            "status": status,
            "category": category,
        }

    @staticmethod
    def _validate_page(*, page: int, page_size: int) -> None:
        if page < 1 or page_size < 1 or page_size > REVIEW_PAGE_SIZE_MAX:
            raise ValueError("invalid review pagination")

    def _decode_rows(self, rows: Sequence[RowMapping]) -> tuple[ReviewItem, ...]:
        try:
            return tuple(self._decode_item(self._record(row)) for row in rows)
        except (ContentUnavailableError, KeyError, TypeError, ValueError) as exc:
            raise ReviewRepositoryDataError("review item data is unavailable") from exc

    @staticmethod
    def _record(row: RowMapping) -> ReviewItemRecord:
        return ReviewItemRecord(
            id=UUID(str(row["id"])),
            user_id=UUID(str(row["user_id"])),
            entry_id=UUID(str(row["entry_id"])) if row["entry_id"] is not None else None,
            entry_signal_id=(
                UUID(str(row["entry_signal_id"]))
                if row["entry_signal_id"] is not None
                else None
            ),
            pattern_candidate_id=(
                UUID(str(row["pattern_candidate_id"]))
                if row["pattern_candidate_id"] is not None
                else None
            ),
            scope=cast(ReviewScope, str(row["scope"])),
            item_type=cast(ReviewItemType, str(row["item_type"])),
            category=cast(ReviewItemCategory, str(row["category"])),
            statement_envelope=dict(row["statement_envelope"]),
            source_quote_envelope=(
                dict(row["source_quote_envelope"])
                if row["source_quote_envelope"] is not None
                else None
            ),
            source_entry_ids=tuple(UUID(str(value)) for value in row["source_entry_ids"]),
            source_dates=tuple(row["source_dates"]),
            inference_level=cast(InferenceLevel, str(row["inference_level"])),
            model_confidence=float(row["model_confidence"]),
            review_status=cast(ReviewStatus, str(row["review_status"])),
            user_feedback=(
                dict(row["user_feedback"]) if row["user_feedback"] is not None else None
            ),
            corrected_statement_envelope=(
                dict(row["corrected_statement_envelope"])
                if row["corrected_statement_envelope"] is not None
                else None
            ),
            feedback_note_envelope=(
                dict(row["feedback_note_envelope"])
                if row["feedback_note_envelope"] is not None
                else None
            ),
            evidence_weight=float(row["evidence_weight"]),
            reflection_eligible=bool(row["reflection_eligible"]),
            metadata=dict(row["metadata"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _decode_item(self, record: ReviewItemRecord) -> ReviewItem:
        statement = self._decrypt_text(
            record.statement_envelope,
            record=record,
            purpose="review_item_statement",
        )
        source_quote = self._decrypt_optional_text(
            record.source_quote_envelope,
            record=record,
            purpose="review_item_source_quote",
        )
        corrected_statement = self._decrypt_optional_text(
            record.corrected_statement_envelope,
            record=record,
            purpose="review_item_corrected_statement",
        )
        note = self._decrypt_optional_text(
            record.feedback_note_envelope,
            record=record,
            purpose="review_item_feedback_note",
        )
        if record.scope == "entry_insight":
            entry_feedback = (
                self._entry_feedback(
                    record,
                    corrected_statement=corrected_statement,
                    note=note,
                )
                if record.user_feedback is not None
                else None
            )
            return EntryInsightReviewItem(
                id=record.id,
                statement=statement,
                source_entry_ids=list(record.source_entry_ids),
                source_dates=list(record.source_dates),
                confidence=record.model_confidence,
                status=record.review_status,
                scope="entry_insight",
                type=cast(EntryInsightType, record.item_type),
                category=cast(EntryInsightCategory, record.category),
                source_quote=source_quote,
                inference_level=cast(
                    Literal["direct", "inferred"], record.inference_level
                ),
                feedback=entry_feedback,
            )
        pattern_feedback = (
            self._pattern_feedback(
                record,
                corrected_statement=corrected_statement,
                note=note,
            )
            if record.user_feedback is not None
            else None
        )
        return PatternReviewItem(
            id=record.id,
            statement=statement,
            source_entry_ids=list(record.source_entry_ids),
            source_dates=list(record.source_dates),
            confidence=record.model_confidence,
            status=record.review_status,
            scope="pattern",
            type=cast(PatternType, record.item_type),
            category=cast(PatternCategory, record.category),
            source_quote=None,
            inference_level="synthesized",
            feedback=pattern_feedback,
        )

    def _decrypt_text(
        self,
        envelope: dict[str, object],
        *,
        record: ReviewItemRecord,
        purpose: EnvelopePurpose,
    ) -> str:
        value = self._cipher.decrypt_json(
            envelope,
            user_id=record.user_id,
            record_id=record.id,
            purpose=purpose,
        )
        if not isinstance(value, str):
            raise ValueError("review item encrypted value is invalid")
        return value

    def _decrypt_optional_text(
        self,
        envelope: dict[str, object] | None,
        *,
        record: ReviewItemRecord,
        purpose: EnvelopePurpose,
    ) -> str | None:
        if envelope is None:
            return None
        return self._decrypt_text(envelope, record=record, purpose=purpose)

    @staticmethod
    def _entry_feedback(
        record: ReviewItemRecord,
        *,
        corrected_statement: str | None,
        note: str | None,
    ) -> EntryInsightFeedback:
        assert record.user_feedback is not None
        return EntryInsightFeedback(
            verdict=cast(EntryInsightVerdict, record.user_feedback["verdict"]),
            corrected_statement=corrected_statement,
            note=note,
            evidence_weight=record.evidence_weight,
            updated_at=cast(datetime, record.user_feedback["updated_at"]),
        )

    @staticmethod
    def _pattern_feedback(
        record: ReviewItemRecord,
        *,
        corrected_statement: str | None,
        note: str | None,
    ) -> PatternFeedback:
        assert record.user_feedback is not None
        return PatternFeedback(
            verdict=cast(PatternVerdict, record.user_feedback["verdict"]),
            corrected_statement=corrected_statement,
            note=note,
            evidence_weight=record.evidence_weight,
            updated_at=cast(datetime, record.user_feedback["updated_at"]),
        )
