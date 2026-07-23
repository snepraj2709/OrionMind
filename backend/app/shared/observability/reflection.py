from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from app.shared.config.settings import Settings


JOB_TYPES = frozenset({"entry_processing", "reflection_synthesis"})
JOB_STATUSES = frozenset({"completed", "pending", "failed", "stale"})
JOB_ERROR_CODES = frozenset(
    {
        "NONE",
        "ENTRY_CONTENT_UNAVAILABLE",
        "INVALID_ANALYSIS",
        "PRIVACY_VALIDATION_FAILED",
        "PROCESSING_FAILED",
        "PROVIDER_UNAVAILABLE",
        "REFLECTION_DISABLED",
        "REFLECTION_ROLLOUT_BLOCKED",
        "REFLECTION_PROVIDER_UNAVAILABLE",
        "INVALID_SYNTHESIS",
        "UNSUPPORTED_JOB_TYPE",
        "WORKER_INTERRUPTED",
    }
)
ENTRY_KINDS = frozenset(
    {
        "personal_reflection",
        "personal_event",
        "personal_observation",
        "task_or_note",
        "informational_text",
        "creative_writing",
        "test_or_noise",
        "copied_or_quoted_text",
        "unclear",
    }
)
ELIGIBILITY_RESULTS = frozenset({"accepted", "uncertain", "excluded"})
SIGNAL_TYPES = frozenset(
    {
        "event",
        "emotion",
        "energy_gain",
        "energy_loss",
        "self_knowledge",
        "desire",
        "explicit_preference",
        "need",
        "avoidance",
        "belief",
        "self_statement",
        "action",
        "outcome",
        "conflict",
        "protective_strategy",
        "realization",
        "causal_relationship",
    }
)
PATTERN_TYPES = frozenset({"hidden_driver", "recurring_loop", "inner_tension"})
CANDIDATE_OUTCOMES = frozenset(
    {"constructed", "publishable", "selected", "discarded"}
)
REVIEW_SCOPES = frozenset({"entry_insight", "pattern"})
REVIEW_FEEDBACK_OUTCOMES = frozenset({"changed", "replayed"})
REVIEW_WEIGHT_BUCKETS = {
    0.0: "zero",
    0.5: "half",
    1.0: "full",
}
SYNTHESIS_SECTION_OUTCOMES = frozenset({"available", "abstained"})
SYNTHESIS_EXECUTION_MODES = frozenset({"shadow", "publish"})
JOB_RETRY_OUTCOMES = frozenset({"attempted", "scheduled", "terminal"})
REFLECTION_STATES = frozenset(
    {
        "available",
        "first_reflection_pending",
        "stale",
        "insufficient_reflective_content",
        "technical_failure",
        "unavailable",
    }
)
PROCESSING_STATES = frozenset({"idle", "pending", "failed", "unavailable"})
FEEDBACK_RESPONSES = frozenset({"resonates", "partly", "rejected"})
VALIDATOR_REASON_CODES = frozenset(
    {
        "EVIDENCE_SIGNAL_MISSING",
        "EVIDENCE_OWNER_MISMATCH",
        "EVIDENCE_ENTRY_MISMATCH",
        "EVIDENCE_ANALYSIS_NOT_ACCEPTED",
        "EVIDENCE_OUTSIDE_BASIS",
        "EVIDENCE_OFFSET_OUT_OF_BOUNDS",
        "EVIDENCE_OFFSET_MISMATCH",
        "EVIDENCE_ROLE_MISMATCH",
        "EVIDENCE_DATE_DIVERSITY",
        "SINGLE_ENTRY_DOMINANCE",
        "DUPLICATE_EVIDENCE",
        "COUNTEREVIDENCE_OMITTED",
        "LOOP_STEP_COUNT",
        "LOOP_TRANSITION_UNSUPPORTED",
        "LOOP_CLOSURE_UNSUPPORTED",
        "TENSION_SIDE_MISSING",
        "TENSION_INTEGRATION_INVALID",
        "UNSAFE_DIAGNOSTIC_LANGUAGE",
        "UNSAFE_IDENTITY_LANGUAGE",
        "HYPOTHESIS_FRAMING_REQUIRED",
        "UNKNOWN_CANDIDATE",
        "CRITIC_DISCARDED",
    }
)


@dataclass(frozen=True, slots=True)
class QueueObservation:
    job_type: str
    queue_depth: int
    oldest_pending_seconds: int


class ReflectionTelemetry:
    """Low-cardinality Reflection metrics and privacy-safe manual spans."""

    def __init__(
        self,
        *,
        meter_provider: MeterProvider | None = None,
        tracer_provider: TracerProvider | None = None,
    ) -> None:
        self._meter_provider = meter_provider
        self._tracer = (
            tracer_provider.get_tracer("orion.reflection")
            if tracer_provider is not None
            else trace.get_tracer("orion.reflection")
        )
        self._queue_lock = Lock()
        self._queue: dict[str, QueueObservation] = {
            job_type: QueueObservation(job_type, 0, 0) for job_type in JOB_TYPES
        }
        if meter_provider is None:
            self._jobs = None
            self._job_duration = None
            self._entry_eligibility = None
            self._signals = None
            self._candidates = None
            self._validator_discards = None
            self._api_responses = None
            self._feedback = None
            self._review_feedback = None
            self._synthesis_sections = None
            self._job_retries = None
            self._scheduler = None
            return
        meter = meter_provider.get_meter("orion.reflection")
        self._jobs = meter.create_counter(
            "reflection_jobs_total", description="Reflection processing job outcomes"
        )
        self._job_duration = meter.create_histogram(
            "reflection_job_duration_seconds",
            unit="s",
            description="Reflection processing job duration",
        )
        meter.create_observable_gauge(
            "reflection_queue_depth",
            callbacks=[self._queue_depth_callback],
            description="Runnable pending processing jobs",
        )
        meter.create_observable_gauge(
            "reflection_queue_oldest_pending_age_seconds",
            callbacks=[self._queue_age_callback],
            unit="s",
            description="Age of the oldest pending processing job",
        )
        self._entry_eligibility = meter.create_counter(
            "reflection_entry_eligibility_total"
        )
        self._signals = meter.create_counter("reflection_signals_total")
        self._candidates = meter.create_counter("reflection_candidates_total")
        self._validator_discards = meter.create_counter(
            "reflection_validator_discards_total"
        )
        self._api_responses = meter.create_counter("reflection_api_responses_total")
        self._feedback = meter.create_counter("reflection_feedback_total")
        self._review_feedback = meter.create_counter(
            "reflection_review_feedback_total"
        )
        self._synthesis_sections = meter.create_counter(
            "reflection_synthesis_sections_total"
        )
        self._job_retries = meter.create_counter("reflection_job_retries_total")
        self._scheduler = meter.create_counter("reflection_scheduler_users_total")

    def record_job(
        self,
        *,
        job_type: str,
        status: str,
        error_code: str,
        duration_seconds: float,
    ) -> None:
        _require(job_type, JOB_TYPES, "job type")
        _require(status, JOB_STATUSES, "job status")
        _require(error_code, JOB_ERROR_CODES, "error code")
        if duration_seconds < 0:
            raise ValueError("job duration is invalid")
        if self._jobs is not None:
            assert self._job_duration is not None
            self._jobs.add(
                1,
                {"type": job_type, "status": status, "error_code": error_code},
            )
            self._job_duration.record(duration_seconds, {"type": job_type})

    def record_entry_analysis(
        self,
        *,
        result: str,
        kind: str,
        signal_types: Sequence[str],
    ) -> None:
        _require(result, ELIGIBILITY_RESULTS, "eligibility result")
        _require(kind, ENTRY_KINDS, "entry kind")
        for signal_type in signal_types:
            _require(signal_type, SIGNAL_TYPES, "signal type")
        if self._entry_eligibility is not None:
            assert self._signals is not None
            self._entry_eligibility.add(1, {"result": result, "kind": kind})
            for signal_type in signal_types:
                self._signals.add(1, {"signal_type": signal_type})

    def record_candidate(self, *, pattern_type: str, outcome: str) -> None:
        _require(pattern_type, PATTERN_TYPES, "pattern type")
        _require(outcome, CANDIDATE_OUTCOMES, "candidate outcome")
        if self._candidates is not None:
            self._candidates.add(
                1, {"pattern_type": pattern_type, "outcome": outcome}
            )

    def record_validator_discard(self, *, reason_code: str) -> None:
        _require(reason_code, VALIDATOR_REASON_CODES, "validator reason code")
        if self._validator_discards is not None:
            self._validator_discards.add(1, {"reason_code": reason_code})

    def record_api_response(
        self, *, reflection_state: str, processing_state: str
    ) -> None:
        _require(reflection_state, REFLECTION_STATES, "reflection state")
        _require(processing_state, PROCESSING_STATES, "processing state")
        if self._api_responses is not None:
            self._api_responses.add(
                1,
                {
                    "reflection_state": reflection_state,
                    "processing_state": processing_state,
                },
            )

    def record_feedback(self, *, response: str) -> None:
        _require(response, FEEDBACK_RESPONSES, "feedback response")
        if self._feedback is not None:
            self._feedback.add(1, {"response": response})

    def record_review_feedback(
        self,
        *,
        scope: str,
        evidence_weight: float,
        outcome: str,
    ) -> None:
        _require(scope, REVIEW_SCOPES, "review scope")
        _require(outcome, REVIEW_FEEDBACK_OUTCOMES, "review feedback outcome")
        if (
            isinstance(evidence_weight, bool)
            or evidence_weight not in REVIEW_WEIGHT_BUCKETS
        ):
            raise ValueError("review evidence weight is invalid")
        if self._review_feedback is not None:
            self._review_feedback.add(
                1,
                {
                    "scope": scope,
                    "weight_bucket": REVIEW_WEIGHT_BUCKETS[evidence_weight],
                    "outcome": outcome,
                },
            )

    def record_synthesis_section(
        self,
        *,
        pattern_type: str,
        execution_mode: str,
        outcome: str,
    ) -> None:
        _require(pattern_type, PATTERN_TYPES, "pattern type")
        _require(execution_mode, SYNTHESIS_EXECUTION_MODES, "execution mode")
        _require(outcome, SYNTHESIS_SECTION_OUTCOMES, "synthesis section outcome")
        if self._synthesis_sections is not None:
            self._synthesis_sections.add(
                1,
                {
                    "pattern_type": pattern_type,
                    "execution_mode": execution_mode,
                    "outcome": outcome,
                },
            )

    def record_job_retry(self, *, job_type: str, outcome: str) -> None:
        _require(job_type, JOB_TYPES, "job type")
        _require(outcome, JOB_RETRY_OUTCOMES, "job retry outcome")
        if self._job_retries is not None:
            self._job_retries.add(
                1,
                {"type": job_type, "outcome": outcome},
            )

    def record_scheduler(self, *, checked: int, eligible: int, enqueued: int) -> None:
        if any(value < 0 for value in (checked, eligible, enqueued)):
            raise ValueError("scheduler counts are invalid")
        if self._scheduler is not None:
            for outcome, value in (
                ("checked", checked),
                ("eligible", eligible),
                ("enqueued", enqueued),
            ):
                self._scheduler.add(value, {"outcome": outcome})

    def observe_queue(self, observations: Sequence[QueueObservation]) -> None:
        normalized: dict[str, QueueObservation] = {}
        for item in observations:
            _require(item.job_type, JOB_TYPES, "job type")
            if item.queue_depth < 0 or item.oldest_pending_seconds < 0:
                raise ValueError("queue observation is invalid")
            normalized[item.job_type] = item
        if set(normalized) != JOB_TYPES:
            raise ValueError("queue observation must cover every job type")
        with self._queue_lock:
            self._queue = normalized

    @contextmanager
    def model_span(
        self,
        *,
        role: str,
        model_id: str,
        prompt_version: str,
    ) -> Iterator[Any]:
        _require(
            role,
            frozenset({"entry_analysis", "embedding", "synthesis", "critic"}),
            "model role",
        )
        _require_token(model_id, "model ID")
        _require_token(prompt_version, "prompt version")
        with self._tracer.start_as_current_span(
            "reflection.model.attempt",
            attributes={
                "orion.model.role": role,
                "orion.model.id": model_id,
                "orion.prompt.version": prompt_version,
            },
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            yield span

    @staticmethod
    def finish_model_span(
        span: Any,
        *,
        status: str,
        duration_ms: int,
        input_tokens: int,
        cached_input_tokens: int,
        cache_write_input_tokens: int,
        output_tokens: int,
        reasoning_output_tokens: int,
        retry_class: str,
        service_tier: str,
    ) -> None:
        _require(status, frozenset({"success", "invalid", "failed"}), "model status")
        _require(
            retry_class,
            frozenset({"none", "retryable", "terminal"}),
            "retry class",
        )
        if min(
            duration_ms,
            input_tokens,
            cached_input_tokens,
            cache_write_input_tokens,
            output_tokens,
            reasoning_output_tokens,
        ) < 0:
            raise ValueError("model attempt measurement is invalid")
        span.set_attribute("orion.model.status", status)
        span.set_attribute("orion.model.duration_ms", duration_ms)
        span.set_attribute("orion.model.input_tokens", input_tokens)
        span.set_attribute("orion.model.cached_input_tokens", cached_input_tokens)
        span.set_attribute(
            "orion.model.cache_write_input_tokens", cache_write_input_tokens
        )
        span.set_attribute("orion.model.output_tokens", output_tokens)
        span.set_attribute(
            "orion.model.reasoning_output_tokens", reasoning_output_tokens
        )
        span.set_attribute("orion.model.retry_class", retry_class)
        span.set_attribute("orion.model.service_tier", service_tier)

    def _queue_depth_callback(self, _options: Any) -> list[Observation]:
        with self._queue_lock:
            return [
                Observation(item.queue_depth, {"type": item.job_type})
                for item in self._queue.values()
            ]

    def _queue_age_callback(self, _options: Any) -> list[Observation]:
        with self._queue_lock:
            return [
                Observation(item.oldest_pending_seconds, {"type": item.job_type})
                for item in self._queue.values()
            ]


@dataclass(frozen=True, slots=True)
class ModelTokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0


def token_usage(response: Any) -> ModelTokenUsage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return ModelTokenUsage()
    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    return ModelTokenUsage(
        input_tokens=_nonnegative_usage(getattr(usage, "input_tokens", 0)),
        cached_input_tokens=_usage_detail(input_details, "cached_tokens"),
        cache_write_input_tokens=_usage_detail(
            input_details, "cache_write_tokens"
        ),
        output_tokens=_nonnegative_usage(getattr(usage, "output_tokens", 0)),
        reasoning_output_tokens=_usage_detail(output_details, "reasoning_tokens"),
    )


def token_counts(response: Any) -> tuple[int, int]:
    """Return aggregate token counts for compatibility with older callers."""

    usage = token_usage(response)
    return usage.input_tokens, usage.output_tokens


def configure_reflection_telemetry(
    settings: Settings,
) -> tuple[ReflectionTelemetry, MeterProvider | None]:
    if not settings.OTEL_ENABLED:
        return ReflectionTelemetry(), None
    exporter = OTLPMetricExporter(
        endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT.get_secret_value(),
        insecure=False,
    )
    provider = MeterProvider(
        metric_readers=[PeriodicExportingMetricReader(exporter)],
        resource=Resource.create({"service.name": settings.OTEL_SERVICE_NAME}),
    )
    return ReflectionTelemetry(meter_provider=provider), provider


def _nonnegative_usage(value: Any) -> int:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else 0
    )


def _usage_detail(details: Any, name: str) -> int:
    if isinstance(details, dict):
        return _nonnegative_usage(details.get(name, 0))
    return _nonnegative_usage(getattr(details, name, 0))


def _require(value: str, allowed: frozenset[str], label: str) -> None:
    if value not in allowed:
        raise ValueError(f"{label} is invalid")


def _require_token(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{label} is invalid")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-"
    if any(character not in allowed for character in value):
        raise ValueError(f"{label} is invalid")
