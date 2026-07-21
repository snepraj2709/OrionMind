from __future__ import annotations

import re
from collections import Counter
from collections.abc import Collection, Mapping
from typing import Literal, TypeAlias
from uuid import UUID

from app.modules.processing.schemas import LoopRole
from app.modules.reflection_engine.schemas import (
    CandidateSignal,
    ConstructedCandidate,
    HiddenDriverStructure,
    InnerTensionStructure,
    RecurringLoopStructure,
)


EvidenceRejectionCode: TypeAlias = Literal[
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
]


LOOP_ROLE_TRANSITIONS: frozenset[tuple[LoopRole, LoopRole]] = frozenset(
    {
        ("trigger", "initial_reward"),
        ("trigger", "interpretation"),
        ("trigger", "emotional_response"),
        ("trigger", "action"),
        ("trigger", "avoidance"),
        ("initial_reward", "interpretation"),
        ("initial_reward", "emotional_response"),
        ("initial_reward", "action"),
        ("initial_reward", "avoidance"),
        ("interpretation", "emotional_response"),
        ("interpretation", "action"),
        ("interpretation", "avoidance"),
        ("interpretation", "short_term_protection"),
        ("interpretation", "long_term_cost"),
        ("emotional_response", "action"),
        ("emotional_response", "avoidance"),
        ("emotional_response", "short_term_protection"),
        ("action", "short_term_protection"),
        ("action", "long_term_cost"),
        ("action", "recovery"),
        ("action", "reinforcement"),
        ("avoidance", "short_term_protection"),
        ("avoidance", "long_term_cost"),
        ("avoidance", "recovery"),
        ("avoidance", "reinforcement"),
        ("short_term_protection", "long_term_cost"),
        ("short_term_protection", "recovery"),
        ("short_term_protection", "reinforcement"),
        ("long_term_cost", "recovery"),
        ("long_term_cost", "reinforcement"),
        ("long_term_cost", "trigger"),
        ("recovery", "reinforcement"),
        ("recovery", "trigger"),
        ("recovery", "initial_reward"),
        ("reinforcement", "trigger"),
        ("reinforcement", "initial_reward"),
        ("reinforcement", "interpretation"),
    }
)

DIAGNOSTIC_LANGUAGE = re.compile(
    r"\b(?:diagnos(?:is|ed|tic)|disorder|syndrome|adhd|ocd|autis(?:m|tic)|"
    r"bipolar|narciss(?:ism|istic)|clinical depression|anxiety disorder)\b",
    re.IGNORECASE,
)
FIXED_IDENTITY_LANGUAGE = re.compile(
    r"\b(?:you are|your personality is|you always|you never|always|never)\b",
    re.IGNORECASE,
)
ELIMINATION_LANGUAGE = re.compile(
    r"\b(?:eliminate|erase|abandon|suppress|ignore|give up|remove|destroy|"
    r"choose only|stop needing)\b",
    re.IGNORECASE,
)


def loop_node_key(role: LoopRole, label_fingerprint: str) -> str:
    return f"{role}:{label_fingerprint}"


def transition_key(
    left_role: LoopRole,
    left_label_fingerprint: str,
    right_role: LoopRole,
    right_label_fingerprint: str,
) -> str:
    return (
        f"{loop_node_key(left_role, left_label_fingerprint)}->"
        f"{loop_node_key(right_role, right_label_fingerprint)}"
    )


def roles_are_compatible(left: LoopRole, right: LoopRole) -> bool:
    return (left, right) in LOOP_ROLE_TRANSITIONS


class EvidenceValidator:
    def validate_candidate(
        self,
        candidate: ConstructedCandidate,
        *,
        user_id: UUID,
        signals: Mapping[UUID, CandidateSignal],
        basis_start,
        basis_end,
        expected_counter_signal_ids: Collection[UUID] = (),
        transition_support: Mapping[str, tuple[int, int]] | None = None,
    ) -> tuple[EvidenceRejectionCode, ...]:
        reasons: list[EvidenceRejectionCode] = []
        support = self._resolve(
            candidate.support_signal_ids,
            signals=signals,
            reasons=reasons,
        )
        counters = self._resolve(
            candidate.counter_signal_ids,
            signals=signals,
            reasons=reasons,
        )
        for signal in (*support, *counters):
            reasons.extend(
                self.validate_signal(
                    signal,
                    user_id=user_id,
                    basis_start=basis_start,
                    basis_end=basis_end,
                )
            )
        expected_counters = set(expected_counter_signal_ids)
        if expected_counters != set(candidate.counter_signal_ids):
            reasons.append("COUNTEREVIDENCE_OMITTED")
        identities = [
            (
                signal.cluster_key,
                signal.signal_type,
                signal.normalized_label_fingerprint,
                signal.loop_role,
            )
            for signal in support
        ]
        if len(identities) != len(set(identities)):
            reasons.append("DUPLICATE_EVIDENCE")
        if set(candidate.support_clusters) != {signal.cluster_key for signal in support}:
            reasons.append("DUPLICATE_EVIDENCE")
        if candidate.publication_gate_passed:
            dates = {signal.entry_date for signal in support}
            if len(dates) < 2:
                reasons.append("EVIDENCE_DATE_DIVERSITY")
            by_entry = Counter(signal.entry_id for signal in support)
            if by_entry and max(by_entry.values()) / len(support) > 0.40:
                reasons.append("SINGLE_ENTRY_DOMINANCE")
        reasons.extend(
            self._validate_role_compatibility(
                candidate,
                signals=signals,
                transition_support=transition_support or {},
            )
        )
        reasons.extend(self._validate_language(candidate))
        return tuple(dict.fromkeys(reasons))

    def validate_signal(
        self,
        signal: CandidateSignal,
        *,
        user_id: UUID,
        basis_start,
        basis_end,
    ) -> tuple[EvidenceRejectionCode, ...]:
        reasons: list[EvidenceRejectionCode] = []
        if (
            signal.user_id != user_id
            or signal.entry_user_id != user_id
            or signal.analysis_user_id != user_id
        ):
            reasons.append("EVIDENCE_OWNER_MISMATCH")
        if signal.analysis_entry_id != signal.entry_id:
            reasons.append("EVIDENCE_ENTRY_MISMATCH")
        if signal.analysis_eligibility != "accepted":
            reasons.append("EVIDENCE_ANALYSIS_NOT_ACCEPTED")
        if (
            basis_start is None
            or basis_end is None
            or not basis_start <= signal.entry_date <= basis_end
        ):
            reasons.append("EVIDENCE_OUTSIDE_BASIS")
        if not (
            0
            <= signal.source_start
            < signal.source_end
            <= len(signal.entry_text)
        ):
            reasons.append("EVIDENCE_OFFSET_OUT_OF_BOUNDS")
        elif (
            signal.entry_text[signal.source_start : signal.source_end]
            != signal.source_quote
        ):
            reasons.append("EVIDENCE_OFFSET_MISMATCH")
        return tuple(reasons)

    @staticmethod
    def _resolve(
        signal_ids: Collection[UUID],
        *,
        signals: Mapping[UUID, CandidateSignal],
        reasons: list[EvidenceRejectionCode],
    ) -> tuple[CandidateSignal, ...]:
        resolved: list[CandidateSignal] = []
        for signal_id in signal_ids:
            signal = signals.get(signal_id)
            if signal is None:
                reasons.append("EVIDENCE_SIGNAL_MISSING")
            else:
                resolved.append(signal)
        return tuple(resolved)

    def _validate_role_compatibility(
        self,
        candidate: ConstructedCandidate,
        *,
        signals: Mapping[UUID, CandidateSignal],
        transition_support: Mapping[str, tuple[int, int]],
    ) -> tuple[EvidenceRejectionCode, ...]:
        structure = candidate.structure
        reasons: list[EvidenceRejectionCode] = []
        if isinstance(structure, HiddenDriverStructure):
            for signal_id in candidate.support_signal_ids:
                signal = signals.get(signal_id)
                if signal is not None and structure.canonical_need not in signal.need_tags:
                    reasons.append("EVIDENCE_ROLE_MISMATCH")
        elif isinstance(structure, RecurringLoopStructure):
            if not 3 <= len(structure.steps) <= 6:
                reasons.append("LOOP_STEP_COUNT")
            assigned: set[UUID] = set()
            for step in structure.steps:
                for signal_id in step.support_signal_ids:
                    signal = signals.get(signal_id)
                    if (
                        signal is None
                        or signal.loop_role != step.loop_role
                        or signal.normalized_label_fingerprint
                        != step.normalized_label_fingerprint
                    ):
                        reasons.append("EVIDENCE_ROLE_MISMATCH")
                    assigned.add(signal_id)
            if assigned != set(candidate.support_signal_ids):
                reasons.append("EVIDENCE_ROLE_MISMATCH")
            required = []
            for left, right in zip(structure.steps, structure.steps[1:]):
                if not roles_are_compatible(left.loop_role, right.loop_role):
                    reasons.append("LOOP_TRANSITION_UNSUPPORTED")
                required.append(
                    transition_key(
                        left.loop_role,
                        left.normalized_label_fingerprint,
                        right.loop_role,
                        right.normalized_label_fingerprint,
                    )
                )
            first = structure.steps[0]
            last = structure.steps[-1]
            closing = transition_key(
                last.loop_role,
                last.normalized_label_fingerprint,
                first.loop_role,
                first.normalized_label_fingerprint,
            )
            if not roles_are_compatible(last.loop_role, first.loop_role):
                reasons.append("LOOP_CLOSURE_UNSUPPORTED")
            for key in required:
                chains, entries = transition_support.get(key, (0, 0))
                if chains < 2 or entries < 2:
                    reasons.append("LOOP_TRANSITION_UNSUPPORTED")
            closing_chains, closing_entries = transition_support.get(closing, (0, 0))
            if closing_chains < 2 or closing_entries < 2:
                reasons.append("LOOP_CLOSURE_UNSUPPORTED")
        elif isinstance(structure, InnerTensionStructure):
            left_ids = set(structure.left_support_signal_ids)
            right_ids = set(structure.right_support_signal_ids)
            if not left_ids or not right_ids:
                reasons.append("TENSION_SIDE_MISSING")
            if left_ids | right_ids != set(candidate.support_signal_ids):
                reasons.append("EVIDENCE_ROLE_MISMATCH")
            for signal_id in left_ids:
                signal = signals.get(signal_id)
                if signal is not None and structure.left_need not in signal.need_tags:
                    reasons.append("EVIDENCE_ROLE_MISMATCH")
            for signal_id in right_ids:
                signal = signals.get(signal_id)
                if signal is not None and structure.right_need not in signal.need_tags:
                    reasons.append("EVIDENCE_ROLE_MISMATCH")
            if not self.integration_honors_both_sides(
                structure.integration,
                left_need=structure.left_need,
                right_need=structure.right_need,
            ):
                reasons.append("TENSION_INTEGRATION_INVALID")
        return tuple(dict.fromkeys(reasons))

    @staticmethod
    def integration_honors_both_sides(
        text: str, *, left_need: str, right_need: str
    ) -> bool:
        normalized = text.casefold().replace("_", " ")
        left = left_need.casefold().replace("_", " ")
        right = right_need.casefold().replace("_", " ")
        return (
            left in normalized
            and right in normalized
            and ELIMINATION_LANGUAGE.search(normalized) is None
        )

    @staticmethod
    def _validate_language(
        candidate: ConstructedCandidate,
    ) -> tuple[EvidenceRejectionCode, ...]:
        structure = candidate.structure
        if isinstance(structure, HiddenDriverStructure):
            statements = (structure.statement,)
            framed = "a possible pattern across your entries" in structure.statement.casefold()
        elif isinstance(structure, RecurringLoopStructure):
            statements = (
                structure.title,
                structure.description,
                *(step.statement for step in structure.steps if step.statement),
                *((structure.protection,) if structure.protection else ()),
                *((structure.interruption,) if structure.interruption else ()),
            )
            framed = "a possible" in structure.description.casefold()
        else:
            statements = (
                structure.left_statement,
                structure.right_statement,
                structure.integration,
            )
            framed = "you may be trying to hold" in structure.integration.casefold()
        reasons: list[EvidenceRejectionCode] = []
        if any(DIAGNOSTIC_LANGUAGE.search(value) for value in statements):
            reasons.append("UNSAFE_DIAGNOSTIC_LANGUAGE")
        if any(FIXED_IDENTITY_LANGUAGE.search(value) for value in statements):
            reasons.append("UNSAFE_IDENTITY_LANGUAGE")
        if not framed:
            reasons.append("HYPOTHESIS_FRAMING_REQUIRED")
        return tuple(reasons)
