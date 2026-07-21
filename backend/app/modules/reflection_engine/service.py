from __future__ import annotations

import re
import logging
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from itertools import combinations
from statistics import fmean
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from app.modules.processing.prompts import NEED_TAGS
from app.modules.processing.schemas import LoopRole, NeedTag
from app.modules.jobs.types import JobClaim
from app.modules.reflection_engine.evidence import (
    EvidenceValidator,
    loop_node_key,
    roles_are_compatible,
    transition_key,
)
from app.modules.reflection_engine.prompts import (
    build_reflection_critic_input,
    build_reflection_synthesis_input,
)
from app.modules.reflection_engine.provider import UnavailableReflectionProvider
from app.modules.reflection_engine.repository import ReflectionEngineRepository
from app.modules.reflection_engine.schemas import (
    AnalysisBasis,
    CandidateBatch,
    CandidateEvidenceLink,
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
    SynthesisEvidenceReference,
)
from app.modules.reflection_engine.scoring import (
    confidence_label,
    hidden_driver_publishable,
    inner_tension_publishable,
    overall_basis_eligible,
    recurring_loop_publishable,
    score_hidden_driver,
    score_inner_tension,
    score_recurring_loop,
)
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.security.encryption import ContentCipher


logger = logging.getLogger("orion.reflection.service")
COUNTER_LANGUAGE = re.compile(
    r"\b(?:no longer|less important|independent(?:ly)?|without (?:needing|"
    r"seeking|wanting)|(?:felt|feel|was|is) (?:satisfied|fulfilled|secure)|"
    r"both .{0,40} together|reconciled)\b",
    re.IGNORECASE,
)
Node = tuple[LoopRole, str]
PUBLICATION_THRESHOLDS = {
    "hidden_driver": 0.68,
    "recurring_loop": 0.72,
    "inner_tension": 0.70,
}


class SnapshotValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _Chain:
    id: int
    entry_id: UUID
    signals: tuple[CandidateSignal, ...]

    @property
    def nodes(self) -> tuple[Node, ...]:
        return tuple(
            (cast(LoopRole, signal.loop_role), signal.normalized_label_fingerprint)
            for signal in self.signals
        )


@dataclass(frozen=True, slots=True)
class _Draft:
    candidate: ConstructedCandidate
    expected_counter_ids: tuple[UUID, ...]
    transition_support: Mapping[str, tuple[int, int]]


class ReflectionEngineService:
    def __init__(
        self,
        *,
        repository: ReflectionEngineRepository,
        cipher: ContentCipher,
        provider: Any | None = None,
        validator: EvidenceValidator | None = None,
        basis_days: int = 90,
    ) -> None:
        if basis_days != 90:
            raise ValueError("the MVP reflection basis must be exactly 90 days")
        self._repository = repository
        self._cipher = cipher
        self._provider = provider or UnavailableReflectionProvider()
        self._validator = validator or EvidenceValidator()
        self._basis_days = basis_days

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
        batch = self.construct_candidates(
            user_id=user_id,
            basis=basis,
            signals=signals,
            previous_candidates=previous,
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
        batch = self.construct_candidates(
            user_id=claim.user_id,
            basis=basis,
            signals=signals,
            previous_candidates=previous,
        )
        feedback = self._feedback_qualifications(raw)
        publishable = [
            candidate
            for candidate in batch.candidates
            if candidate.publication_gate_passed and candidate.status != "rejected"
        ]
        contexts = {
            str(candidate.id): self._synthesis_candidate_context(
                candidate,
                signals=signals,
                feedback_qualification=feedback.get(str(candidate.id)),
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
                logger.info(
                    "reflection_proposal_discarded reason_code=UNKNOWN_CANDIDATE"
                )
                continue
            materialized = self._materialize_proposal(
                deterministic,
                proposal=proposal,
            )
            if materialized is None:
                logger.info(
                    "reflection_proposal_discarded reason_code=EVIDENCE_ROLE_MISMATCH"
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
            )
            if reasons:
                logger.info(
                    "reflection_proposal_discarded reason_code=%s",
                    reasons[0],
                )
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
                    logger.info(
                        "reflection_proposal_discarded reason_code=CRITIC_DISCARDED"
                    )
                    continue
            final_candidates.append(materialized)

        selected = _select_snapshot_candidates(final_candidates)
        selected_ids = {candidate.id for candidate in selected}
        persisted_candidates = [
            _snapshot_candidate_status(candidate, published=candidate.id in selected_ids)
            for candidate in batch.candidates
        ]
        phrased_by_id = {candidate.id: candidate for candidate in selected}
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
            return self._repository.apply_snapshot(
                work.session,
                claim=claim,
                worker_id=worker_id,
                snapshot=snapshot,
                candidates=candidate_rows,
                candidate_evidence=candidate_evidence,
                insights=insights,
                snapshot_evidence=snapshot_evidence,
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
        feedback_qualification: str | None,
    ) -> dict[str, object]:
        by_id = {signal.id: signal for signal in signals}
        evidence = []
        for role, identifiers in (
            ("supporting", candidate.support_signal_ids),
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
                    }
                )
        return {
            "candidate_id": str(candidate.id),
            "pattern_type": candidate.pattern_type,
            "canonical_key": candidate.canonical_key,
            "score": candidate.score,
            "score_components": candidate.score_components.model_dump(mode="json"),
            "deterministic_structure": candidate.structure.model_dump(mode="json"),
            "evidence": evidence,
            "feedback_qualification": feedback_qualification,
        }

    def _materialize_proposal(
        self,
        candidate: ConstructedCandidate,
        *,
        proposal: HiddenDriverProposal | RecurringLoopProposal | InnerTensionProposal,
    ) -> ConstructedCandidate | None:
        expected_evidence = {
            *((item, "supporting") for item in candidate.support_signal_ids),
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
                    (item, "supporting") for item in deterministic.support_signal_ids
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

    def construct_candidates(
        self,
        *,
        user_id: UUID,
        basis: AnalysisBasis,
        signals: Sequence[CandidateSignal],
        previous_candidates: Sequence[PreviousCandidate] = (),
    ) -> CandidateBatch:
        eligible = overall_basis_eligible(
            valid_entry_count=basis.valid_entry_count,
            distinct_entry_dates=basis.distinct_entry_dates,
            reflective_word_count=basis.reflective_word_count,
        )
        if not eligible:
            return CandidateBatch(
                basis=basis,
                basis_eligible=False,
                candidates=[],
                evidence=[],
                discarded_reason_codes=[],
            )
        previous = {
            (candidate.pattern_type, candidate.canonical_key): candidate
            for candidate in previous_candidates
        }
        valid_signals: list[CandidateSignal] = []
        discarded: list[str] = []
        for signal in signals:
            reasons = self._validator.validate_signal(
                signal,
                user_id=user_id,
                basis_start=basis.basis_start,
                basis_end=basis.basis_end,
            )
            if reasons:
                discarded.extend(reasons)
            else:
                valid_signals.append(signal)
        drafts = [
            *self._hidden_driver_drafts(
                user_id=user_id,
                source_version=basis.source_version,
                signals=valid_signals,
                previous=previous,
            ),
            *self._loop_drafts(
                user_id=user_id,
                source_version=basis.source_version,
                signals=valid_signals,
                previous=previous,
            ),
            *self._tension_drafts(
                user_id=user_id,
                source_version=basis.source_version,
                signals=valid_signals,
                previous=previous,
            ),
        ]
        by_id = {signal.id: signal for signal in valid_signals}
        accepted: list[ConstructedCandidate] = []
        evidence: list[CandidateEvidenceLink] = []
        for draft in sorted(
            drafts,
            key=lambda item: (
                item.candidate.pattern_type,
                item.candidate.canonical_key,
            ),
        ):
            reasons = self._validator.validate_candidate(
                draft.candidate,
                user_id=user_id,
                signals=by_id,
                basis_start=basis.basis_start,
                basis_end=basis.basis_end,
                expected_counter_signal_ids=draft.expected_counter_ids,
                transition_support=draft.transition_support,
            )
            if reasons:
                discarded.extend(reasons)
                continue
            accepted.append(draft.candidate)
            evidence.extend(
                CandidateEvidenceLink(
                    candidate_id=draft.candidate.id,
                    signal_id=signal_id,
                    evidence_role="supporting",
                    evidence_weight=by_id[signal_id].confidence,
                )
                for signal_id in draft.candidate.support_signal_ids
            )
            evidence.extend(
                CandidateEvidenceLink(
                    candidate_id=draft.candidate.id,
                    signal_id=signal_id,
                    evidence_role="counter",
                    evidence_weight=by_id[signal_id].confidence,
                )
                for signal_id in draft.candidate.counter_signal_ids
            )
        return CandidateBatch(
            basis=basis,
            basis_eligible=True,
            candidates=accepted,
            evidence=evidence,
            discarded_reason_codes=list(dict.fromkeys(discarded)),
        )

    def _materialize_basis(
        self, raw: Mapping[str, object], *, user_id: UUID
    ) -> tuple[AnalysisBasis, tuple[CandidateSignal, ...], tuple[PreviousCandidate, ...]]:
        basis = AnalysisBasis.model_validate(
            {
                "source_version": raw.get("source_version"),
                "basis_start": raw.get("basis_start"),
                "basis_end": raw.get("basis_end"),
                "valid_entry_count": raw.get("valid_entry_count"),
                "distinct_entry_dates": raw.get("distinct_entry_dates"),
                "reflective_word_count": raw.get("reflective_word_count"),
            }
        )
        raw_signals = raw.get("signals")
        raw_candidates = raw.get("candidates")
        if not isinstance(raw_signals, list) or not isinstance(raw_candidates, list):
            raise ValueError("candidate basis arrays are invalid")
        signals: list[CandidateSignal] = []
        for item in raw_signals:
            if not isinstance(item, dict):
                raise ValueError("candidate basis signal is invalid")
            signal_id = UUID(str(item["id"]))
            entry_id = UUID(str(item["entry_id"]))
            entry_envelope = item.get("entry_content_envelope")
            signal_envelope = item.get("payload_envelope")
            if not isinstance(entry_envelope, dict) or not isinstance(signal_envelope, dict):
                raise ValueError("candidate evidence envelope is invalid")
            entry_text = self._cipher.decrypt(
                entry_envelope,
                user_id=user_id,
                record_id=entry_id,
            )
            payload = self._cipher.decrypt_json(
                signal_envelope,
                user_id=user_id,
                record_id=signal_id,
                purpose="entry_signal_payload",
            )
            if not isinstance(payload, dict):
                raise ValueError("candidate signal payload is invalid")
            signals.append(
                CandidateSignal.model_validate(
                    {
                        **item,
                        "normalized_label": payload.get("normalized_label"),
                        "interpretation": payload.get("interpretation"),
                        "source_quote": payload.get("source_quote"),
                        "entry_text": entry_text,
                    }
                )
            )
        previous: list[PreviousCandidate] = []
        for item in raw_candidates:
            if not isinstance(item, dict):
                raise ValueError("previous candidate is invalid")
            candidate_id = UUID(str(item["id"]))
            envelope = item.get("payload_envelope")
            if not isinstance(envelope, dict):
                raise ValueError("candidate payload envelope is invalid")
            payload = self._cipher.decrypt_json(
                envelope,
                user_id=user_id,
                record_id=candidate_id,
                purpose="reflection_candidate_payload",
            )
            if not isinstance(payload, dict):
                raise ValueError("candidate payload is invalid")
            previous.append(PreviousCandidate.model_validate({**item, "payload": payload}))
        return basis, tuple(signals), tuple(previous)

    def _hidden_driver_drafts(
        self,
        *,
        user_id: UUID,
        source_version: int,
        signals: Sequence[CandidateSignal],
        previous: Mapping[tuple[str, str], PreviousCandidate],
    ) -> list[_Draft]:
        drafts: list[_Draft] = []
        for raw_need in NEED_TAGS:
            need = cast(NeedTag, raw_need)
            tagged = [signal for signal in signals if need in signal.need_tags]
            raw_support = [signal for signal in tagged if not _is_counter(signal)]
            counters = _collapse([signal for signal in tagged if _is_counter(signal)])
            support = _collapse(raw_support)
            if not support:
                continue
            canonical_key = self._canonical_key(
                f"hidden_driver:{need}", user_id=user_id
            )
            prior = previous.get(("hidden_driver", canonical_key))
            clusters = _clusters(support)
            entries = {signal.entry_id for signal in support}
            dates = {signal.entry_date for signal in support}
            score, components = score_hidden_driver(
                supporting_entries=len(entries),
                distinct_dates=len(dates),
                span_days=_span_days(support),
                theme_keys={theme for signal in support for theme in signal.themes},
                support_confidences=[signal.confidence for signal in support],
                counter_confidences=[signal.confidence for signal in counters],
                distinct_signal_types=len({signal.signal_type for signal in support}),
                unique_duplicate_clusters=len(clusters),
                raw_support_signal_count=len(raw_support),
                current_support_clusters=clusters,
                previous_support_clusters=_previous_clusters(prior),
                previous_score=prior.score if prior else None,
            )
            publishable = hidden_driver_publishable(
                supporting_entries=len(entries),
                distinct_dates=len(dates),
                distinct_signal_types=len({signal.signal_type for signal in support}),
                score=score,
            )
            candidate_id = prior.id if prior else _candidate_id(
                user_id, "hidden_driver", canonical_key
            )
            status, rejected_at, rejected_source = _lifecycle(
                prior,
                publishable=publishable,
                support=support,
            )
            display = need.replace("_", " ")
            candidate = ConstructedCandidate(
                id=candidate_id,
                pattern_type="hidden_driver",
                canonical_key=canonical_key,
                status=status,
                score=score,
                score_components=components,
                structure=HiddenDriverStructure(
                    canonical_need=need,
                    statement=(
                        "A possible pattern across your entries may involve the need "
                        f"for {display}."
                    ),
                    underlying_need=display,
                    supporting_entries=len(entries),
                    distinct_dates=len(dates),
                    distinct_signal_types=len(
                        {signal.signal_type for signal in support}
                    ),
                ),
                support_signal_ids=[signal.id for signal in support],
                counter_signal_ids=[signal.id for signal in counters],
                support_clusters=clusters,
                publication_gate_passed=publishable,
                confidence_label=_candidate_confidence_label(
                    prior, status=status, supporting_entries=len(entries)
                ),
                first_seen_at=prior.first_seen_at if prior else _at_utc(min(dates)),
                last_seen_at=_at_utc(max(dates)),
                version=_next_version(prior, source_version),
                rejected_at=rejected_at,
                rejected_source_version=rejected_source,
            )
            drafts.append(
                _Draft(
                    candidate=candidate,
                    expected_counter_ids=tuple(signal.id for signal in counters),
                    transition_support={},
                )
            )
        return drafts

    def _loop_drafts(
        self,
        *,
        user_id: UUID,
        source_version: int,
        signals: Sequence[CandidateSignal],
        previous: Mapping[tuple[str, str], PreviousCandidate],
    ) -> list[_Draft]:
        chains = _build_chains(signals)
        observations: dict[tuple[Node, Node], list[_Chain]] = defaultdict(list)
        for chain in chains:
            for left, right in zip(chain.nodes, chain.nodes[1:]):
                observations[(left, right)].append(chain)
        supported_edges = {
            edge: items
            for edge, items in observations.items()
            if len({item.id for item in items}) >= 2
            and len({item.entry_id for item in items}) >= 2
        }
        cycles = _supported_cycles(supported_edges)
        drafts: list[_Draft] = []
        for nodes in sorted(cycles, key=lambda value: tuple(_node_text(item) for item in value)):
            cycle_edges = tuple(zip(nodes, (*nodes[1:], nodes[0])))
            observing_chains = [
                chain
                for chain in chains
                if len(set(zip(chain.nodes, chain.nodes[1:])) & set(cycle_edges)) >= 2
            ]
            raw_support = [
                signal
                for chain in observing_chains
                for signal in chain.signals
                if _signal_node(signal) in set(nodes)
            ]
            support = _collapse(raw_support)
            if not support:
                continue
            labels = {node[1] for node in nodes}
            counters = _collapse(
                [
                    signal
                    for signal in signals
                    if _is_counter(signal)
                    and signal.normalized_label_fingerprint in labels
                ]
            )
            descriptor = "recurring_loop:" + "|".join(_node_text(node) for node in nodes)
            canonical_key = self._canonical_key(descriptor, user_id=user_id)
            prior = previous.get(("recurring_loop", canonical_key))
            clusters = _clusters(support)
            entries = {signal.entry_id for signal in support}
            dates = {signal.entry_date for signal in support}
            node_set = set(nodes)
            candidate_edges = {
                edge: items
                for edge, items in supported_edges.items()
                if edge[0] in node_set and edge[1] in node_set
            }
            score, components = score_recurring_loop(
                observed_chains=len({chain.id for chain in observing_chains}),
                supported_transitions=len(candidate_edges),
                distinct_dates=len(dates),
                span_days=_span_days(support),
                theme_keys={theme for signal in support for theme in signal.themes},
                support_confidences=[signal.confidence for signal in support],
                counter_confidences=[signal.confidence for signal in counters],
                unique_duplicate_clusters=len(clusters),
                raw_support_signal_count=len(raw_support),
                current_support_clusters=clusters,
                previous_support_clusters=_previous_clusters(prior),
                previous_score=prior.score if prior else None,
            )
            publishable = recurring_loop_publishable(
                observed_chains=len({chain.id for chain in observing_chains}),
                supporting_entries=len(entries),
                supported_transitions=len(candidate_edges),
                distinct_dates=len(dates),
                score=score,
            )
            status, rejected_at, rejected_source = _lifecycle(
                prior,
                publishable=publishable,
                support=support,
            )
            steps = [
                LoopStepStructure(
                    loop_role=node[0],
                    normalized_label_fingerprint=node[1],
                    support_signal_ids=[
                        signal.id for signal in support if _signal_node(signal) == node
                    ],
                )
                for node in nodes
            ]
            transition_support = {
                transition_key(left[0], left[1], right[0], right[1]): (
                    len({chain.id for chain in items}),
                    len({chain.entry_id for chain in items}),
                )
                for (left, right), items in candidate_edges.items()
            }
            candidate = ConstructedCandidate(
                id=prior.id
                if prior
                else _candidate_id(user_id, "recurring_loop", canonical_key),
                pattern_type="recurring_loop",
                canonical_key=canonical_key,
                status=status,
                score=score,
                score_components=components,
                structure=RecurringLoopStructure(
                    title="A possible recurring loop",
                    description=(
                        "A possible recurring loop across your entries may connect "
                        "these supported steps."
                    ),
                    steps=steps,
                    transition_keys=sorted(transition_support),
                    observed_chains=len({chain.id for chain in observing_chains}),
                    supporting_entries=len(entries),
                    supported_transitions=len(candidate_edges),
                    distinct_dates=len(dates),
                ),
                support_signal_ids=[signal.id for signal in support],
                counter_signal_ids=[signal.id for signal in counters],
                support_clusters=clusters,
                publication_gate_passed=publishable,
                confidence_label=_candidate_confidence_label(
                    prior, status=status, supporting_entries=len(entries)
                ),
                first_seen_at=prior.first_seen_at if prior else _at_utc(min(dates)),
                last_seen_at=_at_utc(max(dates)),
                version=_next_version(prior, source_version),
                rejected_at=rejected_at,
                rejected_source_version=rejected_source,
            )
            drafts.append(
                _Draft(
                    candidate=candidate,
                    expected_counter_ids=tuple(signal.id for signal in counters),
                    transition_support=transition_support,
                )
            )
        return drafts

    def _tension_drafts(
        self,
        *,
        user_id: UUID,
        source_version: int,
        signals: Sequence[CandidateSignal],
        previous: Mapping[tuple[str, str], PreviousCandidate],
    ) -> list[_Draft]:
        pairs: set[tuple[NeedTag, NeedTag]] = set()
        for signal in signals:
            if signal.signal_type == "conflict" and len(signal.need_tags) >= 2:
                pairs.update(_need_pair(left, right) for left, right in combinations(signal.need_tags, 2))
        actions: dict[str, list[CandidateSignal]] = defaultdict(list)
        avoidances: dict[str, list[CandidateSignal]] = defaultdict(list)
        for signal in signals:
            if signal.signal_type == "action" or signal.loop_role == "action":
                actions[signal.normalized_label_fingerprint].append(signal)
            if signal.signal_type == "avoidance" or signal.loop_role == "avoidance":
                avoidances[signal.normalized_label_fingerprint].append(signal)
        for label in actions.keys() & avoidances.keys():
            for action in actions[label]:
                for avoidance in avoidances[label]:
                    if action.entry_id == avoidance.entry_id:
                        continue
                    pairs.update(
                        _need_pair(left, right)
                        for left in action.need_tags
                        for right in avoidance.need_tags
                        if left != right
                    )
        drafts: list[_Draft] = []
        for left, right in sorted(pairs):
            tagged = [
                signal
                for signal in signals
                if left in signal.need_tags or right in signal.need_tags
            ]
            raw_support = [signal for signal in tagged if not _is_counter(signal)]
            support = _collapse(raw_support)
            counters = _collapse([signal for signal in tagged if _is_counter(signal)])
            left_support = [signal for signal in support if left in signal.need_tags]
            right_support = [signal for signal in support if right in signal.need_tags]
            if not left_support or not right_support:
                continue
            support = sorted(
                {signal.id: signal for signal in (*left_support, *right_support)}.values(),
                key=_signal_order,
            )
            canonical_key = self._canonical_key(
                f"inner_tension:{left}|{right}", user_id=user_id
            )
            prior = previous.get(("inner_tension", canonical_key))
            clusters = _clusters(support)
            dates = {signal.entry_date for signal in support}
            left_entries = {signal.entry_id for signal in left_support}
            right_entries = {signal.entry_id for signal in right_support}
            direct_entries = {
                signal.entry_id
                for signal in support
                if signal.signal_type == "conflict"
                and left in signal.need_tags
                and right in signal.need_tags
            }
            switches = _side_switches(support, left=left, right=right)
            score, components = score_inner_tension(
                left_supporting_entries=len(left_entries),
                right_supporting_entries=len(right_entries),
                left_mean_confidence=fmean(signal.confidence for signal in left_support),
                right_mean_confidence=fmean(signal.confidence for signal in right_support),
                direct_conflict_entry_count=len(direct_entries),
                need_side_switches=switches,
                theme_keys={theme for signal in support for theme in signal.themes},
                support_confidences=[signal.confidence for signal in support],
                counter_confidences=[signal.confidence for signal in counters],
                unique_duplicate_clusters=len(clusters),
                raw_support_signal_count=len(raw_support),
                current_support_clusters=clusters,
                previous_support_clusters=_previous_clusters(prior),
                previous_score=prior.score if prior else None,
            )
            publishable = inner_tension_publishable(
                left_supporting_entries=len(left_entries),
                right_supporting_entries=len(right_entries),
                distinct_dates=len(dates),
                score=score,
            )
            status, rejected_at, rejected_source = _lifecycle(
                prior,
                publishable=publishable,
                support=support,
            )
            left_display = left.replace("_", " ")
            right_display = right.replace("_", " ")
            candidate = ConstructedCandidate(
                id=prior.id
                if prior
                else _candidate_id(user_id, "inner_tension", canonical_key),
                pattern_type="inner_tension",
                canonical_key=canonical_key,
                status=status,
                score=score,
                score_components=components,
                structure=InnerTensionStructure(
                    left_need=left,
                    right_need=right,
                    left_statement=f"Some entries support the need for {left_display}.",
                    right_statement=f"Some entries support the need for {right_display}.",
                    integration=(
                        "You may be trying to hold both "
                        f"{left_display} and {right_display}; a workable arrangement "
                        "would make room for each."
                    ),
                    left_support_signal_ids=[signal.id for signal in left_support],
                    right_support_signal_ids=[signal.id for signal in right_support],
                    left_supporting_entries=len(left_entries),
                    right_supporting_entries=len(right_entries),
                    distinct_dates=len(dates),
                ),
                support_signal_ids=[signal.id for signal in support],
                counter_signal_ids=[signal.id for signal in counters],
                support_clusters=clusters,
                publication_gate_passed=publishable,
                confidence_label=_candidate_confidence_label(
                    prior,
                    status=status,
                    supporting_entries=len(left_entries | right_entries),
                ),
                first_seen_at=prior.first_seen_at if prior else _at_utc(min(dates)),
                last_seen_at=_at_utc(max(dates)),
                version=_next_version(prior, source_version),
                rejected_at=rejected_at,
                rejected_source_version=rejected_source,
            )
            drafts.append(
                _Draft(
                    candidate=candidate,
                    expected_counter_ids=tuple(signal.id for signal in counters),
                    transition_support={},
                )
            )
        return drafts

    def _canonical_key(self, value: str, *, user_id: UUID) -> str:
        return self._cipher.reflection_fingerprint(
            value,
            user_id=user_id,
            purpose="candidate_canonical",
        )[1]

    def _candidate_row(
        self,
        candidate: ConstructedCandidate,
        *,
        user_id: UUID,
        source_version: int,
    ) -> dict[str, object]:
        payload = {
            "version": 1,
            "pattern_type": candidate.pattern_type,
            "structure": candidate.structure.model_dump(mode="json"),
            "support_clusters": candidate.support_clusters,
            "publication_gate_passed": candidate.publication_gate_passed,
            "confidence_label": candidate.confidence_label,
            "source_version": source_version,
        }
        return {
            "id": str(candidate.id),
            "pattern_type": candidate.pattern_type,
            "canonical_key": candidate.canonical_key,
            "status": candidate.status,
            "score": candidate.score,
            "score_components": candidate.score_components.model_dump(mode="json"),
            "payload_envelope": self._cipher.encrypt_json(
                payload,
                user_id=user_id,
                record_id=candidate.id,
                purpose="reflection_candidate_payload",
            ),
            "first_seen_at": candidate.first_seen_at.isoformat(),
            "last_seen_at": candidate.last_seen_at.isoformat(),
            "version": candidate.version,
            "rejected_at": (
                candidate.rejected_at.isoformat() if candidate.rejected_at else None
            ),
            "rejected_source_version": candidate.rejected_source_version,
            "publication_gate_passed": candidate.publication_gate_passed,
        }


def _is_counter(signal: CandidateSignal) -> bool:
    return COUNTER_LANGUAGE.search(
        f"{signal.normalized_label} {signal.interpretation}"
    ) is not None


def _candidate_id(user_id: UUID, pattern_type: str, canonical_key: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"orion-reflection-candidate:{user_id}:{pattern_type}:{canonical_key}",
    )


def _collapse(signals: Collection[CandidateSignal]) -> list[CandidateSignal]:
    chosen: dict[tuple[str, str, str, str | None], CandidateSignal] = {}
    for signal in sorted(
        signals,
        key=lambda item: (
            -item.confidence,
            item.entry_date,
            str(item.entry_id),
            item.source_start,
            str(item.id),
        ),
    ):
        identity = (
            signal.cluster_key,
            signal.signal_type,
            signal.normalized_label_fingerprint,
            signal.loop_role,
        )
        chosen.setdefault(identity, signal)
    return sorted(chosen.values(), key=_signal_order)


def _signal_order(signal: CandidateSignal):
    return signal.entry_date, str(signal.entry_id), signal.source_start, str(signal.id)


def _clusters(signals: Collection[CandidateSignal]) -> list[str]:
    return sorted({signal.cluster_key for signal in signals})


def _span_days(signals: Collection[CandidateSignal]) -> int:
    dates = [signal.entry_date for signal in signals]
    return (max(dates) - min(dates)).days if dates else 0


def _at_utc(value: date) -> datetime:
    return datetime.combine(value, time.min, timezone.utc)


def _previous_clusters(candidate: PreviousCandidate | None) -> list[str] | None:
    if candidate is None:
        return None
    value = candidate.payload.get("support_clusters")
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("previous candidate support clusters are invalid")
    return sorted(set(value))


def _next_version(candidate: PreviousCandidate | None, source_version: int) -> int:
    if candidate is None or candidate.last_source_version == source_version:
        return candidate.version if candidate else 1
    return candidate.version + 1


def _candidate_confidence_label(
    candidate: PreviousCandidate | None,
    *,
    status: str,
    supporting_entries: int,
):
    if candidate is not None and candidate.status == "rejected" and status == "candidate":
        return "preliminary"
    return confidence_label(supporting_entries)


def _lifecycle(
    candidate: PreviousCandidate | None,
    *,
    publishable: bool,
    support: Collection[CandidateSignal],
):
    if candidate is None:
        return "candidate", None, None
    if candidate.status == "rejected":
        after_rejection = [
            signal
            for signal in support
            if candidate.rejected_source_version is not None
            and signal.analysis_source_version > candidate.rejected_source_version
        ]
        may_reenter = (
            publishable
            and len({signal.entry_id for signal in after_rejection}) >= 3
            and len({signal.entry_date for signal in after_rejection}) >= 2
        )
        if not may_reenter:
            return "rejected", candidate.rejected_at, candidate.rejected_source_version
        return "candidate", None, None
    if candidate.status == "published":
        return ("published" if publishable else "weakened"), None, None
    return "candidate", None, None


def _signal_node(signal: CandidateSignal) -> Node:
    if signal.loop_role is None:
        raise ValueError("loop signal has no role")
    return signal.loop_role, signal.normalized_label_fingerprint


def _node_text(node: Node) -> str:
    return loop_node_key(node[0], node[1])


def _build_chains(signals: Sequence[CandidateSignal]) -> list[_Chain]:
    by_entry: dict[UUID, list[CandidateSignal]] = defaultdict(list)
    for signal in signals:
        if signal.loop_role is not None and not _is_counter(signal):
            by_entry[signal.entry_id].append(signal)
    chains: list[_Chain] = []
    chain_id = 0
    for entry_id in sorted(by_entry, key=str):
        ordered = sorted(by_entry[entry_id], key=lambda item: (item.source_start, str(item.id)))
        current: list[CandidateSignal] = []
        for signal in ordered:
            if not current:
                current = [signal]
                continue
            if roles_are_compatible(
                cast(LoopRole, current[-1].loop_role), cast(LoopRole, signal.loop_role)
            ):
                current.append(signal)
            else:
                if len(current) >= 3:
                    chains.append(_Chain(chain_id, entry_id, tuple(current)))
                    chain_id += 1
                current = [signal]
        if len(current) >= 3:
            chains.append(_Chain(chain_id, entry_id, tuple(current)))
            chain_id += 1
    return chains


def _supported_cycles(
    supported_edges: Mapping[tuple[Node, Node], Sequence[_Chain]],
) -> set[tuple[Node, ...]]:
    graph: dict[Node, set[Node]] = defaultdict(set)
    for left, right in supported_edges:
        graph[left].add(right)
    cycles: set[tuple[Node, ...]] = set()
    for start in sorted(graph, key=_node_text):
        stack: list[tuple[Node, tuple[Node, ...]]] = [(start, (start,))]
        while stack:
            current, path = stack.pop()
            for following in sorted(graph.get(current, ()), key=_node_text, reverse=True):
                if following == start and 3 <= len(path) <= 6:
                    cycles.add(_canonical_rotation(path))
                elif following not in path and len(path) < 6:
                    stack.append((following, (*path, following)))
    return cycles


def _canonical_rotation(nodes: Sequence[Node]) -> tuple[Node, ...]:
    rotations = [tuple((*nodes[index:], *nodes[:index])) for index in range(len(nodes))]
    return min(rotations, key=lambda value: tuple(_node_text(node) for node in value))


def _need_pair(left: NeedTag, right: NeedTag) -> tuple[NeedTag, NeedTag]:
    return tuple(sorted((left, right)))  # type: ignore[return-value]


def _side_switches(
    signals: Collection[CandidateSignal], *, left: NeedTag, right: NeedTag
) -> int:
    sides: list[str] = []
    for signal in sorted(signals, key=_signal_order):
        has_left = left in signal.need_tags
        has_right = right in signal.need_tags
        if has_left and not has_right:
            sides.append("left")
        elif has_right and not has_left:
            sides.append("right")
    return sum(current != previous for previous, current in zip(sides, sides[1:]))
