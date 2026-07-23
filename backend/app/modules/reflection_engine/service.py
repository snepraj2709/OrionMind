from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from app.modules.jobs.types import JobClaim
from app.modules.reflection_engine.candidates import (
    SEMANTIC_ANCHOR_BATCH_SIZE as SEMANTIC_ANCHOR_BATCH_SIZE,
    SEMANTIC_NEIGHBOR_TOP_K as SEMANTIC_NEIGHBOR_TOP_K,
    SEMANTIC_SIMILARITY_THRESHOLD as SEMANTIC_SIMILARITY_THRESHOLD,
    CandidateConstructionMixin,
    _semantic_cluster_keys,
)
from app.modules.reflection_engine.errors import SnapshotValidationError
from app.modules.reflection_engine.evidence import EvidenceValidator
from app.modules.reflection_engine.prompts import (
    REFLECTION_SYNTHESIS_PROMPT_VERSION,
    build_reflection_critic_input,
    build_reflection_synthesis_input,
)
from app.modules.reflection_engine.provider import UnavailableReflectionProvider
from app.modules.reflection_engine.repository import ReflectionEngineRepository
from app.modules.reflection_engine.schemas import (
    AnalysisBasis,
    CandidateBatch,
    CandidateSignal,
    ConstructedCandidate,
    HiddenDriverProposal,
    HiddenDriverStructure,
    InnerTensionProposal,
    InnerTensionStructure,
    LoopStepStructure,
    PreviousCandidate,
    RecurringLoopProposal,
    RecurringLoopStructure,
    ReflectionSynthesisOutput,
)
from app.modules.reflection_engine.scoring import overall_basis_eligible
from app.modules.reflection_engine.synthesis import (
    _critic_allows_publication,
    _final_transition_support,
    _references_match,
    _select_snapshot_candidates,
    _select_synthesis_candidates,
    _select_synthesis_support_ids,
    _snapshot_candidate_status,
    critic_required,
)
from app.modules.reflection_engine.types import ReflectionProvider
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.observability.logging import safe_log
from app.shared.observability.reflection import ReflectionTelemetry
from app.shared.security.encryption import ContentCipher


logger = logging.getLogger("orion.reflection.service")
PATTERN_REVIEW_SOURCE_ENTRY_LIMIT = 100


class ReflectionEngineService(CandidateConstructionMixin):
    def __init__(
        self,
        *,
        repository: ReflectionEngineRepository,
        cipher: ContentCipher,
        provider: ReflectionProvider | None = None,
        validator: EvidenceValidator | None = None,
        basis_days: int = 90,
        embedding_model_id: str = "text-embedding-3-small",
        synthesis_model_id: str = "gpt-5.6-terra",
        telemetry: ReflectionTelemetry | None = None,
    ) -> None:
        if basis_days != 90:
            raise ValueError("the MVP reflection basis must be exactly 90 days")
        self._repository = repository
        self._cipher = cipher
        self._provider = provider or UnavailableReflectionProvider()
        self._validator = validator or EvidenceValidator()
        self._basis_days = basis_days
        self._embedding_model_id = embedding_model_id
        self._synthesis_model_id = synthesis_model_id
        self._telemetry = telemetry or ReflectionTelemetry()

    def construct_and_apply(
        self,
        *,
        user_id: UUID,
        source_version: int,
        uow: UnitOfWorkFactory,
    ) -> CandidateBatch:
        with uow.for_worker() as work:
            raw = self._repository.load_candidate_basis(
                work.session,
                user_id=user_id,
                source_version=source_version,
                basis_days=self._basis_days,
            )
        basis, signals, previous = self._materialize_basis(raw, user_id=user_id)
        semantic_neighbors = self._load_semantic_neighbors(
            uow=uow,
            user_id=user_id,
            source_version=source_version,
            signals=signals,
        )
        batch = self.construct_candidates(
            user_id=user_id,
            basis=basis,
            signals=signals,
            previous_candidates=previous,
            semantic_neighbors=semantic_neighbors,
        )
        candidate_rows = [
            self._candidate_row(candidate, user_id=user_id, source_version=source_version)
            for candidate in batch.candidates
        ]
        evidence_rows = [link.model_dump(mode="json") for link in batch.evidence]
        with uow.for_worker() as work:
            self._repository.apply_candidates(
                work.session,
                user_id=user_id,
                source_version=source_version,
                candidates=candidate_rows,
                evidence=evidence_rows,
            )
        return batch

    def run_synthesis_job(
        self,
        *,
        claim: JobClaim,
        worker_id: str,
        uow: UnitOfWorkFactory,
    ) -> UUID:
        if claim.job_type != "reflection_synthesis" or claim.entry_id is not None:
            raise SnapshotValidationError("job is not reflection synthesis")
        if claim.execution_mode not in {"shadow", "publish"}:
            raise SnapshotValidationError("synthesis execution mode is invalid")
        try:
            source_version = int(claim.source_version)
        except ValueError as exc:
            raise SnapshotValidationError("synthesis source version is invalid") from exc
        with uow.for_worker() as work:
            raw = self._repository.load_synthesis_basis(
                work.session,
                claim=claim,
                worker_id=worker_id,
                basis_days=self._basis_days,
            )
        basis, signals, previous = self._materialize_basis(raw, user_id=claim.user_id)
        if basis.source_version != source_version:
            raise SnapshotValidationError("synthesis basis source does not match the job")
        semantic_neighbors = self._load_semantic_neighbors(
            uow=uow,
            user_id=claim.user_id,
            source_version=source_version,
            signals=signals,
        )
        semantic_clusters = _semantic_cluster_keys(signals, semantic_neighbors)
        batch = self.construct_candidates(
            user_id=claim.user_id,
            basis=basis,
            signals=signals,
            previous_candidates=previous,
            semantic_neighbors=semantic_neighbors,
        )
        feedback = self._feedback_qualifications(raw)
        previously_rejected = {
            candidate.id for candidate in previous if candidate.status == "rejected"
        }
        previous_by_id = {candidate.id: candidate for candidate in previous}
        publishable = _select_synthesis_candidates(
            [
                candidate
                for candidate in batch.candidates
                if candidate.publication_gate_passed
                and candidate.status != "rejected"
                and candidate.id not in previously_rejected
            ]
        )
        synthesis_support = {
            candidate.id: _select_synthesis_support_ids(candidate, signals)
            for candidate in publishable
        }
        contexts = {
            str(candidate.id): self._synthesis_candidate_context(
                candidate,
                signals=signals,
                basis_end=basis.basis_end,
                previous_candidate=previous_by_id.get(candidate.id),
                feedback_qualification=feedback.get(str(candidate.id)),
                support_signal_ids=synthesis_support[candidate.id],
            )
            for candidate in publishable
        }
        _, safety_identifier = self._cipher.reflection_fingerprint(
            str(claim.user_id),
            user_id=claim.user_id,
            purpose="safety_identifier",
        )
        if publishable:
            output = self._provider.synthesize(
                payload=build_reflection_synthesis_input(
                    candidates=list(contexts.values()),
                    feedback_qualifications=feedback,
                ),
                safety_identifier=safety_identifier,
            )
            if not isinstance(output, ReflectionSynthesisOutput):
                output = ReflectionSynthesisOutput.model_validate(output)
        else:
            output = ReflectionSynthesisOutput(
                hidden_drivers=[],
                recurring_loops=[],
                inner_tensions=[],
                abstentions=[],
            )

        by_candidate = {candidate.id: candidate for candidate in publishable}
        by_signal = {signal.id: signal for signal in signals}
        final_candidates: list[ConstructedCandidate] = []
        proposals: list[
            HiddenDriverProposal | RecurringLoopProposal | InnerTensionProposal
        ] = [
            *output.hidden_drivers,
            *output.recurring_loops,
            *output.inner_tensions,
        ]
        for proposal in proposals:
            deterministic = by_candidate.get(proposal.candidate_id)
            if deterministic is None:
                self._record_discard("UNKNOWN_CANDIDATE")
                continue
            materialized = self._materialize_proposal(
                deterministic,
                proposal=proposal,
                synthesis_support_signal_ids=synthesis_support[deterministic.id],
            )
            if materialized is None:
                self._record_discard(
                    "EVIDENCE_ROLE_MISMATCH", candidate=deterministic
                )
                continue
            reasons = self._validator.validate_candidate(
                materialized,
                user_id=claim.user_id,
                signals=by_signal,
                basis_start=basis.basis_start,
                basis_end=basis.basis_end,
                expected_counter_signal_ids=materialized.counter_signal_ids,
                transition_support=_final_transition_support(materialized),
                semantic_clusters=semantic_clusters,
            )
            if reasons:
                self._record_discard(reasons[0], candidate=materialized)
                continue
            if critic_required(materialized):
                critique = self._provider.critique(
                    payload=build_reflection_critic_input(
                        candidate=contexts[str(materialized.id)],
                        proposal=proposal.model_dump(mode="json"),
                    ),
                    safety_identifier=safety_identifier,
                )
                if not _critic_allows_publication(critique):
                    self._record_discard(
                        "CRITIC_DISCARDED", candidate=materialized
                    )
                    continue
            final_candidates.append(materialized)

        selected = _select_snapshot_candidates(final_candidates)
        for candidate in selected:
            self._telemetry.record_candidate(
                pattern_type=candidate.pattern_type,
                outcome="selected",
            )
            safe_log(
                logger,
                "reflection_candidate_observed",
                candidate_id=candidate.id,
                pattern_type=candidate.pattern_type,
                outcome="selected",
            )
        selected_ids = {candidate.id for candidate in selected}
        persisted_candidates = [
            _snapshot_candidate_status(candidate, published=candidate.id in selected_ids)
            for candidate in batch.candidates
        ]
        phrased_by_id = {
            candidate.id: _snapshot_candidate_status(candidate, published=True)
            for candidate in selected
        }
        persisted_candidates = [
            phrased_by_id.get(candidate.id, candidate) for candidate in persisted_candidates
        ]
        snapshot, insights, snapshot_evidence = self._snapshot_rows(
            user_id=claim.user_id,
            raw=raw,
            basis=basis,
            candidates=selected,
            signals=by_signal,
        )
        pattern_review_items = self._pattern_review_rows(
            user_id=claim.user_id,
            source_version=source_version,
            candidates=selected,
            signals=by_signal,
        )
        candidate_rows = [
            self._candidate_row(
                candidate,
                user_id=claim.user_id,
                source_version=source_version,
            )
            for candidate in persisted_candidates
        ]
        candidate_evidence = [link.model_dump(mode="json") for link in batch.evidence]
        with uow.for_worker() as work:
            if claim.execution_mode == "shadow":
                return self._repository.complete_shadow(
                    work.session,
                    claim=claim,
                    worker_id=worker_id,
                    candidate_count=len(batch.candidates),
                    selected_count=len(selected),
                    provider_called=bool(publishable),
                )
            return self._repository.apply_snapshot(
                work.session,
                claim=claim,
                worker_id=worker_id,
                snapshot=snapshot,
                candidates=candidate_rows,
                candidate_evidence=candidate_evidence,
                insights=insights,
                snapshot_evidence=snapshot_evidence,
                pattern_review_items=pattern_review_items,
            )

    def _record_discard(
        self,
        reason_code: str,
        *,
        candidate: ConstructedCandidate | None = None,
    ) -> None:
        self._telemetry.record_validator_discard(reason_code=reason_code)
        safe_log(
            logger,
            "reflection_proposal_discarded",
            reason_code=reason_code,
        )
        if candidate is not None:
            self._telemetry.record_candidate(
                pattern_type=candidate.pattern_type,
                outcome="discarded",
            )
            safe_log(
                logger,
                "reflection_candidate_observed",
                candidate_id=candidate.id,
                pattern_type=candidate.pattern_type,
                outcome="discarded",
            )

    @staticmethod
    def _feedback_qualifications(raw: Mapping[str, object]) -> dict[str, str]:
        value = raw.get("feedback_qualifications", {})
        if not isinstance(value, dict) or any(
            not isinstance(key, str) or item != "partly"
            for key, item in value.items()
        ):
            raise SnapshotValidationError("feedback qualification payload is invalid")
        return cast(dict[str, str], value)

    @staticmethod
    def _synthesis_candidate_context(
        candidate: ConstructedCandidate,
        *,
        signals: Sequence[CandidateSignal],
        basis_end: date | None,
        previous_candidate: PreviousCandidate | None,
        feedback_qualification: str | None,
        support_signal_ids: Sequence[UUID],
    ) -> dict[str, object]:
        if basis_end is None:
            raise SnapshotValidationError("synthesis basis end is unavailable")
        by_id = {signal.id: signal for signal in signals}
        evidence = []
        for role, identifiers in (
            ("supporting", support_signal_ids),
            ("counter", candidate.counter_signal_ids),
        ):
            for signal_id in identifiers:
                signal = by_id[signal_id]
                evidence.append(
                    {
                        "signal_id": str(signal.id),
                        "evidence_role": role,
                        "entry_date": signal.entry_date.isoformat(),
                        "signal_type": signal.signal_type,
                        "normalized_label": signal.normalized_label,
                        "interpretation": signal.interpretation,
                        "themes": signal.themes,
                        "need_tags": signal.need_tags,
                        "loop_role": signal.loop_role,
                        "confidence": signal.confidence,
                        "model_confidence": (
                            signal.model_confidence
                            if signal.model_confidence is not None
                            else signal.confidence
                        ),
                        "evidence_weight": signal.evidence_weight,
                        "is_new_since_previous": (
                            previous_candidate is None
                            or signal.analysis_source_version
                            > previous_candidate.last_source_version
                        ),
                    }
                )
        support = [by_id[signal_id] for signal_id in candidate.support_signal_ids]

        def activation(days: int | None) -> dict[str, int]:
            start = (
                date.min if days is None else basis_end - timedelta(days=days - 1)
            )
            selected = [signal for signal in support if signal.entry_date >= start]
            return {
                "supporting_signals": len(selected),
                "supporting_entries": len({signal.entry_id for signal in selected}),
                "supporting_dates": len({signal.entry_date for signal in selected}),
            }

        prior_context = None
        if previous_candidate is not None:
            prior_context = {
                "status": previous_candidate.status,
                "score": previous_candidate.score,
                "last_source_version": previous_candidate.last_source_version,
                "structure": previous_candidate.payload.get("structure"),
                "confidence_label": previous_candidate.payload.get("confidence_label"),
            }
        deterministic_structure = candidate.structure.model_dump(mode="json")
        selected = set(support_signal_ids)
        if isinstance(candidate.structure, InnerTensionStructure):
            deterministic_structure["left_support_signal_ids"] = [
                str(item)
                for item in candidate.structure.left_support_signal_ids
                if item in selected
            ]
            deterministic_structure["right_support_signal_ids"] = [
                str(item)
                for item in candidate.structure.right_support_signal_ids
                if item in selected
            ]
        elif isinstance(candidate.structure, RecurringLoopStructure):
            for raw_step, step in zip(
                deterministic_structure["steps"],
                candidate.structure.steps,
                strict=True,
            ):
                raw_step["support_signal_ids"] = [
                    str(item) for item in step.support_signal_ids if item in selected
                ]
        return {
            "candidate_id": str(candidate.id),
            "pattern_type": candidate.pattern_type,
            "canonical_key": candidate.canonical_key,
            "score": candidate.score,
            "score_components": candidate.score_components.model_dump(mode="json"),
            "deterministic_structure": deterministic_structure,
            "evidence": evidence,
            "range_activation": {
                "7d": activation(7),
                "30d": activation(30),
                "all": activation(None),
            },
            "previous_candidate": prior_context,
            "feedback_qualification": feedback_qualification,
            "review_weight": candidate.review_weight,
        }

    def _materialize_proposal(
        self,
        candidate: ConstructedCandidate,
        *,
        proposal: HiddenDriverProposal | RecurringLoopProposal | InnerTensionProposal,
        synthesis_support_signal_ids: Sequence[UUID],
    ) -> ConstructedCandidate | None:
        structure: (
            HiddenDriverStructure | RecurringLoopStructure | InnerTensionStructure
        )
        expected_evidence = {
            *((item, "supporting") for item in synthesis_support_signal_ids),
            *((item, "counter") for item in candidate.counter_signal_ids),
        }
        if isinstance(proposal, HiddenDriverProposal):
            if not isinstance(candidate.structure, HiddenDriverStructure):
                return None
            if (
                proposal.canonical_need != candidate.structure.canonical_need
                or not _references_match(proposal.evidence, expected_evidence)
            ):
                return None
            structure = candidate.structure.model_copy(
                update={
                    "statement": proposal.statement,
                    "underlying_need": proposal.underlying_need,
                }
            )
        elif isinstance(proposal, RecurringLoopProposal):
            if not isinstance(candidate.structure, RecurringLoopStructure):
                return None
            if (
                proposal.canonical_key != candidate.canonical_key
                or len(proposal.steps) != len(candidate.structure.steps)
                or not _references_match(
                    proposal.counterevidence,
                    {(item, "counter") for item in candidate.counter_signal_ids},
                )
            ):
                return None
            steps: list[LoopStepStructure] = []
            for proposed, deterministic in zip(
                proposal.steps, candidate.structure.steps, strict=True
            ):
                expected = {
                    (item, "supporting")
                    for item in deterministic.support_signal_ids
                    if item in synthesis_support_signal_ids
                }
                if (
                    proposed.loop_role != deterministic.loop_role
                    or not _references_match(proposed.evidence, expected)
                ):
                    return None
                steps.append(
                    deterministic.model_copy(update={"statement": proposed.statement})
                )
            structure = candidate.structure.model_copy(
                update={
                    "title": proposal.title,
                    "description": proposal.description,
                    "steps": steps,
                    "protection": proposal.protection,
                    "interruption": proposal.interruption,
                }
            )
        elif isinstance(proposal, InnerTensionProposal):
            if not isinstance(candidate.structure, InnerTensionStructure):
                return None
            if (
                proposal.left_need != candidate.structure.left_need
                or proposal.right_need != candidate.structure.right_need
                or not _references_match(proposal.evidence, expected_evidence)
            ):
                return None
            structure = candidate.structure.model_copy(
                update={
                    "left_statement": proposal.left_statement,
                    "right_statement": proposal.right_statement,
                    "integration": proposal.integration,
                }
            )
        else:
            return None
        return ConstructedCandidate.model_validate(
            {
                **candidate.model_dump(mode="python"),
                "status": "published",
                "structure": structure,
            }
        )

    def _snapshot_rows(
        self,
        *,
        user_id: UUID,
        raw: Mapping[str, object],
        basis: AnalysisBasis,
        candidates: Sequence[ConstructedCandidate],
        signals: Mapping[UUID, CandidateSignal],
    ) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
        if basis.basis_start is None or basis.basis_end is None:
            raise SnapshotValidationError("snapshot basis dates are unavailable")
        version = raw.get("next_snapshot_version")
        excluded = raw.get("excluded_entry_count")
        if not isinstance(version, int) or version < 1:
            raise SnapshotValidationError("snapshot version is invalid")
        if not isinstance(excluded, int) or excluded < 0:
            raise SnapshotValidationError("excluded entry count is invalid")
        snapshot_id = uuid5(
            NAMESPACE_URL,
            f"orion-reflection-snapshot:{user_id}:{basis.source_version}",
        )
        snapshot = {
            "id": str(snapshot_id),
            "version": version,
            "source_version": basis.source_version,
            "basis_start": basis.basis_start.isoformat(),
            "basis_end": basis.basis_end.isoformat(),
            "valid_entry_count": basis.valid_entry_count,
            "excluded_entry_count": excluded,
            "distinct_entry_dates": basis.distinct_entry_dates,
            "reflective_word_count": basis.reflective_word_count,
            "status": "available",
            "model_name": self._synthesis_model_id,
            "prompt_version": REFLECTION_SYNTHESIS_PROMPT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        by_type: dict[str, list[ConstructedCandidate]] = defaultdict(list)
        for candidate in candidates:
            by_type[candidate.pattern_type].append(candidate)
        insights: list[dict[str, object]] = []
        evidence: list[dict[str, object]] = []
        for pattern_type, reason_code in (
            ("hidden_driver", "DRIVER_NOT_REPEATED"),
            ("recurring_loop", "LOOP_NOT_REPEATED"),
            ("inner_tension", "BOTH_SIDES_NOT_SUPPORTED"),
        ):
            selected = by_type.get(pattern_type, [])
            if not selected:
                insight_id = uuid5(snapshot_id, f"{pattern_type}:0")
                insights.append(
                    {
                        "id": str(insight_id),
                        "pattern_type": pattern_type,
                        "ordinal": 0,
                        "status": "insufficient_evidence",
                        "reason_code": (
                            "NOT_ENOUGH_REFLECTIVE_CONTENT"
                            if not overall_basis_eligible(
                                valid_entry_count=basis.valid_entry_count,
                                distinct_entry_dates=basis.distinct_entry_dates,
                                reflective_word_count=basis.reflective_word_count,
                            )
                            else reason_code
                        ),
                    }
                )
                continue
            for ordinal, candidate in enumerate(selected):
                insight_id = uuid5(snapshot_id, f"{pattern_type}:{ordinal}")
                payload = {
                    "version": 1,
                    "pattern_type": pattern_type,
                    "structure": candidate.structure.model_dump(mode="json"),
                }
                insights.append(
                    {
                        "id": str(insight_id),
                        "candidate_id": str(candidate.id),
                        "pattern_type": pattern_type,
                        "ordinal": ordinal,
                        "status": "available",
                        "payload_envelope": self._cipher.encrypt_json(
                            payload,
                            user_id=user_id,
                            record_id=insight_id,
                            purpose="reflection_insight_payload",
                        ),
                        "confidence_label": candidate.confidence_label,
                        "score": candidate.score,
                    }
                )
                for role, identifiers in (
                    ("supporting", candidate.support_signal_ids),
                    ("counter", candidate.counter_signal_ids),
                ):
                    for evidence_ordinal, signal_id in enumerate(identifiers):
                        signal = signals[signal_id]
                        evidence.append(
                            {
                                "insight_id": str(insight_id),
                                "signal_id": str(signal.id),
                                "entry_id": str(signal.entry_id),
                                "evidence_role": role,
                                "ordinal": evidence_ordinal,
                                "source_start": signal.source_start,
                                "source_end": signal.source_end,
                            }
                        )
        return snapshot, insights, evidence

    def _pattern_review_rows(
        self,
        *,
        user_id: UUID,
        source_version: int,
        candidates: Sequence[ConstructedCandidate],
        signals: Mapping[UUID, CandidateSignal],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for candidate in candidates:
            review_item_id = candidate.review_item_id or uuid5(
                NAMESPACE_URL, f"orion-pattern-review-item:{candidate.id}"
            )
            if isinstance(candidate.structure, HiddenDriverStructure):
                statement = candidate.structure.statement
            elif isinstance(candidate.structure, RecurringLoopStructure):
                statement = candidate.structure.description
            else:
                statement = candidate.structure.integration
            supporting_signals = [
                signals[signal_id] for signal_id in candidate.support_signal_ids
            ]
            supporting_entries = sorted(
                {signal.entry_id: signal for signal in supporting_signals}.values(),
                key=lambda signal: (signal.entry_date, str(signal.entry_id)),
            )[:PATTERN_REVIEW_SOURCE_ENTRY_LIMIT]
            source_entry_ids = [
                str(signal.entry_id) for signal in supporting_entries
            ]
            source_dates = sorted(
                {signal.entry_date.isoformat() for signal in supporting_entries}
            )
            rows.append(
                {
                    "id": str(review_item_id),
                    "pattern_candidate_id": str(candidate.id),
                    "item_type": candidate.pattern_type,
                    "category": candidate.pattern_type,
                    "statement_envelope": self._cipher.encrypt_json(
                        statement,
                        user_id=user_id,
                        record_id=review_item_id,
                        purpose="review_item_statement",
                    ),
                    "source_entry_ids": source_entry_ids,
                    "source_dates": source_dates,
                    "inference_level": "synthesized",
                    "model_confidence": candidate.score,
                    "metadata": {
                        "model_id": self._synthesis_model_id,
                        "prompt_version": REFLECTION_SYNTHESIS_PROMPT_VERSION,
                        "source": "reflection_synthesis",
                        "source_version": source_version,
                        "candidate_version": candidate.version,
                    },
                }
            )
        return rows
