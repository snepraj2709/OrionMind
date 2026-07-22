from __future__ import annotations

import unicodedata
from datetime import date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.modules.entries.repository import EntryRepository, MissingMatchingDraftError
from app.modules.entries.types import (
    EntryOperation,
    EntryPageData,
    EntrySummaryData,
    PastEntryAcceptedData,
    VoicePreparation,
)
from app.modules.past_imports.service import PastImportService
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.exceptions.domain import DomainError
from app.shared.security.encryption import ContentCipher, ContentUnavailableError


class EntryService:
    def __init__(
        self,
        *,
        repository: EntryRepository,
        past_imports: PastImportService,
        cipher: ContentCipher,
    ) -> None:
        self._repository = repository
        self._past_imports = past_imports
        self._cipher = cipher

    def get_draft(self, *, user_id: UUID, uow: UnitOfWorkFactory) -> tuple[str | None, datetime | None]:
        with uow.for_user(user_id) as work:
            draft = self._repository.active_draft(work.session, user_id)
        if draft is None:
            return None, None
        try:
            return self._cipher.decrypt(draft.envelope, user_id=user_id, record_id=draft.id), draft.updated_at
        except Exception as exc:
            raise DomainError(
                status_code=503,
                error_code="ENTRY_DRAFT_UNAVAILABLE",
                message="The saved draft is temporarily unavailable.",
                headers={"Retry-After": "30"},
            ) from exc

    def save_draft(
        self, *, user_id: UUID, content: str, uow: UnitOfWorkFactory
    ) -> tuple[str | None, datetime | None]:
        if _blank_draft(content):
            return self.discard_draft(user_id=user_id, uow=uow)
        try:
            canonical = self._cipher.canonicalize(content)
            fingerprint_key_id, fingerprint = self._cipher.draft_fingerprint(
                canonical, user_id=user_id
            )
            with uow.for_user(user_id) as work:
                self._repository.lock_draft_owner(work.session, user_id)
                existing = self._repository.active_draft(work.session, user_id)
                draft_id = existing.id if existing else uuid4()
                envelope = self._cipher.encrypt(canonical, user_id=user_id, record_id=draft_id)
                self._repository.save_draft(
                    work.session,
                    user_id=user_id,
                    draft_id=draft_id,
                    envelope=envelope,
                    fingerprint_key_id=fingerprint_key_id,
                    fingerprint=fingerprint,
                )
                saved = self._repository.active_draft(work.session, user_id)
            if saved is None:
                raise RuntimeError("saved draft invariant failed")
            return canonical, saved.updated_at
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError(
                status_code=503,
                error_code="ENTRY_DRAFT_UNAVAILABLE",
                message="The saved draft is temporarily unavailable.",
                headers={"Retry-After": "30"},
            ) from exc

    def discard_draft(
        self, *, user_id: UUID, uow: UnitOfWorkFactory
    ) -> tuple[None, None]:
        try:
            with uow.for_user(user_id) as work:
                self._repository.discard_draft(work.session, user_id)
        except Exception as exc:
            raise DomainError(
                status_code=503,
                error_code="ENTRY_DRAFT_UNAVAILABLE",
                message="The saved draft is temporarily unavailable.",
                headers={"Retry-After": "30"},
            ) from exc
        return None, None

    def submit_text(
        self, *, user_id: UUID, content: str, uow: UnitOfWorkFactory
    ) -> EntryOperation:
        try:
            canonical = self._cipher.canonicalize(content)
            key_id, fingerprint = self._cipher.draft_fingerprint(canonical, user_id=user_id)
        except Exception as exc:
            raise DomainError(
                status_code=422,
                error_code="VALIDATION_ERROR",
                message="The request is invalid.",
            ) from exc
        entry_id = uuid4()
        processing_token = uuid4()
        envelope = self._cipher.encrypt(canonical, user_id=user_id, record_id=entry_id)
        try:
            with uow.for_user(user_id) as work:
                timezone = self._repository.profile_timezone(work.session, user_id)
                config_id = self._repository.fixed_config_id(work.session)
                entry_date = datetime.now(ZoneInfo(timezone)).date()
                claim = self._repository.submit_text(
                    work.session,
                    user_id=user_id,
                    entry_id=entry_id,
                    envelope=envelope,
                    fingerprint_key_id=key_id,
                    fingerprint=fingerprint,
                    entry_date=entry_date,
                    theme_config_id=config_id,
                    processing_token=processing_token,
                )
        except MissingMatchingDraftError as exc:
            raise DomainError(
                status_code=409,
                error_code="INVALID_STATE",
                message="A matching saved draft is required.",
            ) from exc
        operation = self.get_detail(user_id=user_id, entry_id=claim.entry_id, uow=uow)
        return EntryOperation(
            entry=operation.entry,
            plaintext=operation.plaintext,
            status_code=201 if claim.created else 200,
        )

    def list_entries(
        self, *, user_id: UUID, page: int, page_size: int, uow: UnitOfWorkFactory
    ) -> EntryPageData:
        with uow.for_user(user_id) as work:
            entries, total, themes = self._repository.list_entries(
                work.session, user_id, page=page, page_size=page_size
            )
        items = []
        for entry in entries:
            plaintext = self._decrypt_entry(entry.id, entry.envelope, user_id)
            items.append(
                EntrySummaryData(
                    entry=entry,
                    plaintext=plaintext,
                    themes=themes.get(entry.id, ()) if entry.processing_status == "completed" else (),
                )
            )
        return EntryPageData(items=tuple(items), total=total, page=page, page_size=page_size)

    def get_detail(
        self, *, user_id: UUID, entry_id: UUID, uow: UnitOfWorkFactory
    ) -> EntryOperation:
        with uow.for_user(user_id) as work:
            entry = self._repository.entry_detail(work.session, user_id, entry_id)
        if entry is None:
            raise DomainError(
                status_code=404,
                error_code="NOT_FOUND",
                message="The requested resource was not found.",
            )
        plaintext = self._decrypt_entry(entry.id, entry.envelope, user_id)
        return EntryOperation(entry=entry, plaintext=plaintext, status_code=200)

    def retry(
        self, *, user_id: UUID, entry_id: UUID, uow: UnitOfWorkFactory
    ) -> EntryOperation:
        with uow.for_user(user_id) as work:
            entry = self._repository.entry(work.session, user_id, entry_id)
            if entry is None:
                raise DomainError(
                    status_code=404,
                    error_code="NOT_FOUND",
                    message="The requested resource was not found.",
                )
            retried = self._repository.retry_failed(work.session, user_id, entry_id)
        if not retried:
            raise DomainError(
                status_code=409,
                error_code="INVALID_STATE",
                message="Only a failed entry can be retried.",
            )
        return self.get_detail(user_id=user_id, entry_id=entry_id, uow=uow)

    def prepare_voice(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
        requested_date: date | None,
        uow: UnitOfWorkFactory,
    ) -> VoicePreparation:
        if idempotency_key != idempotency_key.strip() or not 1 <= len(idempotency_key) <= 128:
            raise DomainError(422, "VALIDATION_ERROR", "The request is invalid.")
        with uow.for_user(user_id) as work:
            timezone = self._repository.profile_timezone(work.session, user_id)
            today = datetime.now(ZoneInfo(timezone)).date()
            effective_date = requested_date or today
            if effective_date > today:
                raise DomainError(422, "VALIDATION_ERROR", "The request is invalid.")
            claim_token = uuid4()
            claim = self._repository.claim_voice_action(
                work.session,
                user_id=user_id,
                idempotency_key=idempotency_key,
                effective_date=effective_date,
                claim_token=claim_token,
            )
        if claim.outcome == "date_conflict":
            raise DomainError(409, "INVALID_STATE", "The idempotency key conflicts with this action.")
        if claim.outcome == "in_progress":
            raise DomainError(409, "INVALID_STATE", "The voice action is already in progress.")
        if claim.outcome == "replay":
            assert claim.entry_id is not None
            replay = self.get_detail(user_id=user_id, entry_id=claim.entry_id, uow=uow)
            return VoicePreparation(effective_date, None, replay)
        return VoicePreparation(effective_date, claim.claim_token, None)

    def abandon_voice(
        self, *, user_id: UUID, idempotency_key: str, claim_token: UUID, uow: UnitOfWorkFactory
    ) -> None:
        with uow.for_user(user_id) as work:
            self._repository.release_voice_action(
                work.session,
                user_id=user_id,
                idempotency_key=idempotency_key,
                claim_token=claim_token,
            )

    def create_voice(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
        effective_date: date,
        claim_token: UUID,
        transcript: str,
        uow: UnitOfWorkFactory,
    ) -> EntryOperation:
        canonical = self._cipher.canonicalize(transcript)
        entry_id, processing_token = uuid4(), uuid4()
        envelope = self._cipher.encrypt(canonical, user_id=user_id, record_id=entry_id)
        with uow.for_user(user_id) as work:
            config_id = self._repository.fixed_config_id(work.session)
            self._repository.create_voice(
                work.session,
                user_id=user_id,
                entry_id=entry_id,
                envelope=envelope,
                entry_date=effective_date,
                config_id=config_id,
                idempotency_key=idempotency_key,
                processing_token=processing_token,
                claim_token=claim_token,
            )
        detail = self.get_detail(user_id=user_id, entry_id=entry_id, uow=uow)
        return EntryOperation(detail.entry, detail.plaintext, 201)

    def create_past(
        self,
        *,
        user_id: UUID,
        entry_date: date,
        content: str,
        uow: UnitOfWorkFactory,
    ) -> PastEntryAcceptedData:
        try:
            canonical = self._cipher.canonicalize(content)
        except Exception as exc:
            raise DomainError(422, "VALIDATION_ERROR", "The request is invalid.") from exc
        with uow.for_user(user_id) as work:
            timezone = self._repository.profile_timezone(work.session, user_id)
            today = datetime.now(ZoneInfo(timezone)).date()
            earliest = _shift_ten_years(today)
            if entry_date < earliest or entry_date > today:
                raise DomainError(422, "VALIDATION_ERROR", "The request is invalid.")
            config_id = self._repository.fixed_config_id(work.session)
            entry_id = uuid4()
            envelope = self._cipher.encrypt(canonical, user_id=user_id, record_id=entry_id)
            key_id, fingerprint = self._cipher.past_fingerprint(
                canonical, user_id=user_id, entry_date=entry_date.isoformat()
            )
            try:
                return self._past_imports.queue(
                    work.session,
                    user_id=user_id,
                    entry_id=entry_id,
                    envelope=envelope,
                    entry_date=entry_date,
                    config_id=config_id,
                    fingerprint_key_id=key_id,
                    fingerprint=fingerprint,
                )
            except Exception as exc:
                if getattr(exc, "orig", exc).__class__.__name__ == "UniqueViolation":
                    raise DomainError(
                        409,
                        "PAST_ENTRY_DUPLICATE",
                        "This historical entry has already been imported.",
                    ) from exc
                raise

    def _decrypt_entry(self, entry_id: UUID, envelope: dict, user_id: UUID) -> str:
        try:
            return self._cipher.decrypt(envelope, user_id=user_id, record_id=entry_id)
        except ContentUnavailableError as exc:
            raise DomainError(
                status_code=500,
                error_code="ENTRY_CONTENT_UNAVAILABLE",
                message="Entry content is temporarily unavailable.",
            ) from exc


def _blank_draft(content: str) -> bool:
    normalized = unicodedata.normalize(
        "NFC", content.replace("\r\n", "\n").replace("\r", "\n")
    )
    return normalized.strip("\t\n\v\f\r ") == ""


def _shift_ten_years(value: date) -> date:
    try:
        return value.replace(year=value.year - 10)
    except ValueError:
        return value.replace(year=value.year - 10, day=28)
