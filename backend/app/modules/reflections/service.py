from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Mapping
from datetime import date, datetime, timedelta
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from app.modules.reflection_engine.schemas import (
    HiddenDriverStructure,
    InnerTensionStructure,
    RecurringLoopStructure,
)
from app.modules.reflections.repository import (
    ReflectionResourceNotFoundError,
    ReflectionsRepository,
)
from app.modules.reflections.schemas import (
    AnalysisBasis,
    AvailableHiddenDriver,
    AvailableInnerTensions,
    AvailableRecurringLoop,
    EvidenceItem,
    FeedbackResult,
    InnerTension,
    LoopStep,
    ReasonCode,
    ReflectionData,
    ReflectionRange,
    ReflectionResponse,
    SnapshotMetadata,
)
from app.modules.reflections.types import FeedbackCommand, ReflectionQuery
from app.modules.reflections.views import insufficient
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.exceptions.domain import DomainError
from app.shared.security.encryption import ContentCipher


NO_STORE_HEADERS = {"Cache-Control": "private, no-store"}
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


class ReflectionsService:
    def __init__(
        self,
        *,
        repository: ReflectionsRepository,
        cipher: ContentCipher,
        enabled: bool,
        allowed_user_ids: Collection[UUID],
        basis_days: int = 90,
    ) -> None:
        if basis_days != 90:
            raise ValueError("the MVP reflection basis must be exactly 90 days")
        self._repository = repository
        self._cipher = cipher
        self._enabled = enabled
        self._allowed_user_ids = frozenset(allowed_user_ids)

    def read(
        self,
        *,
        query: ReflectionQuery,
        uow: UnitOfWorkFactory,
    ) -> ReflectionResponse:
        self._require_enabled(query.user_id)
        with uow.for_user(query.user_id) as work:
            raw = self._repository.load_aggregate(work.session, user_id=query.user_id)
        return self._build_response(query=query, raw=raw)

    def save_feedback(
        self,
        *,
        command: FeedbackCommand,
        uow: UnitOfWorkFactory,
    ) -> FeedbackResult:
        self._require_enabled(command.user_id)
        try:
            with uow.for_user(command.user_id) as work:
                saved = self._repository.put_feedback(
                    work.session,
                    user_id=command.user_id,
                    snapshot_id=command.snapshot_id,
                    insight_id=command.insight_id,
                    response=command.response,
                )
        except ReflectionResourceNotFoundError as exc:
            raise DomainError(
                404,
                "NOT_FOUND",
                "The requested resource was not found.",
                headers=NO_STORE_HEADERS,
            ) from exc
        return FeedbackResult(
            snapshot_id=saved.snapshot_id,
            insight_id=saved.insight_id,
            response=saved.response,
            updated_at=saved.updated_at,
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
        latest_accepted = _nonnegative_int(
            state.get("latest_accepted_source_version", 0),
            "latest accepted source version",
        )
        last_error = state.get("last_processing_error_code")
        if last_error is not None and not isinstance(last_error, str):
            raise ValueError("reflection processing error state is invalid")
        job_status = job.get("status")
        if job_status not in {None, "pending", "running", "completed", "failed"}:
            raise ValueError("reflection job status is invalid")
        failed = job_status == "failed" or last_error is not None
        pending = job_status in {"pending", "running"}

        if snapshot_raw is None:
            if failed:
                raise DomainError(
                    503,
                    "SERVICE_UNAVAILABLE",
                    "The service is temporarily unavailable.",
                    details={
                        "reflectionState": "technical_failure",
                        "processingState": "failed",
                    },
                    headers=NO_STORE_HEADERS,
                )
            reflection_state = (
                "first_reflection_pending"
                if pending or latest_accepted > 0
                else "insufficient_reflective_content"
            )
            processing_state = (
                "pending" if reflection_state == "first_reflection_pending" else "idle"
            )
            basis = self._analysis_basis(
                _required_mapping(raw.get("current_basis"), "current basis"),
                query.range,
            )
            return ReflectionResponse(
                range=query.range,
                reflection_state=reflection_state,
                processing_state=processing_state,
                snapshot=None,
                analysis_basis=basis,
                data=_empty_data(),
            )

        snapshot_source = _positive_int(
            snapshot_raw.get("source_version"), "snapshot source version"
        )
        stored_status = snapshot_raw.get("status")
        if stored_status not in {"available", "stale"}:
            raise ValueError("snapshot status is invalid")
        newer_entries = latest_accepted > snapshot_source
        stale = failed or pending or newer_entries or stored_status == "stale"
        reflection_state = "stale" if stale else "available"
        processing_state = "failed" if failed else "pending" if stale else "idle"
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
        feedback: Mapping[UUID, str],
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
        feedback: Mapping[UUID, str],
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
        common = {
            "id": insight_id,
            "confidence": confidence,
            "score": score,
            "evidence": public_evidence,
            "feedback": feedback.get(insight_id),
        }
        if pattern_type == "hidden_driver":
            value = HiddenDriverStructure.model_validate(structure)
            drivers = list(
                dict.fromkeys(
                    item.interpretation
                    for signal_id, role, item in all_evidence
                    if role == "supporting"
                )
            )[:5]
            return AvailableHiddenDriver(
                **common,
                statement=value.statement,
                underlying_need=value.underlying_need,
                drivers=drivers or [value.underlying_need],
            )
        if pattern_type == "recurring_loop":
            value = RecurringLoopStructure.model_validate(structure)
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
                for ordinal, step in enumerate(value.steps)
            ]
            if value.protection is None or value.interruption is None:
                raise ValueError("published loop display fields are unavailable")
            return AvailableRecurringLoop(
                **common,
                title=value.title,
                description=value.description,
                steps=steps,
                protection=value.protection,
                interruption=value.interruption,
            )
        value = InnerTensionStructure.model_validate(structure)
        return InnerTension(
            **common,
            left_title=value.left_need,
            left_body=value.left_statement,
            right_title=value.right_need,
            right_body=value.right_statement,
            integration=value.integration,
            dates=sorted({item.entry_date for item in public_evidence}),
        )


def _empty_data() -> ReflectionData:
    return ReflectionData(
        hidden_driver=insufficient("NOT_ENOUGH_REFLECTIVE_CONTENT"),
        recurring_loop=insufficient("LOOP_NOT_REPEATED"),
        inner_tensions=insufficient("BOTH_SIDES_NOT_SUPPORTED"),
    )


def _range_bounds(
    *,
    basis_start: date | None,
    basis_end: date | None,
    selected_range: ReflectionRange,
) -> tuple[date | None, date | None]:
    if basis_start is None or basis_end is None:
        return None, None
    if selected_range == "all":
        return basis_start, basis_end
    days = 7 if selected_range == "7d" else 30
    return max(basis_start, basis_end - timedelta(days=days - 1)), basis_end


def _feedback_map(value: object) -> dict[UUID, str]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise ValueError("reflection feedback payload is invalid")
    result: dict[UUID, str] = {}
    for item in value:
        row = _required_mapping(item, "reflection feedback")
        response = row.get("response")
        if response not in {"resonates", "partly", "rejected"}:
            raise ValueError("reflection feedback response is invalid")
        result[UUID(str(row.get("insight_id")))] = cast(str, response)
    return result


def _first(value: list[Mapping[str, object]] | None) -> Mapping[str, object] | None:
    return value[0] if value else None


def _required_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} is invalid")
    return cast(Mapping[str, object], value)


def _optional_mapping(value: object, name: str) -> Mapping[str, object] | None:
    if value is None:
        return None
    return _required_mapping(value, name)


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} is invalid")
    return value


def _positive_int(value: object, name: str) -> int:
    result = _nonnegative_int(value, name)
    if result < 1:
        raise ValueError(f"{name} is invalid")
    return result


def _date(value: object, name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{name} is invalid") from exc
    raise ValueError(f"{name} is invalid")


def _optional_date(value: object, name: str) -> date | None:
    return None if value is None else _date(value, name)


def _datetime(value: object, name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{name} is invalid") from exc
    raise ValueError(f"{name} is invalid")
