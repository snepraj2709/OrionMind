from __future__ import annotations

import json
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.processing.embeddings import MAX_EMBEDDING_BATCH
from app.modules.processing.schemas import LoopRole, NeedTag, SignalType, ThemeKey
from app.modules.processing.service import signal_embedding_text
from app.modules.processing.types import SignalEmbeddingProvider
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.security.encryption import ContentCipher


class _StrictBackfillModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmbeddingBackfillStatus(_StrictBackfillModel):
    model_id: str
    missing_signal_count: int = Field(ge=0)
    claimable_signal_count: int = Field(ge=0)
    active_claim_count: int = Field(ge=0)


class EmbeddingBackfillItem(_StrictBackfillModel):
    signal_id: UUID
    user_id: UUID
    payload_envelope: dict[str, object]
    signal_type: SignalType
    themes: list[ThemeKey] = Field(max_length=3)
    need_tags: list[NeedTag] = Field(max_length=4)
    loop_role: LoopRole | None


class EmbeddingBackfillBatch(_StrictBackfillModel):
    batch_token: UUID
    model_id: str
    items: list[EmbeddingBackfillItem] = Field(max_length=MAX_EMBEDDING_BATCH)


class EmbeddingBackfillEstimate(_StrictBackfillModel):
    model_id: str
    missing_signal_count: int = Field(ge=0)
    claimable_signal_count: int = Field(ge=0)
    active_claim_count: int = Field(ge=0)
    max_batch_size: int = Field(ge=1, le=MAX_EMBEDDING_BATCH)
    estimated_input_tokens_upper_bound: int = Field(ge=0)
    estimated_cost_usd_upper_bound: float = Field(ge=0)
    pricing_assumption: str


class EmbeddingBackfillResult(_StrictBackfillModel):
    batch_token: UUID
    claimed_signal_count: int = Field(ge=0)
    stored_signal_count: int = Field(ge=0)
    remaining_missing_signal_count: int = Field(ge=0)


class EmbeddingBackfillRepository:
    def status(self, session: Session, *, model_id: str) -> EmbeddingBackfillStatus:
        payload = session.scalar(
            text("SELECT public.get_signal_embedding_backfill_status(:model_id)"),
            {"model_id": model_id},
        )
        return EmbeddingBackfillStatus.model_validate(payload)

    def claim(
        self, session: Session, *, batch_size: int, model_id: str
    ) -> EmbeddingBackfillBatch:
        payload = session.scalar(
            text(
                "SELECT public.claim_signal_embedding_backfill_batch("
                ":batch_size, :model_id)"
            ),
            {"batch_size": batch_size, "model_id": model_id},
        )
        return EmbeddingBackfillBatch.model_validate(payload)

    def store(
        self,
        session: Session,
        *,
        batch_token: UUID,
        model_id: str,
        embeddings: list[dict[str, object]],
    ) -> int:
        return int(
            session.scalar(
                text(
                    "SELECT public.store_signal_embedding_backfill_batch("
                    ":batch_token, CAST(:embeddings AS jsonb), :model_id)"
                ),
                {
                    "batch_token": batch_token,
                    "embeddings": json.dumps(embeddings),
                    "model_id": model_id,
                },
            )
        )

    def release(self, session: Session, *, batch_token: UUID) -> int:
        return int(
            session.scalar(
                text(
                    "SELECT public.release_signal_embedding_backfill_batch("
                    ":batch_token)"
                ),
                {"batch_token": batch_token},
            )
        )


class EmbeddingBackfillService:
    INPUT_TOKENS_PER_SIGNAL_UPPER_BOUND = 512
    PRICE_PER_MILLION_INPUT_TOKENS_USD = 0.02

    def __init__(
        self,
        *,
        repository: EmbeddingBackfillRepository,
        cipher: ContentCipher,
        provider: SignalEmbeddingProvider,
        model_id: str,
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._provider = provider
        self._model_id = model_id

    def dry_run(
        self, *, uow: UnitOfWorkFactory, batch_size: int = MAX_EMBEDDING_BATCH
    ) -> EmbeddingBackfillEstimate:
        bounded = _batch_size(batch_size)
        with uow.for_worker() as work:
            status = self._repository.status(work.session, model_id=self._model_id)
        estimated_tokens = (
            status.missing_signal_count * self.INPUT_TOKENS_PER_SIGNAL_UPPER_BOUND
        )
        return EmbeddingBackfillEstimate(
            **status.model_dump(),
            max_batch_size=bounded,
            estimated_input_tokens_upper_bound=estimated_tokens,
            estimated_cost_usd_upper_bound=round(
                estimated_tokens
                * self.PRICE_PER_MILLION_INPUT_TOKENS_USD
                / 1_000_000,
                8,
            ),
            pricing_assumption=(
                "Upper bound assumes 512 input tokens per signal at "
                "$0.02 per million embedding input tokens."
            ),
        )

    def run_batch(
        self, *, uow: UnitOfWorkFactory, batch_size: int = MAX_EMBEDDING_BATCH
    ) -> EmbeddingBackfillResult:
        bounded = _batch_size(batch_size)
        with uow.for_worker() as work:
            batch = self._repository.claim(
                work.session, batch_size=bounded, model_id=self._model_id
            )
        if not batch.items:
            with uow.for_worker() as work:
                remaining = self._repository.status(
                    work.session, model_id=self._model_id
                ).missing_signal_count
            return EmbeddingBackfillResult(
                batch_token=batch.batch_token,
                claimed_signal_count=0,
                stored_signal_count=0,
                remaining_missing_signal_count=remaining,
            )

        try:
            texts = tuple(self._embedding_text(item) for item in batch.items)
            vectors = self._provider.embed(texts=texts, safety_identifier="")
            if len(vectors) != len(batch.items):
                raise RuntimeError("embedding backfill response count is invalid")
            payload = [
                {"signal_id": str(item.signal_id), "values": list(vector)}
                for item, vector in zip(batch.items, vectors, strict=True)
            ]
            stored = self._store_with_ambiguous_commit_retry(
                uow=uow,
                batch_token=batch.batch_token,
                embeddings=payload,
            )
        except Exception:
            with uow.for_worker() as work:
                self._repository.release(
                    work.session, batch_token=batch.batch_token
                )
            raise

        with uow.for_worker() as work:
            remaining = self._repository.status(
                work.session, model_id=self._model_id
            ).missing_signal_count
        return EmbeddingBackfillResult(
            batch_token=batch.batch_token,
            claimed_signal_count=len(batch.items),
            stored_signal_count=stored,
            remaining_missing_signal_count=remaining,
        )

    def _store_with_ambiguous_commit_retry(
        self,
        *,
        uow: UnitOfWorkFactory,
        batch_token: UUID,
        embeddings: list[dict[str, object]],
    ) -> int:
        try:
            return self._store_once(
                uow=uow,
                batch_token=batch_token,
                embeddings=embeddings,
            )
        except DBAPIError as exc:
            if not exc.connection_invalidated:
                raise
            return self._store_once(
                uow=uow,
                batch_token=batch_token,
                embeddings=embeddings,
            )

    def _store_once(
        self,
        *,
        uow: UnitOfWorkFactory,
        batch_token: UUID,
        embeddings: list[dict[str, object]],
    ) -> int:
        with uow.for_worker() as work:
            return self._repository.store(
                work.session,
                batch_token=batch_token,
                model_id=self._model_id,
                embeddings=embeddings,
            )

    def _embedding_text(self, item: EmbeddingBackfillItem) -> str:
        payload = self._cipher.decrypt_json(
            item.payload_envelope,
            user_id=item.user_id,
            record_id=item.signal_id,
            purpose="entry_signal_payload",
        )
        if not isinstance(payload, dict):
            raise ValueError("backfill signal payload is invalid")
        normalized_label = payload.get("normalized_label")
        interpretation = payload.get("interpretation")
        if (
            not isinstance(normalized_label, str)
            or not normalized_label.strip()
            or not isinstance(interpretation, str)
            or not interpretation.strip()
        ):
            raise ValueError("backfill signal payload is invalid")
        return signal_embedding_text(
            signal_type=item.signal_type,
            normalized_label=normalized_label,
            interpretation=interpretation,
            themes=item.themes,
            need_tags=item.need_tags,
            loop_role=item.loop_role,
        )


def _batch_size(value: int) -> int:
    if isinstance(value, bool) or not 1 <= value <= MAX_EMBEDDING_BATCH:
        raise ValueError(f"batch size must be between 1 and {MAX_EMBEDDING_BATCH}")
    return value
