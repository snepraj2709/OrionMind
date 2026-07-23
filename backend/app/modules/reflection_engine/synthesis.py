from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Literal, TypeAlias
from uuid import UUID

from app.modules.reflection_engine.ordering import signal_order
from app.modules.reflection_engine.schemas import (
    CandidateSignal,
    ConstructedCandidate,
    InnerTensionStructure,
    PatternType,
    RecurringLoopStructure,
    ReflectionCriticOutput,
    SynthesisEvidenceReference,
)


PUBLICATION_THRESHOLDS = {
    "hidden_driver": 0.68,
    "recurring_loop": 0.72,
    "inner_tension": 0.70,
}


SynthesisSectionStatus: TypeAlias = Literal[
    "available",
    "insufficient_evidence",
]


def synthesis_section_status(
    *,
    pattern_type: PatternType,
    selected_pattern_types: Collection[PatternType],
) -> SynthesisSectionStatus:
    return (
        "available"
        if pattern_type in selected_pattern_types
        else "insufficient_evidence"
    )


def critic_required(candidate: ConstructedCandidate) -> bool:
    """Return the exact deterministic P0 critic routing decision."""

    threshold = PUBLICATION_THRESHOLDS[candidate.pattern_type]
    return (
        round(abs(candidate.score - threshold), 10) <= 0.05
        or candidate.score_components.contradiction >= 0.20
    )


def _critic_allows_publication(value: object) -> bool:
    critique = (
        value
        if isinstance(value, ReflectionCriticOutput)
        else ReflectionCriticOutput.model_validate(value)
    )
    return (
        critique.recommended_action == "publish"
        and critique.entailed
        and not critique.overreaches
        and not critique.contradictory_evidence_ignored
        and not critique.diagnostic_language
        and critique.evidence_diversity_adequate
    )


def _references_match(
    references: Sequence[SynthesisEvidenceReference],
    expected: Collection[tuple[UUID, str]],
) -> bool:
    actual = [(item.signal_id, item.evidence_role) for item in references]
    return len(actual) == len(set(actual)) and set(actual) == set(expected)


def _final_transition_support(
    candidate: ConstructedCandidate,
) -> Mapping[str, tuple[int, int]]:
    structure = candidate.structure
    if not isinstance(structure, RecurringLoopStructure):
        return {}
    # These keys were generated only from transitions that P0-05 proved across
    # at least two chains and two entries. The model cannot alter the role or
    # fingerprint fields, so presence remains the authoritative local proof.
    return {key: (2, 2) for key in structure.transition_keys}


def _select_snapshot_candidates(
    candidates: Sequence[ConstructedCandidate],
) -> list[ConstructedCandidate]:
    ordered = sorted(
        candidates,
        key=lambda item: (-item.score, item.canonical_key, str(item.id)),
    )
    selected: list[ConstructedCandidate] = []
    for pattern_type in ("hidden_driver", "recurring_loop"):
        candidate = next(
            (item for item in ordered if item.pattern_type == pattern_type),
            None,
        )
        if candidate is not None:
            selected.append(candidate)
    selected.extend(
        [item for item in ordered if item.pattern_type == "inner_tension"][:5]
    )
    return selected


def _select_synthesis_candidates(
    candidates: Sequence[ConstructedCandidate],
) -> list[ConstructedCandidate]:
    ordered = sorted(
        candidates,
        key=lambda item: (-item.score, item.canonical_key, str(item.id)),
    )
    limits = {
        "hidden_driver": 15,
        "recurring_loop": 6,
        "inner_tension": 8,
    }
    selected: list[ConstructedCandidate] = []
    for pattern_type, limit in limits.items():
        selected.extend(
            [
                item
                for item in ordered
                if item.pattern_type == pattern_type
            ][:limit],
        )
    return selected


def _select_synthesis_support_ids(
    candidate: ConstructedCandidate,
    signals: Sequence[CandidateSignal],
) -> list[UUID]:
    """Bound model context while retaining diverse, deterministic evidence."""
    by_id = {signal.id: signal for signal in signals}

    def diverse(identifiers: Sequence[UUID], limit: int) -> list[UUID]:
        ordered = sorted(
            (by_id[item] for item in identifiers),
            key=lambda item: (-item.confidence, *signal_order(item)),
        )
        chosen: list[CandidateSignal] = []
        seen_entries: set[UUID] = set()
        seen_types: set[str] = set()
        for require_new_type in (True, False):
            for signal in ordered:
                if signal in chosen or signal.entry_id in seen_entries:
                    continue
                if require_new_type and signal.signal_type in seen_types:
                    continue
                chosen.append(signal)
                seen_entries.add(signal.entry_id)
                seen_types.add(signal.signal_type)
                if len(chosen) == limit:
                    return [item.id for item in chosen]
        for signal in ordered:
            if signal not in chosen:
                chosen.append(signal)
                if len(chosen) == limit:
                    break
        return [item.id for item in chosen]

    if isinstance(candidate.structure, InnerTensionStructure):
        selected = [
            *diverse(candidate.structure.left_support_signal_ids, 4),
            *diverse(candidate.structure.right_support_signal_ids, 4),
        ]
    elif isinstance(candidate.structure, RecurringLoopStructure):
        selected = [
            signal_id
            for step in candidate.structure.steps
            for signal_id in diverse(step.support_signal_ids, 2)
        ]
    else:
        selected = diverse(candidate.support_signal_ids, 8)
    return list(dict.fromkeys(selected))


def _snapshot_candidate_status(
    candidate: ConstructedCandidate,
    *,
    published: bool,
) -> ConstructedCandidate:
    if published:
        status = "published"
    elif candidate.status in {"rejected", "weakened", "superseded"}:
        status = candidate.status
    else:
        status = "candidate"
    return candidate.model_copy(update={"status": status})
