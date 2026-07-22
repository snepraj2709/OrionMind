from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import SecretStr
from psycopg import sql
from sqlalchemy.exc import DBAPIError

from app.main import create_app
from app.modules.jobs.repository import JobRepository
from app.modules.processing.embeddings import EMBEDDING_DIMENSIONS
from app.modules.processing.redaction import DetectedEntity, PiiRedactor
from app.modules.processing.repository import StaleAnalysisClaimError
from app.modules.processing.schemas import ModelEntryAnalysis, ModelThemeClassification
from app.modules.processing.service import _bind_model_offsets
from app.shared.config import Settings
from app.shared.database.session import build_database_sessions
from app.shared.security.encryption import AesGcmContentCipher
from scripts.migrate import apply_migrations, load_migrations


ROOT = Path(__file__).resolve().parents[1]
USER = UUID("b1111111-1111-4111-8111-111111111111")
CONFIG_ID = UUID("00000000-0000-0000-0000-000000000801")


def database_url() -> str:
    value = os.environ.get("STAGE2_DISPOSABLE_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("STAGE2_DISPOSABLE_DATABASE_URL is not configured")
    parsed = urlsplit(value)
    if parsed.path != "/orion_stage2_test" or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
    }:
        pytest.fail("entry analysis tests require the exact disposable database")
    return value


def reset(value: str) -> None:
    parsed = urlsplit(value)
    maintenance = urlunsplit(
        (parsed.scheme, parsed.netloc, "/postgres", parsed.query, parsed.fragment)
    )
    name = parsed.path.removeprefix("/")
    with psycopg.connect(maintenance, autocommit=True) as connection:
        connection.execute(
            "SELECT pg_catalog.pg_terminate_backend(pid) "
            "FROM pg_catalog.pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_catalog.pg_backend_pid()",
            (name,),
        )
        connection.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def bootstrap(value: str) -> None:
    reset(value)
    with psycopg.connect(value) as connection:
        connection.execute((ROOT / "tests/sql/bootstrap_auth.sql").read_text(), prepare=False)
        connection.execute("INSERT INTO auth.users (id) VALUES (%s)", (USER,))
        connection.commit()
    apply_migrations(value, load_migrations(ROOT / "migrations"))


def cipher() -> AesGcmContentCipher:
    return AesGcmContentCipher(
        encryption_keys={"entry-key": b"e" * 32},
        active_encryption_key_id="entry-key",
        fingerprint_keys={"fingerprint-key": b"f" * 32},
        active_fingerprint_key_id="fingerprint-key",
    )


@dataclass(frozen=True, slots=True)
class RuleAnalyzer:
    value: str | None = None

    def detect(self, text: str) -> tuple[DetectedEntity, ...]:
        if self.value is None or self.value not in text:
            return ()
        start = text.index(self.value)
        return (DetectedEntity("PERSON", start, start + len(self.value), 0.99),)


class Provider:
    def __init__(self, *, eligibility: str = "accepted", with_signal: bool = True) -> None:
        self.eligibility = eligibility
        self.with_signal = with_signal
        self.calls: list[dict[str, object]] = []

    def analyze(
        self,
        *,
        redacted_text: str,
        themes,
        deterministic_features,
        entry_date,
        safety_identifier,
    ) -> ModelEntryAnalysis:
        self.calls.append(
            {
                "redacted_text": redacted_text,
                "theme_keys": tuple(item.key for item in themes),
                "deterministic_features": deterministic_features,
                "entry_date": entry_date,
                "safety_identifier": safety_identifier,
            }
        )
        accepted = self.eligibility == "accepted"
        signals = []
        if accepted and self.with_signal:
            signals.append(
                {
                    "signal_type": "self_statement",
                    "normalized_label": "capable through explanation",
                    "interpretation": "Explaining the plan supported a sense of capability.",
                    "source_quote": redacted_text,
                    "source_start": 0,
                    "source_end": len(redacted_text),
                    "themes": ["career"],
                    "need_tags": ["competence"],
                    "loop_role": "action",
                    "confidence": 0.91,
                    "occurred_on": entry_date,
                }
            )
        score = 0.85 if accepted else 0.45
        return ModelEntryAnalysis.model_validate(
            {
                "quality": {
                    "entry_kind": "personal_reflection" if accepted else "unclear",
                    "lived_experience_score": score,
                    "self_reference_score": score,
                    "emotional_information_score": score,
                    "causal_reasoning_score": score,
                    "personal_relevance_score": score,
                    "confidence": 0.9,
                    "eligibility": self.eligibility,
                    "exclusion_reason_codes": [] if accepted else ["UNCLEAR"],
                },
                "signals": signals,
                "legacy": {
                    "ideas": [{"source_segment_id": "segment_0001"}],
                    "memories": [],
                    "theme": {
                        "mode": "dominant",
                        "themes": [
                            {
                                "key": "career",
                                "tier": "primary",
                                "evidence_segment_id": "segment_0001",
                            }
                        ],
                    },
                    "reflection": {
                        "filled_energy": {
                            "activity": "explaining the plan",
                            "confidence": 0.9,
                        },
                        "drained_energy": None,
                        "learned_about_self": None,
                    },
                },
            }
        )


class EmbeddingProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def embed(self, *, texts, safety_identifier):
        self.calls.append({"texts": texts, "safety_identifier": safety_identifier})
        return tuple(
            tuple(1.0 if index == 0 else 0.0 for index in range(EMBEDDING_DIMENSIONS))
            for _ in texts
        )


def test_model_signal_offsets_are_bound_to_exact_verbatim_quote() -> None:
    content = "The exact quote belongs here."
    result = Provider().analyze(
        redacted_text=content,
        themes=(),
        deterministic_features=object(),
        entry_date=date(2026, 6, 1),
        safety_identifier="a" * 64,
    )
    result.signals[0].source_start = 7
    result.signals[0].source_end = 8

    bound = _bind_model_offsets(result, redacted_text=content)

    assert bound.signals[0].source_start == 0
    assert bound.signals[0].source_end == len(content)


def test_model_signal_binding_rejects_non_verbatim_quote() -> None:
    content = "The exact quote belongs here."
    result = Provider().analyze(
        redacted_text=content,
        themes=(),
        deterministic_features=object(),
        entry_date=date(2026, 6, 1),
        safety_identifier="a" * 64,
    )
    result.signals[0].source_quote = "A quote that is not present."

    with pytest.raises(ValueError, match="source quote mismatch"):
        _bind_model_offsets(result, redacted_text=content)


def test_model_signal_binding_recovers_exact_source_from_safe_normalization() -> None:
    content = "I said, \u201cThis is exact.\u201d\nThen I paused."
    result = Provider().analyze(
        redacted_text=content,
        themes=(),
        deterministic_features=object(),
        entry_date=date(2026, 6, 1),
        safety_identifier="a" * 64,
    )
    result.signals[0].source_quote = 'I said, "This is exact." Then I paused.'

    bound = _bind_model_offsets(result, redacted_text=content)

    assert bound.signals[0].source_quote == content
    assert bound.signals[0].source_start == 0
    assert bound.signals[0].source_end == len(content)


def test_model_signal_binding_preserves_exact_overlapping_evidence() -> None:
    content = "I felt tired and disappointed."
    result = Provider().analyze(
        redacted_text=content,
        themes=(),
        deterministic_features=object(),
        entry_date=date(2026, 6, 1),
        safety_identifier="a" * 64,
    )
    result.signals.append(
        result.signals[0].model_copy(
            update={
                "signal_type": "emotion",
                "normalized_label": "disappointed",
                "source_quote": "tired and disappointed",
            }
        )
    )
    result.signals[0].source_quote = content

    bound = _bind_model_offsets(result, redacted_text=content)

    assert [signal.source_quote for signal in bound.signals] == [
        content,
        "tired and disappointed",
    ]


def test_model_theme_shape_is_normalized_without_changing_semantic_choices() -> None:
    classification = ModelThemeClassification.model_validate(
        {
            "mode": None,
            "themes": [
                {
                    "key": "career",
                    "tier": "tertiary",
                    "evidence_segment_id": "segment_0002",
                },
                {
                    "key": "personal_growth",
                    "tier": "primary",
                    "evidence_segment_id": "segment_0004",
                },
            ],
        }
    )

    assert classification.mode == "dominant"
    assert [theme.key for theme in classification.themes] == [
        "career",
        "personal_growth",
    ]
    assert [theme.tier for theme in classification.themes] == [
        "primary",
        "secondary",
    ]


def application(
    value: str,
    provider: Provider,
    *,
    person: str | None = None,
    embeddings: EmbeddingProvider | None = None,
):
    service = cipher()
    sqlalchemy_url = value.replace("postgresql://", "postgresql+psycopg://", 1)
    settings = Settings.model_validate(
        {
            "ENVIRONMENT": "test",
            "APP_DATABASE_URL": SecretStr(sqlalchemy_url),
            "WORKER_DATABASE_URL": SecretStr(sqlalchemy_url),
            "CORS_ALLOW_ORIGINS": "https://app.example.test",
            "LOG_FORMAT": "text",
            "RATE_LIMITING_ENABLED": False,
            "PROCESSING_JOB_HEARTBEAT_SECONDS": 1,
        }
    )
    return create_app(
        settings=settings,
        database_sessions=build_database_sessions(settings),
        extraction_provider=provider,
        embedding_provider=embeddings or EmbeddingProvider(),
        content_cipher=service,
        pii_redactor=PiiRedactor(analyzer=RuleAnalyzer(person), cipher=service),
    )


def insert_and_enqueue(connection: psycopg.Connection, content: str) -> tuple[UUID, UUID]:
    entry_id = uuid4()
    envelope = cipher().encrypt(content, user_id=USER, record_id=entry_id)
    connection.execute(
        "INSERT INTO public.entries "
        "(id, user_id, content_envelope, input_type, entry_date, original_theme_config_id) "
        "VALUES (%s, %s, %s::jsonb, 'text', CURRENT_DATE, %s)",
        (entry_id, USER, json.dumps(envelope), CONFIG_ID),
    )
    connection.execute("SET LOCAL ROLE authenticated")
    connection.execute(
        "SELECT pg_catalog.set_config('request.jwt.claims', %s, true)",
        (json.dumps({"sub": str(USER), "role": "authenticated"}),),
    )
    job_id = connection.execute(
        "SELECT public.enqueue_processing_job_for_owner(%s, %s, %s)",
        (USER, entry_id, str(entry_id)),
    ).fetchone()[0]
    return entry_id, job_id


def test_redacted_provider_exact_offset_legacy_parity_and_atomic_counters(
    caplog: pytest.LogCaptureFixture,
) -> None:
    value = database_url()
    bootstrap(value)
    content = "Rahul helped me explain the plan, and I felt capable afterward."
    with psycopg.connect(value) as connection, connection.transaction():
        entry_id, job_id = insert_and_enqueue(connection, content)
    provider = Provider()
    embeddings = EmbeddingProvider()
    app = application(value, provider, person="Rahul", embeddings=embeddings)
    caplog.set_level(logging.INFO)
    assert app.state.processing_worker.run_one(
        worker_id="analysis-worker", uow=app.state.database_sessions.unit_of_work_factory
    ) is True

    assert len(provider.calls) == 1
    assert len(embeddings.calls) == 1
    request = provider.calls[0]
    redacted = str(request["redacted_text"])
    assert redacted == "<PERSON_1> helped me explain the plan, and I felt capable afterward."
    assert "Rahul" not in redacted
    assert "Rahul" not in str(embeddings.calls[0]["texts"])
    assert "<PERSON_1>" not in str(embeddings.calls[0]["texts"])
    assert request["safety_identifier"] != str(USER)
    assert request["theme_keys"] == (
        "career",
        "money",
        "health",
        "love_life",
        "family_friends",
        "personal_growth",
        "fun_recreation",
        "home_lifestyle",
    )
    for secret in (content, redacted, "Rahul", "<PERSON_1>"):
        assert secret not in caplog.text

    service = cipher()
    with psycopg.connect(value) as connection:
        analysis = connection.execute(
            "SELECT id, eligibility, redacted_text_envelope, offset_map_envelope, "
            "source_version FROM public.entry_analyses WHERE entry_id = %s",
            (entry_id,),
        ).fetchone()
        assert analysis[1] == "accepted"
        assert service.decrypt_json(
            analysis[2],
            user_id=USER,
            record_id=analysis[0],
            purpose="entry_redacted_text",
        ) == redacted
        signal = connection.execute(
            "SELECT id, source_start, source_end, payload_envelope, "
            "extensions.vector_dims(embedding), embedding_model, embedded_at IS NOT NULL "
            "FROM public.entry_signals WHERE entry_id = %s",
            (entry_id,),
        ).fetchone()
        assert signal[4:] == (
            EMBEDDING_DIMENSIONS,
            "text-embedding-3-small",
            True,
        )
        assert connection.execute(
            "SELECT embedding OPERATOR(extensions.<=>) embedding "
            "FROM public.entry_signals WHERE id = %s",
            (signal[0],),
        ).fetchone()[0] == pytest.approx(0.0)
        payload = service.decrypt_json(
            signal[3],
            user_id=USER,
            record_id=signal[0],
            purpose="entry_signal_payload",
        )
        assert payload["source_quote"] == content
        assert content[signal[1] : signal[2]] == content
        assert connection.execute(
            "SELECT entry.processing_status, job.status, classification.mode, idea.content, "
            "theme.score FROM public.entries AS entry "
            "JOIN public.processing_jobs AS job ON job.entry_id = entry.id "
            "JOIN public.entry_classifications AS classification "
            "ON classification.entry_id = entry.id "
            "JOIN public.ideas AS idea ON idea.entry_id = entry.id "
            "JOIN public.entry_themes AS theme "
            "ON theme.classification_id = classification.id "
            "WHERE entry.id = %s AND job.id = %s",
            (entry_id, job_id),
        ).fetchone() == ("completed", "completed", "dominant", content, 1)
        assert connection.execute(
            "SELECT latest_accepted_source_version, new_valid_entries, "
            "new_accepted_signals, pending_local_dates "
            "FROM public.reflection_user_state WHERE user_id = %s",
            (USER,),
        ).fetchone() == (analysis[4], 1, 1, [date.today()])
        plaintext_rows = connection.execute(
            "SELECT row_to_json(signal)::text FROM public.entry_signals AS signal "
            "WHERE signal.entry_id = %s",
            (entry_id,),
        ).fetchone()[0]
        vault_text = connection.execute(
            "SELECT mapping_envelope::text FROM public.user_pii_vaults WHERE user_id = %s",
            (USER,),
        ).fetchone()[0]
        assert "Rahul" not in plaintext_rows + vault_text
        assert "<PERSON_1>" not in plaintext_rows + vault_text
    app.state.database_sessions.dispose()


def test_garbage_exact_and_near_duplicates_write_audits_without_contamination() -> None:
    value = database_url()
    bootstrap(value)
    content = "I felt calm after the meeting."
    with psycopg.connect(value) as connection:
        for _ in range(10):
            with connection.transaction():
                insert_and_enqueue(connection, content)
        with connection.transaction():
            insert_and_enqueue(connection, "I felt calm after the meeting!")
        with connection.transaction():
            insert_and_enqueue(connection, "hello testing mic")
    provider = Provider()
    embeddings = EmbeddingProvider()
    app = application(value, provider, embeddings=embeddings)
    for _ in range(12):
        assert app.state.processing_worker.run_one(
            worker_id="quality-worker",
            uow=app.state.database_sessions.unit_of_work_factory,
        ) is True
    assert len(provider.calls) == 1
    assert len(embeddings.calls) == 1
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT eligibility, count(*) FROM public.entry_analyses "
            "GROUP BY eligibility ORDER BY eligibility"
        ).fetchall() == [("accepted", 1), ("excluded", 11)]
        reasons = connection.execute(
            "SELECT exclusion_reason_codes FROM public.entry_analyses "
            "WHERE eligibility = 'excluded'"
        ).fetchall()
        flattened = [code for row in reasons for code in row[0]]
        assert flattened.count("EXACT_DUPLICATE") == 9
        assert "NEAR_DUPLICATE" in flattened
        assert "TEST_OR_NOISE" in flattened
        assert connection.execute(
            "SELECT new_valid_entries, new_accepted_signals "
            "FROM public.reflection_user_state WHERE user_id = %s",
            (USER,),
        ).fetchone() == (1, 1)
        assert connection.execute("SELECT count(*) FROM public.entry_signals").fetchone() == (1,)
    app.state.database_sessions.dispose()


def test_embedding_persistence_failure_rolls_back_completed_analysis() -> None:
    value = database_url()
    bootstrap(value)
    app = application(value, Provider())
    with psycopg.connect(value) as connection, connection.transaction():
        entry_id, _job_id = insert_and_enqueue(
            connection,
            "I felt capable after explaining a difficult plan clearly.",
        )

    repository = JobRepository()
    uow = app.state.database_sessions.unit_of_work_factory
    with uow.for_worker() as work:
        claim = repository.claim(work.session, worker_id="embedding-rollback-worker")
    assert claim is not None and claim.entry_id == entry_id
    with uow.for_worker() as work:
        payload = repository.entry_payload(
            work.session,
            claim=claim,
            worker_id="embedding-rollback-worker",
        )
    assert payload is not None
    prepared = app.state.processing_service.analyze(
        user_id=USER,
        entry_id=entry_id,
        entry_date=payload.entry_date,
        theme_config_id=payload.theme_config_id,
        content=cipher().decrypt(payload.envelope, user_id=USER, record_id=entry_id),
        uow=uow,
    )
    prepared.signals[0]["embedding"] = [0.0]

    with pytest.raises(DBAPIError):
        app.state.processing_service.apply_job_analysis(
            claim=claim,
            worker_id="embedding-rollback-worker",
            theme_config_id=payload.theme_config_id,
            prepared=prepared,
            apply_legacy=True,
            uow=uow,
        )

    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT count(*) FROM public.entry_analyses WHERE entry_id = %s",
            (entry_id,),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM public.entry_signals WHERE entry_id = %s",
            (entry_id,),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT entry.processing_status, job.status "
            "FROM public.entries AS entry "
            "JOIN public.processing_jobs AS job ON job.entry_id = entry.id "
            "WHERE entry.id = %s",
            (entry_id,),
        ).fetchone() == ("processing", "running")
    app.state.database_sessions.dispose()


def test_uncertain_keeps_legacy_output_and_stale_claim_persists_no_analysis() -> None:
    value = database_url()
    bootstrap(value)
    uncertain_provider = Provider(eligibility="uncertain", with_signal=False)
    app = application(value, uncertain_provider)
    with psycopg.connect(value) as connection, connection.transaction():
        uncertain_entry, _ = insert_and_enqueue(
            connection, "I may have felt uneasy, but I am not sure why."
        )
    assert app.state.processing_worker.run_one(
        worker_id="uncertain-worker",
        uow=app.state.database_sessions.unit_of_work_factory,
    ) is True
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT eligibility FROM public.entry_analyses WHERE entry_id = %s",
            (uncertain_entry,),
        ).fetchone() == ("uncertain",)
        assert connection.execute(
            "SELECT count(*) FROM public.ideas WHERE entry_id = %s", (uncertain_entry,)
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM public.entry_signals WHERE entry_id = %s", (uncertain_entry,)
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM public.reflection_user_state WHERE user_id = %s", (USER,)
        ).fetchone() == (0,)

    provider = Provider(with_signal=False)
    stale_app = application(value, provider)
    with psycopg.connect(value) as connection, connection.transaction():
        stale_entry, _ = insert_and_enqueue(
            connection, "A distinct reflection about preparing slowly helped me."
        )
    repository = JobRepository()
    uow = stale_app.state.database_sessions.unit_of_work_factory
    with uow.for_worker() as work:
        claim = repository.claim(work.session, worker_id="stale-worker")
    assert claim is not None and claim.entry_id == stale_entry
    with uow.for_worker() as work:
        payload = repository.entry_payload(work.session, claim=claim, worker_id="stale-worker")
    assert payload is not None
    prepared = stale_app.state.processing_service.analyze(
        user_id=USER,
        entry_id=stale_entry,
        entry_date=payload.entry_date,
        theme_config_id=payload.theme_config_id,
        content=cipher().decrypt(payload.envelope, user_id=USER, record_id=stale_entry),
        uow=uow,
    )
    with psycopg.connect(value) as connection:
        connection.execute(
            "UPDATE public.processing_jobs SET heartbeat_at = pg_catalog.now() - interval '10 minutes' "
            "WHERE id = %s",
            (claim.job_id,),
        )
        connection.commit()
    with uow.for_worker() as work:
        assert repository.recover(
            work.session,
            stale_before=datetime.now(timezone.utc) - timedelta(minutes=5),
        ) == 1
    with pytest.raises(StaleAnalysisClaimError):
        stale_app.state.processing_service.apply_job_analysis(
            claim=claim,
            worker_id="stale-worker",
            theme_config_id=payload.theme_config_id,
            prepared=prepared,
            apply_legacy=True,
            uow=uow,
        )
    with psycopg.connect(value) as connection:
        assert connection.execute(
            "SELECT count(*) FROM public.entry_analyses WHERE entry_id = %s", (stale_entry,)
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM public.entry_classifications WHERE entry_id = %s",
            (stale_entry,),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT processing_status FROM public.entries WHERE id = %s", (stale_entry,)
        ).fetchone() == ("pending",)
    app.state.database_sessions.dispose()
    stale_app.state.database_sessions.dispose()
