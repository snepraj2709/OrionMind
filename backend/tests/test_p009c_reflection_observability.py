from __future__ import annotations

import io
import json
import logging
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.modules.processing.provider import (
    OpenAIEntryAnalysisProvider,
    ProviderUnavailableError,
)
from app.modules.processing.schemas import DeterministicQualityFeatures
from app.modules.processing.redaction import (
    _offline_tldextract,
    initialize_offline_privacy_runtime,
)
from app.modules.reflection_engine.evaluation import (
    EvaluationDatasetRejected,
    FrozenEvaluationDataset,
    evaluate_frozen_dataset,
)
from app.modules.reflection_engine.preflight import (
    ModelAccessPreflightError,
    ModelAccessTarget,
    check_reflection_model_access,
)
from app.modules.reflections.service import ReflectionsService
from app.modules.reflections.types import ReflectionQuery
from app.shared.observability.logging import JsonFormatter, configure_logging, safe_log
from app.shared.observability.reflection import QueueObservation, ReflectionTelemetry


ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "sentinel-private-journal-7f956c"
REQUIRED_METRICS = {
    "reflection_jobs_total",
    "reflection_job_duration_seconds",
    "reflection_queue_depth",
    "reflection_entry_eligibility_total",
    "reflection_signals_total",
    "reflection_candidates_total",
    "reflection_validator_discards_total",
    "reflection_api_responses_total",
    "reflection_feedback_total",
}


def _metric_names(reader: InMemoryMetricReader) -> set[str]:
    data = reader.get_metrics_data()
    return {
        metric.name
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    }


def test_all_required_metrics_export_with_controlled_labels_and_no_public_route() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    telemetry = ReflectionTelemetry(meter_provider=provider)
    telemetry.record_job(
        job_type="entry_processing",
        status="completed",
        error_code="NONE",
        duration_seconds=0.25,
    )
    telemetry.observe_queue(
        (
            QueueObservation("entry_processing", 2, 7),
            QueueObservation("reflection_synthesis", 1, 3),
        )
    )
    telemetry.record_entry_analysis(
        result="accepted",
        kind="personal_reflection",
        signal_types=("self_statement",),
    )
    telemetry.record_candidate(pattern_type="hidden_driver", outcome="constructed")
    telemetry.record_validator_discard(reason_code="EVIDENCE_OWNER_MISMATCH")
    telemetry.record_api_response(
        reflection_state="available", processing_state="idle"
    )
    telemetry.record_feedback(response="resonates")
    telemetry.record_scheduler(checked=3, eligible=2, enqueued=1)

    names = _metric_names(reader)
    assert REQUIRED_METRICS <= names
    assert "reflection_queue_oldest_pending_age_seconds" in names
    assert "reflection_scheduler_users_total" in names
    assert not any("metrics" in route for route in _public_route_paths())
    with pytest.raises(ValueError):
        telemetry.record_candidate(pattern_type="unknown", outcome="constructed")
    with pytest.raises(ValueError):
        telemetry.record_api_response(
            reflection_state="journal text", processing_state="idle"
        )
    provider.shutdown()


def _public_route_paths() -> tuple[str, ...]:
    from app.contract import PUBLIC_OPERATIONS

    return tuple(path for _method, path in PUBLIC_OPERATIONS)


class _FailingResponses:
    def parse(self, **_kwargs):
        raise RuntimeError(SENTINEL)


class _FailingClient:
    responses = _FailingResponses()

    def with_options(self, **_kwargs):
        return self


def test_sentinel_never_appears_in_structured_logs_or_model_spans() -> None:
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry = ReflectionTelemetry(tracer_provider=tracer_provider)
    provider = OpenAIEntryAnalysisProvider(
        _FailingClient(),
        model="gpt-5.6-luna",
        connect_timeout=1,
        response_timeout=1,
        total_timeout=1,
        telemetry=telemetry,
    )
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    target = logging.getLogger("orion.processing.provider")
    target.addHandler(handler)
    try:
        with pytest.raises(ProviderUnavailableError):
            provider.analyze(
                redacted_text=SENTINEL,
                themes=(),
                deterministic_features=DeterministicQualityFeatures(
                    word_count=1,
                    meaningful_token_count=1,
                    unique_token_ratio=1,
                    repeated_ngram_ratio=0,
                    alphabetic_character_ratio=1,
                    exact_duplicate=False,
                    near_duplicate_similarity=None,
                    repeated_recent_entry_count=0,
                    copied_text_ratio=0,
                    hard_exclusion_codes=[],
                ),
                entry_date=date(2026, 7, 21),
                safety_identifier="a" * 64,
            )
    finally:
        target.removeHandler(handler)
        tracer_provider.shutdown()
    payload = stream.getvalue()
    spans = exporter.get_finished_spans()
    assert SENTINEL not in payload
    assert len(spans) == 1
    assert SENTINEL not in json.dumps(
        {key: value for key, value in spans[0].attributes.items()},
        sort_keys=True,
    )
    assert spans[0].events == ()


def test_structured_logger_refuses_unknown_events_fields_and_values() -> None:
    logger = logging.getLogger("orion.test.observability")
    with pytest.raises(ValueError):
        safe_log(logger, "not_allowlisted")
    with pytest.raises(ValueError):
        safe_log(logger, "reflection_api_response", journal=SENTINEL)
    with pytest.raises(ValueError):
        safe_log(
            logger,
            "reflection_api_response",
            reflection_state="unknown",
            processing_state="idle",
            status_code=200,
        )


def test_logging_suppresses_third_party_http_request_lines() -> None:
    configure_logging(json_logs=True)
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


class _AggregateRepository:
    def load_aggregate(self, _session, *, user_id):
        return {
            "snapshot": None,
            "state": {"latest_accepted_source_version": 0},
            "job": {},
            "current_basis": {
                "basis_start": None,
                "basis_end": None,
                "valid_entry_count": 0,
                "excluded_entry_count": 0,
                "distinct_entry_dates": 0,
                "reflective_word_count": 0,
            },
        }

    def request_synthesis_if_eligible(self, _session, *, user_id):
        return None


class _UnitOfWork:
    @contextmanager
    def for_user(self, _user_id):
        yield SimpleNamespace(session=object())

    @contextmanager
    def for_worker(self):
        yield SimpleNamespace(session=object())


def test_reflections_service_records_wire_states_and_http_status() -> None:
    user_id = uuid4()
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    telemetry = ReflectionTelemetry(meter_provider=provider)
    service = ReflectionsService(
        repository=_AggregateRepository(),  # type: ignore[arg-type]
        cipher=object(),  # type: ignore[arg-type]
        enabled=True,
        allowed_user_ids={user_id},
        telemetry=telemetry,
    )
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    target = logging.getLogger("orion.reflections.service")
    previous_level = target.level
    target.setLevel(logging.INFO)
    target.addHandler(handler)
    try:
        response = service.read(
            query=ReflectionQuery(user_id=user_id, range="all"),
            uow=_UnitOfWork(),  # type: ignore[arg-type]
        )
    finally:
        target.removeHandler(handler)
        target.setLevel(previous_level)
    assert response.reflection_state == "insufficient_reflective_content"
    assert response.processing_state == "idle"
    event = json.loads(stream.getvalue().splitlines()[-1])
    assert event["status_code"] == 200
    assert event["reflection_state"] == "insufficient_reflective_content"
    assert event["processing_state"] == "idle"
    assert "reflection_api_responses_total" in _metric_names(reader)
    provider.shutdown()


def test_tldextract_is_snapshot_only_cacheless_and_privacy_startup_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _offline_tldextract.cache_clear()
    extractor = _offline_tldextract()
    assert extractor.suffix_list_urls == ()
    assert extractor.fallback_to_snapshot is True
    assert extractor._cache.enabled is False

    from app.modules.processing import redaction

    monkeypatch.setattr(
        redaction,
        "_local_entity_analyzer",
        lambda: (_ for _ in ()).throw(RuntimeError("model missing")),
    )
    with pytest.raises(RuntimeError, match="model missing"):
        initialize_offline_privacy_runtime()


class _ModelsOnlyClient:
    def __init__(self, failing: str | None = None) -> None:
        self.calls: list[str] = []
        self.failing = failing
        self.models = self

    @property
    def responses(self):
        raise AssertionError("preflight must not access Responses")

    def retrieve(self, model_id: str):
        self.calls.append(model_id)
        if model_id == self.failing:
            raise RuntimeError(SENTINEL)
        return SimpleNamespace(id=model_id)


def _targets() -> tuple[ModelAccessTarget, ...]:
    return (
        ModelAccessTarget("entry_analysis", "gpt-5.6-luna"),
        ModelAccessTarget("embedding", "text-embedding-3-small"),
        ModelAccessTarget("synthesis", "gpt-5.6-terra"),
        ModelAccessTarget("critic", "gpt-5.6-sol"),
    )


def test_model_preflight_uses_only_models_retrieve_and_sanitizes_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _ModelsOnlyClient()
    assert check_reflection_model_access(client, _targets()) == _targets()
    assert client.calls == [item.model_id for item in _targets()]

    failing = _ModelsOnlyClient("gpt-5.6-terra")
    with pytest.raises(ModelAccessPreflightError) as raised:
        check_reflection_model_access(failing, _targets())
    assert raised.value.failed_roles == ("synthesis",)
    assert SENTINEL not in caplog.text


def _dataset(*, count: int = 100, consent: bool = True) -> FrozenEvaluationDataset:
    records = []
    for _index in range(count):
        extraction = {
            "idea_spans": [{"start": 0, "end": 4}],
            "memory_spans": [],
            "top_theme": "career",
            "invalid_structured_output": False,
            "reflection_polarity": {
                "filled_energy": "positive",
                "drained_energy": "negative",
                "learned_about_self": "neutral",
            },
        }
        records.append(
            {
                "entry_id": str(uuid4()),
                "consent_granted": consent,
                "expected": extraction,
                "combined_analyzer": extraction,
                "legacy_invalid_structured_output": False,
            }
        )
    return FrozenEvaluationDataset.model_validate({"version": 1, "records": records})


def test_evaluation_requires_consent_and_100_records_then_applies_all_gates() -> None:
    with pytest.raises(EvaluationDatasetRejected, match="at least 100"):
        evaluate_frozen_dataset(_dataset(count=99))
    with pytest.raises(EvaluationDatasetRejected, match="explicit consent"):
        evaluate_frozen_dataset(_dataset(consent=False))

    passed = evaluate_frozen_dataset(_dataset())
    assert passed.passed is True
    assert passed.exact_span_precision == 1
    assert passed.top_theme_agreement == 1
    assert passed.combined_invalid_structured_outputs == 0
    assert passed.reflection_polarity_regressions == 0


def test_observability_migration_has_fresh_install_parity() -> None:
    migration = (ROOT / "migrations/0012_reflection_observability.sql").read_text()
    schema = (ROOT / "supabase_schema.sql").read_text()
    assert migration in schema
    for function in (
        "schedule_reflection_jobs_observed",
        "get_processing_queue_observability",
    ):
        assert f"CREATE FUNCTION public.{function}" in migration
        assert f"GRANT EXECUTE ON FUNCTION public.{function}" in migration
