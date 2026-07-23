from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from itertools import combinations
from statistics import fmean
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from app.modules.processing.prompts import NEED_TAGS
from app.modules.processing.schemas import LoopRole, NeedTag
from app.modules.reflection_engine.evidence import (
    EvidenceValidator,
    loop_node_key,
    loop_role_fingerprint,
    roles_are_compatible,
    transition_key,
)
from app.modules.reflection_engine.ordering import signal_order as _signal_order
from app.modules.reflection_engine.repository import (
    PersistedCandidateSignal,
    PersistedPreviousCandidate,
    ReflectionEngineRepository,
    SemanticNeighbor,
)
from app.modules.reflection_engine.schemas import (
    AnalysisBasis,
    CandidateBatch,
    CandidateEvidenceLink,
    CandidateSignal,
    CandidateStatus,
    ConfidenceLabel,
    ConstructedCandidate,
    HiddenDriverStructure,
    InnerTensionStructure,
    LoopStepStructure,
    PatternType,
    PreviousCandidate,
    RecurringLoopStructure,
)
from app.modules.reflection_engine.scoring import (
    confidence_label,
    clamp01,
    hidden_driver_publishable,
    inner_tension_publishable,
    overall_basis_eligible,
    recurring_loop_publishable,
    score_hidden_driver,
    score_inner_tension,
    score_recurring_loop,
)
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.observability.logging import safe_log
from app.shared.observability.reflection import ReflectionTelemetry
from app.shared.security.encryption import ContentCipher


logger = logging.getLogger("orion.reflection.service")
COUNTER_LANGUAGE = re.compile(
    r"\b(?:no longer|less important|independent(?:ly)?|without (?:needing|"
    r"seeking|wanting)|(?:felt|feel|was|is) (?:satisfied|fulfilled|secure)|"
    r"both .{0,40} together|reconciled)\b",
    re.IGNORECASE,
)
Node = tuple[LoopRole, str]
SEMANTIC_SIMILARITY_THRESHOLD = 0.90
SEMANTIC_NEIGHBOR_TOP_K = 8
SEMANTIC_ANCHOR_BATCH_SIZE = 4096


@dataclass(frozen=True, slots=True)
class _Chain:
    id: int
    entry_id: UUID
    signals: tuple[CandidateSignal, ...]

    @property
    def nodes(self) -> tuple[Node, ...]:
        return tuple(_signal_node(signal) for signal in self.signals)


@dataclass(frozen=True, slots=True)
class _Draft:
    candidate: ConstructedCandidate
    expected_counter_ids: tuple[UUID, ...]
    transition_support: Mapping[str, tuple[int, int]]



class CandidateConstructionMixin:
    _repository: ReflectionEngineRepository
    _cipher: ContentCipher
    _validator: EvidenceValidator
    _embedding_model_id: str
    _telemetry: ReflectionTelemetry

    def construct_candidates(
        self,
        *,
        user_id: UUID,
        basis: AnalysisBasis,
        signals: Sequence[CandidateSignal],
        previous_candidates: Sequence[PreviousCandidate] = (),
        semantic_neighbors: Sequence[SemanticNeighbor] = (),
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
        semantic_clusters = _semantic_cluster_keys(signals, semantic_neighbors)
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
                semantic_clusters=semantic_clusters,
            ),
            *self._loop_drafts(
                user_id=user_id,
                source_version=basis.source_version,
                signals=valid_signals,
                previous=previous,
                semantic_clusters=semantic_clusters,
            ),
            *self._tension_drafts(
                user_id=user_id,
                source_version=basis.source_version,
                signals=valid_signals,
                previous=previous,
                semantic_clusters=semantic_clusters,
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
                semantic_clusters=semantic_clusters,
            )
            if reasons:
                discarded.extend(reasons)
                self._telemetry.record_candidate(
                    pattern_type=draft.candidate.pattern_type,
                    outcome="discarded",
                )
                safe_log(
                    logger,
                    "reflection_candidate_observed",
                    candidate_id=draft.candidate.id,
                    pattern_type=draft.candidate.pattern_type,
                    outcome="discarded",
                )
                continue
            accepted.append(draft.candidate)
            evidence.extend(
                CandidateEvidenceLink(
                    candidate_id=draft.candidate.id,
                    signal_id=signal_id,
                    evidence_role="supporting",
                    evidence_weight=(
                        by_id[signal_id].confidence * draft.candidate.review_weight
                    ),
                )
                for signal_id in draft.candidate.support_signal_ids
            )
            evidence.extend(
                CandidateEvidenceLink(
                    candidate_id=draft.candidate.id,
                    signal_id=signal_id,
                    evidence_role="counter",
                    evidence_weight=(
                        by_id[signal_id].confidence * draft.candidate.review_weight
                    ),
                )
                for signal_id in draft.candidate.counter_signal_ids
            )
        for reason_code in discarded:
            self._telemetry.record_validator_discard(reason_code=reason_code)
        for candidate in accepted:
            self._telemetry.record_candidate(
                pattern_type=candidate.pattern_type,
                outcome="constructed",
            )
            safe_log(
                logger,
                "reflection_candidate_observed",
                candidate_id=candidate.id,
                pattern_type=candidate.pattern_type,
                outcome="constructed",
            )
            if candidate.publication_gate_passed:
                self._telemetry.record_candidate(
                    pattern_type=candidate.pattern_type,
                    outcome="publishable",
                )
        return CandidateBatch(
            basis=basis,
            basis_eligible=True,
            candidates=accepted,
            evidence=evidence,
            discarded_reason_codes=list(dict.fromkeys(discarded)),
        )

    def _load_semantic_neighbors(
        self,
        *,
        uow: UnitOfWorkFactory,
        user_id: UUID,
        source_version: int,
        signals: Sequence[CandidateSignal],
    ) -> tuple[SemanticNeighbor, ...]:
        signal_ids = [signal.id for signal in signals]
        if not signal_ids:
            return ()
        neighbors: list[SemanticNeighbor] = []
        with uow.for_worker() as work:
            for start in range(0, len(signal_ids), SEMANTIC_ANCHOR_BATCH_SIZE):
                neighbors.extend(
                    self._repository.load_semantic_neighbors(
                        work.session,
                        user_id=user_id,
                        anchor_signal_ids=signal_ids[
                            start : start + SEMANTIC_ANCHOR_BATCH_SIZE
                        ],
                        source_version=source_version,
                        model_id=self._embedding_model_id,
                        top_k=SEMANTIC_NEIGHBOR_TOP_K,
                        similarity_threshold=SEMANTIC_SIMILARITY_THRESHOLD,
                    )
                )
        return tuple(neighbors)

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
            stored = PersistedCandidateSignal.model_validate(item)
            entry_text = self._cipher.decrypt(
                stored.entry_content_envelope,
                user_id=user_id,
                record_id=stored.entry_id,
            )
            payload = self._cipher.decrypt_json(
                stored.payload_envelope,
                user_id=user_id,
                record_id=stored.id,
                purpose="entry_signal_payload",
            )
            if not isinstance(payload, dict):
                raise ValueError("candidate signal payload is invalid")
            signals.append(
                CandidateSignal.model_validate(
                    {
                        **stored.domain_values(),
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
            persisted_candidate = PersistedPreviousCandidate.model_validate(item)
            payload = self._cipher.decrypt_json(
                persisted_candidate.payload_envelope,
                user_id=user_id,
                record_id=persisted_candidate.id,
                purpose="reflection_candidate_payload",
            )
            if not isinstance(payload, dict):
                raise ValueError("candidate payload is invalid")
            previous.append(
                PreviousCandidate.model_validate(
                    {**persisted_candidate.domain_values(), "payload": payload}
                )
            )
        return basis, tuple(signals), tuple(previous)

    def _hidden_driver_drafts(
        self,
        *,
        user_id: UUID,
        source_version: int,
        signals: Sequence[CandidateSignal],
        previous: Mapping[tuple[PatternType, str], PreviousCandidate],
        semantic_clusters: Mapping[UUID, str],
    ) -> list[_Draft]:
        drafts: list[_Draft] = []
        for raw_need in NEED_TAGS:
            need = cast(NeedTag, raw_need)
            tagged = [signal for signal in signals if need in signal.need_tags]
            raw_support = [signal for signal in tagged if not _is_counter(signal)]
            counters = _collapse(
                [signal for signal in tagged if _is_counter(signal)], semantic_clusters
            )
            support = _collapse(raw_support, semantic_clusters)
            if not support:
                continue
            canonical_key = self._canonical_key(
                f"hidden_driver:{need}", user_id=user_id
            )
            prior = previous.get(("hidden_driver", canonical_key))
            clusters = _clusters(support, semantic_clusters)
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
            review_weight = prior.review_weight if prior else 1.0
            score = clamp01(score * review_weight)
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
                review_weight=review_weight,
                review_item_id=prior.review_item_id if prior else None,
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
        previous: Mapping[tuple[PatternType, str], PreviousCandidate],
        semantic_clusters: Mapping[UUID, str],
    ) -> list[_Draft]:
        chains = _build_chains(
            _deduplicate_semantic_signals(signals, semantic_clusters)
        )
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
            node_set = set(nodes)
            candidate_edges = {
                edge: items
                for edge, items in supported_edges.items()
                if edge[0] in node_set and edge[1] in node_set
            }
            observing_chains = [
                chain
                for chain in chains
                if len(set(zip(chain.nodes, chain.nodes[1:])) & set(cycle_edges)) >= 2
            ]
            supporting_chains = {
                chain.id: chain
                for items in candidate_edges.values()
                for chain in items
            }.values()
            raw_support = [
                signal
                for chain in supporting_chains
                for signal in chain.signals
                if _signal_node(signal) in node_set
            ]
            support = _collapse(raw_support, semantic_clusters)
            if not support:
                continue
            labels = {node[1] for node in nodes}
            counters = _collapse(
                [
                    signal
                    for signal in signals
                    if _is_counter(signal)
                    and signal.normalized_label_fingerprint in labels
                ],
                semantic_clusters,
            )
            descriptor = "recurring_loop:" + "|".join(_node_text(node) for node in nodes)
            canonical_key = self._canonical_key(descriptor, user_id=user_id)
            prior = previous.get(("recurring_loop", canonical_key))
            clusters = _clusters(support, semantic_clusters)
            entries = {signal.entry_id for signal in support}
            dates = {signal.entry_date for signal in support}
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
            review_weight = prior.review_weight if prior else 1.0
            score = clamp01(score * review_weight)
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
                review_weight=review_weight,
                review_item_id=prior.review_item_id if prior else None,
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
        previous: Mapping[tuple[PatternType, str], PreviousCandidate],
        semantic_clusters: Mapping[UUID, str],
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
            support = _collapse(raw_support, semantic_clusters)
            counters = _collapse(
                [signal for signal in tagged if _is_counter(signal)], semantic_clusters
            )
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
            clusters = _clusters(support, semantic_clusters)
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
            review_weight = prior.review_weight if prior else 1.0
            score = clamp01(score * review_weight)
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
                review_weight=review_weight,
                review_item_id=prior.review_item_id if prior else None,
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


def _collapse(
    signals: Collection[CandidateSignal],
    semantic_clusters: Mapping[UUID, str] | None = None,
) -> list[CandidateSignal]:
    semantic_clusters = semantic_clusters or {}
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
        semantic_cluster = semantic_clusters.get(signal.id)
        identity = (
            semantic_cluster or signal.cluster_key,
            signal.signal_type,
            (
                "semantic"
                if semantic_cluster is not None
                else signal.normalized_label_fingerprint
            ),
            signal.loop_role,
        )
        chosen.setdefault(identity, signal)
    return sorted(chosen.values(), key=_signal_order)


def _clusters(
    signals: Collection[CandidateSignal],
    semantic_clusters: Mapping[UUID, str] | None = None,
) -> list[str]:
    semantic_clusters = semantic_clusters or {}
    return sorted(
        {semantic_clusters.get(signal.id, signal.cluster_key) for signal in signals}
    )


def _deduplicate_semantic_signals(
    signals: Sequence[CandidateSignal], semantic_clusters: Mapping[UUID, str]
) -> list[CandidateSignal]:
    chosen: dict[tuple[str, str, str | None], CandidateSignal] = {}
    untouched: list[CandidateSignal] = []
    for signal in sorted(
        signals,
        key=lambda item: (-item.confidence, *_signal_order(item)),
    ):
        semantic_cluster = semantic_clusters.get(signal.id)
        if semantic_cluster is None:
            untouched.append(signal)
            continue
        chosen.setdefault(
            (semantic_cluster, signal.signal_type, signal.loop_role), signal
        )
    return sorted([*untouched, *chosen.values()], key=_signal_order)


def _semantic_cluster_keys(
    signals: Sequence[CandidateSignal],
    neighbors: Sequence[SemanticNeighbor],
) -> dict[UUID, str]:
    by_id = {signal.id: signal for signal in signals}
    compatible_edges: dict[UUID, dict[UUID, SemanticNeighbor]] = defaultdict(dict)
    for neighbor in neighbors:
        anchor = by_id.get(neighbor.anchor_signal_id)
        candidate = by_id.get(neighbor.neighbor_signal_id)
        if (
            anchor is None
            or candidate is None
            or neighbor.similarity < SEMANTIC_SIMILARITY_THRESHOLD
            or not _semantic_signals_compatible(anchor, candidate)
        ):
            continue
        existing = compatible_edges[anchor.id].get(candidate.id)
        if existing is None or neighbor.similarity > existing.similarity:
            compatible_edges[anchor.id][candidate.id] = neighbor
        compatible_edges[candidate.id].setdefault(anchor.id, neighbor)

    result: dict[UUID, str] = {}
    for signal in sorted(signals, key=_signal_order):
        earlier = [
            (by_id[neighbor_id], edge)
            for neighbor_id, edge in compatible_edges.get(signal.id, {}).items()
            if _signal_order(by_id[neighbor_id]) < _signal_order(signal)
        ]
        if not earlier:
            continue
        chosen, _edge = min(
            earlier,
            key=lambda item: (
                -item[1].similarity,
                item[1].cosine_distance,
                _signal_order(item[0]),
            ),
        )
        # Deliberately use the direct neighbor's persisted cluster, not its computed
        # semantic root. This prevents A~B~C transitive chaining without A~C.
        result.setdefault(chosen.id, chosen.cluster_key)
        result[signal.id] = chosen.cluster_key
    return result


def _semantic_signals_compatible(
    left: CandidateSignal, right: CandidateSignal
) -> bool:
    if (
        left.entry_id == right.entry_id
        or left.user_id != right.user_id
        or left.entry_user_id != right.entry_user_id
        or left.analysis_user_id != right.analysis_user_id
        or left.analysis_eligibility != "accepted"
        or right.analysis_eligibility != "accepted"
        or left.signal_type != right.signal_type
        or left.loop_role != right.loop_role
        or _is_counter(left) != _is_counter(right)
    ):
        return False
    return bool(set(left.need_tags) & set(right.need_tags)) or bool(
        set(left.themes) & set(right.themes)
    )


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
) -> ConfidenceLabel:
    if candidate is not None and candidate.status == "rejected" and status == "candidate":
        return "preliminary"
    return confidence_label(supporting_entries)


def _lifecycle(
    candidate: PreviousCandidate | None,
    *,
    publishable: bool,
    support: Collection[CandidateSignal],
) -> tuple[CandidateStatus, datetime | None, int | None]:
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
    return signal.loop_role, loop_role_fingerprint(signal.loop_role)


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
