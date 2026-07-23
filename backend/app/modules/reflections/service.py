from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Collection, Mapping
from datetime import date
from typing import Any, TypedDict, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from app.modules.reflection_engine.schemas import (
    HiddenDriverStructure,
    InnerTensionStructure,
    RecurringLoopStructure,
)
from app.modules.reflections.aggregate import (
    _date,
    _datetime,
    _feedback_map,
    _first,
    _nonnegative_int,
    _optional_date,
    _optional_mapping,
    _positive_int,
    _range_bounds,
    _required_mapping,
)
from app.modules.reflections.repository import (
    ReflectionsRepository,
)
from app.modules.reflections.schemas import (
    AnalysisBasis,
    AvailableHiddenDriver,
    AvailableInnerTensions,
    AvailableRecurringLoop,
    Confidence,
    EvidenceItem,
    FeedbackResponse,
    FeedbackResult,
    InnerTension,
    LoopStep,
    ReasonCode,
    ReflectionData,
    ReflectionRange,
    ReflectionResponse,
    RecalculationResponse,
    SnapshotMetadata,
)
from app.modules.reflections.state import PersistedReflectionState
from app.modules.reflections.types import FeedbackCommand, ReflectionQuery
from app.modules.reflections.views import insufficient, processing, unavailable
from app.modules.review.service import ReviewService
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.exceptions.domain import DomainError
from app.shared.observability.logging import safe_log
from app.shared.observability.reflection import ReflectionTelemetry
from app.shared.security.encryption import ContentCipher


NO_STORE_HEADERS = {"Cache-Control": "private, no-store"}
UNAVAILABLE_HEADERS = {**NO_STORE_HEADERS, "Retry-After": "60"}
logger = logging.getLogger("orion.reflections.service")
PATTERN_TYPES = frozenset({"hidden_driver", "recurring_loop", "inner_tension"})
REASON_CODES = frozenset(
    {
        "NOT_ENOUGH_REFLECTIVE_CONTENT",
        "DRIVER_NOT_REPEATED",
        "LOOP_NOT_REPEATED",
        "BOTH_SIDES_NOT_SUPPORTED",
        "INSUFFICIENT_EVIDENCE",
    }
)


class _CommonInsightFields(TypedDict):
    id: UUID
    confidence: Confidence
    score: float
    evidence_entry_count: int
    evidence: list[EvidenceItem]
    feedback: FeedbackResponse | None


class ReflectionsService:
    def __init__(
        self,
        *,
        repository: ReflectionsRepository,
        review_service: ReviewService,
        cipher: ContentCipher,
        enabled: bool,
        recalculation_enabled: bool,
        allowed_user_ids: Collection[UUID],
        basis_days: int = 90,
        telemetry: ReflectionTelemetry | None = None,
    ) -> None:
        if basis_days != 90:
            raise ValueError("the MVP reflection basis must be exactly 90 days")
        self._repository = repository
        self._review_service = review_service
        self._cipher = cipher
        self._enabled = enabled
        self._recalculation_enabled = recalculation_enabled
        self._allowed_user_ids = frozenset(allowed_user_ids)
        self._telemetry = telemetry or ReflectionTelemetry()

    def read(
        self,
        *,
        query: ReflectionQuery,
        uow: UnitOfWorkFactory,
    ) -> ReflectionResponse:
        try:
            self._require_enabled(query.user_id)
            with uow.for_user(query.user_id) as work:
                raw = self._repository.load_aggregate(
                    work.session, user_id=query.user_id
                )
            result = self._build_response(query=query, raw=raw)
        except DomainError as exc:
            reflection_state = str(
                exc.details.get("reflectionState", "unavailable")
            )
            processing_state = str(
                exc.details.get("processingState", "unavailable")
            )
            self._record_api_response(
                reflection_state=reflection_state,
                processing_state=processing_state,
                status_code=exc.status_code,
            )
            raise
        except Exception:
            self._record_api_response(
                reflection_state="technical_failure",
                processing_state="failed",
                status_code=500,
            )
            raise
        self._record_api_response(
            reflection_state=result.reflection_state,
            processing_state=result.processing_state,
            status_code=200,
        )
        return result

    def save_feedback(
        self,
        *,
        command: FeedbackCommand,
        uow: UnitOfWorkFactory,
    ) -> FeedbackResult:
        self._require_enabled(command.user_id)
        item = self._review_service.save_legacy_pattern_feedback(
            user_id=command.user_id,
            snapshot_id=command.snapshot_id,
            insight_id=command.insight_id,
            response=command.response,
            uow=uow,
        )
        if item.feedback is None:
            raise RuntimeError("saved pattern feedback is unavailable")
        result = FeedbackResult(
            snapshot_id=command.snapshot_id,
            insight_id=command.insight_id,
            response=command.response,
            updated_at=item.feedback.updated_at,
        )
        self._telemetry.record_feedback(response=result.response)
        safe_log(
            logger,
            "reflection_feedback_saved",
            snapshot_id=result.snapshot_id,
            response=result.response,
            status_code=200,
        )
        return result

    def request_recalculation(
        self,
        *,
        user_id: UUID,
        uow: UnitOfWorkFactory,
    ) -> RecalculationResponse:
        self._require_enabled(user_id)
        if not self._recalculation_enabled:
            raise DomainError(
                503,
                "REFLECTION_RECALCULATION_UNAVAILABLE",
                "Reflection recalculation is temporarily unavailable.",
                headers=UNAVAILABLE_HEADERS,
            )
        try:
            with uow.for_user(user_id) as work:
                result = self._repository.request_recalculation(
                    work.session,
                    user_id=user_id,
                )
        except Exception as exc:
            raise DomainError(
                503,
                "REFLECTION_RECALCULATION_UNAVAILABLE",
                "Reflection recalculation is temporarily unavailable.",
                headers=UNAVAILABLE_HEADERS,
            ) from exc
        if result.outcome == "already_current":
            raise DomainError(
                409,
                "REFLECTION_ALREADY_CURRENT",
                "The reflection is already current.",
                headers=NO_STORE_HEADERS,
            )
        if result.outcome == "not_eligible":
            raise DomainError(
                409,
                "REFLECTION_NOT_ELIGIBLE",
                "There is not enough reflective evidence to recalculate yet.",
                details={
                    "valid_entry_count": result.valid_entry_count,
                    "distinct_entry_dates": result.distinct_entry_dates,
                    "reflective_word_count": result.reflective_word_count,
                    "reason_codes": ["MINIMUM_BASIS_NOT_MET"],
                },
                headers=NO_STORE_HEADERS,
            )
        if result.outcome == "unavailable" or result.job_id is None:
            raise DomainError(
                503,
                "REFLECTION_RECALCULATION_UNAVAILABLE",
                "Reflection recalculation is temporarily unavailable.",
                headers=UNAVAILABLE_HEADERS,
            )
        safe_log(
            logger,
            "reflection_synthesis_requested",
            job_id=result.job_id,
            source_version=result.source_version,
        )
        return RecalculationResponse(job_id=result.job_id)

    def _record_api_response(
        self,
        *,
        reflection_state: str,
        processing_state: str,
        status_code: int,
    ) -> None:
        self._telemetry.record_api_response(
            reflection_state=reflection_state,
            processing_state=processing_state,
        )
        safe_log(
            logger,
            "reflection_api_response",
            reflection_state=reflection_state,
            processing_state=processing_state,
            status_code=status_code,
        )

    def _require_enabled(self, user_id: UUID) -> None:
        if not self._enabled or user_id not in self._allowed_user_ids:
            raise DomainError(
                503,
                "SERVICE_UNAVAILABLE",
                "The service is temporarily unavailable.",
                headers=NO_STORE_HEADERS,
            )

    def _build_response(
        self,
        *,
        query: ReflectionQuery,
        raw: Mapping[str, object],
    ) -> ReflectionResponse:
        snapshot_raw = _optional_mapping(raw.get("snapshot"), "snapshot")
        state = _optional_mapping(raw.get("state"), "state") or {}
        job = _optional_mapping(raw.get("job"), "job") or {}
        persisted_state = PersistedReflectionState.parse(state=state, job=job)

        if snapshot_raw is None:
            basis = self._analysis_basis(
                _required_mapping(raw.get("current_basis"), "current basis"),
                query.range,
            )
            if persisted_state.failed:
                return ReflectionResponse(
                    range=query.range,
                    reflection_state="technical_failure",
                    processing_state="failed",
                    snapshot=None,
                    analysis_basis=basis,
                    data=_unavailable_data(),
                )
            reflection_state, processing_state = persisted_state.without_snapshot()
            data = (
                _processing_data()
                if processing_state == "pending"
                else _insufficient_data()
            )
            return ReflectionResponse(
                range=query.range,
                reflection_state=reflection_state,
                processing_state=processing_state,
                snapshot=None,
                analysis_basis=basis,
                data=data,
            )

        snapshot_source, reflection_state, processing_state, stale = (
            persisted_state.with_snapshot(snapshot_raw)
        )
        basis = self._analysis_basis(snapshot_raw, query.range)
        evidence_by_insight = self._evidence(
            query=query,
            raw=raw,
            range_from=basis.current_range_from,
            range_to=basis.current_range_to,
        )
        feedback = _feedback_map(raw.get("feedback"))
        data = self._data(
            query=query,
            raw=raw,
            evidence_by_insight=evidence_by_insight,
            feedback=feedback,
        )
        return ReflectionResponse(
            range=query.range,
            reflection_state=cast(Any, reflection_state),
            processing_state=cast(Any, processing_state),
            snapshot=SnapshotMetadata(
                id=UUID(str(snapshot_raw.get("id"))),
                version=_positive_int(snapshot_raw.get("version"), "snapshot version"),
                generated_at=_datetime(snapshot_raw.get("created_at"), "snapshot creation"),
                source_version=snapshot_source,
                is_stale=stale,
            ),
            analysis_basis=basis,
            data=data,
        )

    def _analysis_basis(
        self,
        raw: Mapping[str, object],
        selected_range: ReflectionRange,
    ) -> AnalysisBasis:
        basis_start = _optional_date(raw.get("basis_start"), "basis start")
        basis_end = _optional_date(raw.get("basis_end"), "basis end")
        if (basis_start is None) != (basis_end is None):
            raise ValueError("reflection basis dates are invalid")
        if basis_start is not None and basis_start > cast(date, basis_end):
            raise ValueError("reflection basis window is invalid")
        range_from, range_to = _range_bounds(
            basis_start=basis_start,
            basis_end=basis_end,
            selected_range=selected_range,
        )
        excluded = raw.get("excluded_reasons")
        excluded_reasons = None
        if excluded is not None:
            if not isinstance(excluded, dict) or any(
                not isinstance(key, str)
                or isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
                for key, value in excluded.items()
            ):
                raise ValueError("reflection exclusion summary is invalid")
            excluded_reasons = dict(sorted(excluded.items()))
        return AnalysisBasis(
            valid_entry_count=_nonnegative_int(
                raw.get("valid_entry_count"), "valid entry count"
            ),
            excluded_entry_count=_nonnegative_int(
                raw.get("excluded_entry_count"), "excluded entry count"
            ),
            distinct_entry_dates=_nonnegative_int(
                raw.get("distinct_entry_dates"), "distinct entry dates"
            ),
            reflective_word_count=_nonnegative_int(
                raw.get("reflective_word_count"), "reflective word count"
            ),
            current_range_from=range_from,
            current_range_to=range_to,
            excluded_reasons=excluded_reasons,
        )

    def _evidence(
        self,
        *,
        query: ReflectionQuery,
        raw: Mapping[str, object],
        range_from: date | None,
        range_to: date | None,
    ) -> dict[UUID, list[tuple[UUID, str, EvidenceItem]]]:
        rows = raw.get("evidence", [])
        if not isinstance(rows, list):
            raise ValueError("reflection evidence payload is invalid")
        result: dict[UUID, list[tuple[UUID, str, EvidenceItem]]] = defaultdict(list)
        entry_cache: dict[UUID, str] = {}
        signal_cache: dict[UUID, Mapping[str, object]] = {}
        for raw_row in rows:
            row = _required_mapping(raw_row, "evidence row")
            insight_id = UUID(str(row.get("insight_id")))
            signal_id = UUID(str(row.get("signal_id")))
            entry_id = UUID(str(row.get("entry_id")))
            role = row.get("evidence_role")
            if role not in {"supporting", "counter"}:
                raise ValueError("reflection evidence role is invalid")
            entry_date = _date(row.get("entry_date"), "evidence entry date")
            if (
                range_from is not None
                and range_to is not None
                and not (range_from <= entry_date <= range_to)
            ):
                continue
            if entry_id not in entry_cache:
                envelope = row.get("entry_content_envelope")
                if not isinstance(envelope, dict):
                    raise ValueError("entry evidence envelope is invalid")
                entry_cache[entry_id] = self._cipher.decrypt(
                    envelope,
                    user_id=query.user_id,
                    record_id=entry_id,
                )
            if signal_id not in signal_cache:
                envelope = row.get("signal_payload_envelope")
                if not isinstance(envelope, dict):
                    raise ValueError("signal evidence envelope is invalid")
                payload = self._cipher.decrypt_json(
                    envelope,
                    user_id=query.user_id,
                    record_id=signal_id,
                    purpose="entry_signal_payload",
                )
                signal_cache[signal_id] = _required_mapping(
                    payload, "signal evidence payload"
                )
            signal = signal_cache[signal_id]
            quote = signal.get("source_quote")
            interpretation = signal.get("interpretation")
            if not isinstance(quote, str) or not quote or not isinstance(
                interpretation, str
            ) or not interpretation:
                raise ValueError("signal evidence text is invalid")
            start = _nonnegative_int(row.get("source_start"), "evidence start")
            end = _positive_int(row.get("source_end"), "evidence end")
            text = entry_cache[entry_id]
            if start >= end or end > len(text) or text[start:end] != quote:
                raise ValueError("persisted reflection evidence is invalid")
            themes = row.get("themes", [])
            if not isinstance(themes, list) or any(
                not isinstance(item, str) for item in themes
            ):
                raise ValueError("reflection evidence themes are invalid")
            source_label = (
                "Voice entry" if row.get("input_type") == "audio" else "Journal entry"
            )
            item = EvidenceItem(
                id=uuid5(
                    NAMESPACE_URL,
                    f"orion-reflection-evidence:{insight_id}:{signal_id}:{role}",
                ),
                entry_date=entry_date,
                source_label=source_label,
                quote=quote,
                interpretation=interpretation,
                theme=themes[0] if themes else None,
                supports=(
                    "Supporting evidence"
                    if role == "supporting"
                    else "Counterevidence"
                ),
            )
            result[insight_id].append((signal_id, cast(str, role), item))
        return result

    def _data(
        self,
        *,
        query: ReflectionQuery,
        raw: Mapping[str, object],
        evidence_by_insight: Mapping[UUID, list[tuple[UUID, str, EvidenceItem]]],
        feedback: Mapping[UUID, FeedbackResponse],
    ) -> ReflectionData:
        rows = raw.get("insights", [])
        if not isinstance(rows, list):
            raise ValueError("reflection insights payload is invalid")
        by_type: dict[str, list[Mapping[str, object]]] = defaultdict(list)
        for item in rows:
            row = _required_mapping(item, "reflection insight")
            pattern_type = row.get("pattern_type")
            if pattern_type not in PATTERN_TYPES:
                raise ValueError("reflection insight type is invalid")
            by_type[cast(str, pattern_type)].append(row)

        hidden = self._single_insight(
            query=query,
            row=_first(by_type.get("hidden_driver")),
            pattern_type="hidden_driver",
            evidence_by_insight=evidence_by_insight,
            feedback=feedback,
        )
        loop = self._single_insight(
            query=query,
            row=_first(by_type.get("recurring_loop")),
            pattern_type="recurring_loop",
            evidence_by_insight=evidence_by_insight,
            feedback=feedback,
        )
        tension_rows = by_type.get("inner_tension", [])
        available_tensions: list[InnerTension] = []
        tension_insufficient = None
        for row in tension_rows:
            built = self._single_insight(
                query=query,
                row=row,
                pattern_type="inner_tension",
                evidence_by_insight=evidence_by_insight,
                feedback=feedback,
            )
            if isinstance(built, InnerTension):
                available_tensions.append(built)
            else:
                tension_insufficient = built
        inner = (
            AvailableInnerTensions(tensions=available_tensions)
            if available_tensions
            else tension_insufficient or insufficient("BOTH_SIDES_NOT_SUPPORTED")
        )
        return ReflectionData(
            hidden_driver=cast(Any, hidden),
            recurring_loop=cast(Any, loop),
            inner_tensions=cast(Any, inner),
        )

    def _single_insight(
        self,
        *,
        query: ReflectionQuery,
        row: Mapping[str, object] | None,
        pattern_type: str,
        evidence_by_insight: Mapping[UUID, list[tuple[UUID, str, EvidenceItem]]],
        feedback: Mapping[UUID, FeedbackResponse],
    ) -> AvailableHiddenDriver | AvailableRecurringLoop | InnerTension | object:
        if row is None:
            default = {
                "hidden_driver": "DRIVER_NOT_REPEATED",
                "recurring_loop": "LOOP_NOT_REPEATED",
                "inner_tension": "BOTH_SIDES_NOT_SUPPORTED",
            }[pattern_type]
            return insufficient(cast(ReasonCode, default))
        status = row.get("status")
        if status == "insufficient_evidence":
            reason = row.get("reason_code")
            if reason not in REASON_CODES:
                raise ValueError("reflection insufficiency reason is invalid")
            return insufficient(cast(ReasonCode, reason))
        if status != "available":
            raise ValueError("reflection insight status is invalid")
        insight_id = UUID(str(row.get("id")))
        envelope = row.get("payload_envelope")
        if not isinstance(envelope, dict):
            raise ValueError("reflection insight envelope is invalid")
        payload = self._cipher.decrypt_json(
            envelope,
            user_id=query.user_id,
            record_id=insight_id,
            purpose="reflection_insight_payload",
        )
        payload = _required_mapping(payload, "reflection insight payload")
        if set(payload) != {"version", "pattern_type", "structure"}:
            raise ValueError("reflection insight payload shape is invalid")
        if payload.get("version") != 1 or payload.get("pattern_type") != pattern_type:
            raise ValueError("reflection insight payload identity is invalid")
        structure = _required_mapping(payload.get("structure"), "insight structure")
        confidence = row.get("confidence_label")
        if confidence not in {"preliminary", "emerging", "recurring"}:
            raise ValueError("reflection confidence is invalid")
        score = row.get("score")
        all_evidence = evidence_by_insight.get(insight_id, [])
        public_evidence = [item[2] for item in all_evidence]
        common: _CommonInsightFields = {
            "id": insight_id,
            "confidence": cast(Confidence, confidence),
            "score": cast(float, score),
            "evidence_entry_count": _positive_int(
                row.get("evidence_entry_count"), "evidence entry count"
            ),
            "evidence": public_evidence,
            "feedback": feedback.get(insight_id),
        }
        if pattern_type == "hidden_driver":
            hidden_driver = HiddenDriverStructure.model_validate(structure)
            drivers = list(
                dict.fromkeys(
                    item.interpretation
                    for signal_id, role, item in all_evidence
                    if role == "supporting"
                )
            )[:5]
            return AvailableHiddenDriver(
                **common,
                statement=hidden_driver.statement,
                underlying_need=hidden_driver.underlying_need,
                drivers=drivers or [hidden_driver.underlying_need],
            )
        if pattern_type == "recurring_loop":
            recurring_loop = RecurringLoopStructure.model_validate(structure)
            evidence_by_signal = {
                signal_id: item for signal_id, _role, item in all_evidence
            }
            steps = [
                LoopStep(
                    id=uuid5(insight_id, f"loop-step:{ordinal}"),
                    text=step.statement or step.loop_role.replace("_", " "),
                    evidence=[
                        evidence_by_signal[item]
                        for item in step.support_signal_ids
                        if item in evidence_by_signal
                    ],
                )
                for ordinal, step in enumerate(recurring_loop.steps)
            ]
            if recurring_loop.protection is None or recurring_loop.interruption is None:
                raise ValueError("published loop display fields are unavailable")
            return AvailableRecurringLoop(
                **common,
                title=recurring_loop.title,
                description=recurring_loop.description,
                steps=steps,
                protection=recurring_loop.protection,
                interruption=recurring_loop.interruption,
            )
        inner_tension = InnerTensionStructure.model_validate(structure)
        return InnerTension(
            **common,
            left_title=inner_tension.left_need,
            left_body=inner_tension.left_statement,
            right_title=inner_tension.right_need,
            right_body=inner_tension.right_statement,
            integration=inner_tension.integration,
            dates=sorted({item.entry_date for item in public_evidence}),
        )


def _insufficient_data() -> ReflectionData:
    return ReflectionData(
        hidden_driver=insufficient("MINIMUM_BASIS_NOT_MET"),
        recurring_loop=insufficient("MINIMUM_BASIS_NOT_MET"),
        inner_tensions=insufficient("MINIMUM_BASIS_NOT_MET"),
    )


def _processing_data() -> ReflectionData:
    return ReflectionData(
        hidden_driver=processing(),
        recurring_loop=processing(),
        inner_tensions=processing(),
    )


def _unavailable_data() -> ReflectionData:
    return ReflectionData(
        hidden_driver=unavailable(),
        recurring_loop=unavailable(),
        inner_tensions=unavailable(),
    )
