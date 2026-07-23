from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.modules.processing.embedding_backfill import (
    EmbeddingBackfillBatch,
    EmbeddingBackfillItem,
    EmbeddingBackfillRepository,
    EmbeddingBackfillService,
    EmbeddingBackfillStatus,
)
from app.modules.reflection_engine.repository import (
    ReflectionEngineRepository,
    SemanticNeighbor,
)
from app.modules.reflection_engine.service import (
    SEMANTIC_ANCHOR_BATCH_SIZE,
    ReflectionEngineService,
)


ROOT = Path(__file__).resolve().parents[1]
USER_ID = UUID("91111111-1111-4111-8111-111111111111")


class UnitOfWork:
    @contextmanager
    def for_worker(self):
        yield SimpleNamespace(session=object())


class SemanticBatchRepository:
    def __init__(self) -> None:
        self.anchor_batches: list[list[UUID]] = []

    def load_semantic_neighbors(self, _session, **kwargs):
        self.anchor_batches.append(kwargs["anchor_signal_ids"])
        return ()


class MappingResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self.rows


class SemanticSession:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, statement, parameters):
        self.calls.append((str(statement), parameters))
        return MappingResult(self.rows)


def test_semantic_repository_uses_one_bounded_owner_scoped_query() -> None:
    anchor = uuid4()
    neighbor = uuid4()
    session = SemanticSession(
        [
            {
                "anchor_signal_id": anchor,
                "neighbor_signal_id": neighbor,
                "cosine_distance": 0.04,
                "similarity": 0.96,
            }
        ]
    )

    result = ReflectionEngineRepository().load_semantic_neighbors(
        session,  # type: ignore[arg-type]
        user_id=USER_ID,
        anchor_signal_ids=[anchor],
        source_version=12,
        model_id="text-embedding-3-small",
        top_k=8,
        similarity_threshold=0.90,
    )

    assert result == (
        SemanticNeighbor(
            anchor_signal_id=anchor,
            neighbor_signal_id=neighbor,
            cosine_distance=0.04,
            similarity=0.96,
        ),
    )
    assert len(session.calls) == 1
    assert "find_signal_semantic_neighbors" in session.calls[0][0]
    assert "CAST(:anchor_signal_ids AS uuid[])" in session.calls[0][0]
    assert "CAST(:source_version AS bigint)" in session.calls[0][0]
    assert "CAST(:model_id AS text)" in session.calls[0][0]
    assert "CAST(:top_k AS integer)" in session.calls[0][0]
    assert "CAST(:similarity_threshold AS numeric)" in session.calls[0][0]
    assert session.calls[0][1] == {
        "user_id": USER_ID,
        "anchor_signal_ids": [anchor],
        "source_version": 12,
        "model_id": "text-embedding-3-small",
        "top_k": 8,
        "similarity_threshold": 0.90,
    }


def test_semantic_neighbor_metadata_is_strict_and_finite() -> None:
    payload = {
        "anchor_signal_id": str(uuid4()),
        "neighbor_signal_id": str(uuid4()),
        "cosine_distance": 0.1,
        "similarity": 0.9,
    }
    with pytest.raises(ValidationError):
        SemanticNeighbor.model_validate({**payload, "payload_envelope": {}})
    with pytest.raises(ValidationError):
        SemanticNeighbor.model_validate({**payload, "similarity": float("nan")})


def test_semantic_retrieval_batches_large_bases_without_dropping_anchors() -> None:
    repository = SemanticBatchRepository()
    engine = ReflectionEngineService(
        repository=repository,  # type: ignore[arg-type]
        cipher=object(),  # type: ignore[arg-type]
    )
    signals = [
        SimpleNamespace(id=uuid4())
        for _ in range(SEMANTIC_ANCHOR_BATCH_SIZE + 1)
    ]

    result = engine._load_semantic_neighbors(  # noqa: SLF001
        uow=UnitOfWork(),  # type: ignore[arg-type]
        user_id=USER_ID,
        source_version=12,
        signals=signals,  # type: ignore[arg-type]
    )

    assert result == ()
    assert [len(batch) for batch in repository.anchor_batches] == [
        SEMANTIC_ANCHOR_BATCH_SIZE,
        1,
    ]
    assert [item for batch in repository.anchor_batches for item in batch] == [
        signal.id for signal in signals
    ]


class BackfillRepository:
    def __init__(self, batch: EmbeddingBackfillBatch) -> None:
        self.batch = batch
        self.status_calls = 0
        self.claim_calls = 0
        self.stored = None
        self.released = []

    def status(self, _session, *, model_id: str):
        self.status_calls += 1
        return EmbeddingBackfillStatus(
            model_id=model_id,
            missing_signal_count=1 if self.stored is None else 0,
            claimable_signal_count=1 if self.stored is None else 0,
            active_claim_count=0,
        )

    def claim(self, _session, *, batch_size: int, model_id: str):
        self.claim_calls += 1
        assert batch_size == 1
        assert model_id == self.batch.model_id
        return self.batch

    def store(self, _session, **kwargs):
        self.stored = kwargs
        return len(kwargs["embeddings"])

    def release(self, _session, *, batch_token):
        self.released.append(batch_token)
        return 1


class AmbiguousStoreRepository(BackfillRepository):
    def __init__(self, batch: EmbeddingBackfillBatch) -> None:
        super().__init__(batch)
        self.store_attempts = 0

    def store(self, _session, **kwargs):
        self.store_attempts += 1
        self.stored = kwargs
        if self.store_attempts == 1:
            raise OperationalError(
                "COMMIT",
                {},
                ConnectionError("commit result unavailable"),
                connection_invalidated=True,
            )
        return len(kwargs["embeddings"])


class Cipher:
    def decrypt_json(self, _envelope, **_kwargs):
        return {
            "normalized_label": "meaningful progress",
            "interpretation": "Finishing the draft may reinforce competence.",
            "source_quote": "finished the draft",
        }


class Provider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def embed(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("provider failed")
        return (tuple([0.01] * 1536),)


def backfill_batch() -> EmbeddingBackfillBatch:
    return EmbeddingBackfillBatch(
        batch_token=uuid4(),
        model_id="text-embedding-3-small",
        items=[
            EmbeddingBackfillItem(
                signal_id=uuid4(),
                user_id=USER_ID,
                payload_envelope={},
                signal_type="self_statement",
                themes=["career"],
                need_tags=["competence"],
                loop_role="interpretation",
            )
        ],
    )


def test_backfill_dry_run_has_no_provider_or_claim_side_effects() -> None:
    repository = BackfillRepository(backfill_batch())
    provider = Provider()
    result = EmbeddingBackfillService(
        repository=repository,  # type: ignore[arg-type]
        cipher=Cipher(),  # type: ignore[arg-type]
        provider=provider,
        model_id="text-embedding-3-small",
    ).dry_run(uow=UnitOfWork(), batch_size=1)  # type: ignore[arg-type]

    assert result.missing_signal_count == 1
    assert result.estimated_input_tokens_upper_bound == 512
    assert result.estimated_cost_usd_upper_bound == pytest.approx(0.00001024)
    assert repository.status_calls == 1
    assert repository.claim_calls == 0
    assert provider.calls == []


def test_backfill_batch_reuses_signal_summary_and_stores_exactly_once() -> None:
    batch = backfill_batch()
    repository = BackfillRepository(batch)
    provider = Provider()
    result = EmbeddingBackfillService(
        repository=repository,  # type: ignore[arg-type]
        cipher=Cipher(),  # type: ignore[arg-type]
        provider=provider,
        model_id=batch.model_id,
    ).run_batch(uow=UnitOfWork(), batch_size=1)  # type: ignore[arg-type]

    assert result.claimed_signal_count == 1
    assert result.stored_signal_count == 1
    assert result.remaining_missing_signal_count == 0
    assert len(provider.calls) == 1
    assert provider.calls[0]["texts"][0].startswith("signal_type: self_statement")
    assert repository.stored["batch_token"] == batch.batch_token
    assert len(repository.stored["embeddings"][0]["values"]) == 1536
    assert repository.released == []


def test_backfill_provider_failure_releases_claim_for_resume() -> None:
    batch = backfill_batch()
    repository = BackfillRepository(batch)
    with pytest.raises(RuntimeError, match="provider failed"):
        EmbeddingBackfillService(
            repository=repository,  # type: ignore[arg-type]
            cipher=Cipher(),  # type: ignore[arg-type]
            provider=Provider(fail=True),
            model_id=batch.model_id,
        ).run_batch(uow=UnitOfWork(), batch_size=1)  # type: ignore[arg-type]
    assert repository.stored is None
    assert repository.released == [batch.batch_token]


def test_backfill_retries_ambiguous_store_without_reembedding() -> None:
    batch = backfill_batch()
    repository = AmbiguousStoreRepository(batch)
    provider = Provider()

    result = EmbeddingBackfillService(
        repository=repository,  # type: ignore[arg-type]
        cipher=Cipher(),  # type: ignore[arg-type]
        provider=provider,
        model_id=batch.model_id,
    ).run_batch(uow=UnitOfWork(), batch_size=1)  # type: ignore[arg-type]

    assert result.stored_signal_count == 1
    assert repository.store_attempts == 2
    assert len(provider.calls) == 1
    assert repository.released == []


def test_semantic_migration_is_exact_scan_worker_only_and_null_safe() -> None:
    migration = (ROOT / "migrations/0018_semantic_signal_retrieval.sql").read_text()
    lowered = migration.casefold()
    assert "hnsw" not in lowered and "ivfflat" not in lowered
    assert lowered.count("operator(extensions.<=>)") == 3
    assert "current_setting('role', true) is distinct from 'orion_worker'" in lowered
    assert "analysis.eligibility = 'accepted'" in lowered
    assert "neighbor_analysis.eligibility = 'accepted'" in lowered
    assert "neighbor.entry_id <> anchor.entry_id" in lowered
    assert "neighbor.embedding_model = p_model_id" in lowered
    assert "neighbor.embedding is not null" in lowered
    assert "for update of signal skip locked" in lowered
    assert "and embedding is null" in lowered
    assert "where embedding_backfill_token = p_batch_token" in lowered
    assert "order by id\n    for update" in lowered
    assert "if stored_count = expected_count then" in lowered
    assert "to orion_worker" in lowered
    assert "to authenticated" not in lowered.split(
        "create or replace function public.get_reflections_for_owner", 1
    )[0]

    expected_schema = "\n\n".join(
        path.read_text().rstrip("\n")
        for path in sorted((ROOT / "migrations").glob("*.sql"))
    ) + "\n"
    assert (ROOT / "supabase_schema.sql").read_text() == expected_schema


def test_backfill_repository_type_is_constructible() -> None:
    assert isinstance(EmbeddingBackfillRepository(), EmbeddingBackfillRepository)
