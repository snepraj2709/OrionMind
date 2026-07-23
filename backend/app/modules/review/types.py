from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Mapping, cast
from uuid import UUID


ReviewScope = Literal["entry_insight", "pattern"]
EntryInsightType = Literal[
    "energy_gain",
    "energy_loss",
    "self_knowledge",
    "realization",
    "explicit_preference",
    "need",
    "belief",
    "avoidance",
    "protective_strategy",
    "conflict",
    "causal_relationship",
]
PatternType = Literal["hidden_driver", "recurring_loop", "inner_tension"]
ReviewItemType = EntryInsightType | PatternType

EntryInsightCategory = Literal["energy", "self_knowledge", "needs_beliefs"]
PatternCategory = Literal["hidden_driver", "recurring_loop", "inner_tension"]
ReviewItemCategory = EntryInsightCategory | PatternCategory
ReviewCategoryFilter = Literal[
    "all",
    "energy",
    "self_knowledge",
    "needs_beliefs",
    "hidden_driver",
    "recurring_loop",
    "inner_tension",
]

ReviewStatus = Literal[
    "pending",
    "confirmed",
    "partially_confirmed",
    "rejected",
]
InferenceLevel = Literal["direct", "inferred", "synthesized"]

EntryInsightVerdict = Literal["accurate", "partly_accurate", "not_accurate"]
PatternVerdict = Literal["resonates", "partly_true", "not_true"]
ReviewVerdict = EntryInsightVerdict | PatternVerdict
EvidenceWeight = float

ENTRY_INSIGHT_TYPES: tuple[EntryInsightType, ...] = (
    "energy_gain",
    "energy_loss",
    "self_knowledge",
    "realization",
    "explicit_preference",
    "need",
    "belief",
    "avoidance",
    "protective_strategy",
    "conflict",
    "causal_relationship",
)
PATTERN_TYPES: tuple[PatternType, ...] = (
    "hidden_driver",
    "recurring_loop",
    "inner_tension",
)
ENTRY_INSIGHT_CATEGORIES: tuple[EntryInsightCategory, ...] = (
    "energy",
    "self_knowledge",
    "needs_beliefs",
)
PATTERN_CATEGORIES: tuple[PatternCategory, ...] = (
    "hidden_driver",
    "recurring_loop",
    "inner_tension",
)
REVIEW_STATUSES: tuple[ReviewStatus, ...] = (
    "pending",
    "confirmed",
    "partially_confirmed",
    "rejected",
)
ENTRY_INSIGHT_VERDICTS: tuple[EntryInsightVerdict, ...] = (
    "accurate",
    "partly_accurate",
    "not_accurate",
)
PATTERN_VERDICTS: tuple[PatternVerdict, ...] = (
    "resonates",
    "partly_true",
    "not_true",
)
ENTRY_INSIGHT_CATEGORY_BY_TYPE: Mapping[
    EntryInsightType, EntryInsightCategory
] = {
    "energy_gain": "energy",
    "energy_loss": "energy",
    "self_knowledge": "self_knowledge",
    "realization": "self_knowledge",
    "explicit_preference": "self_knowledge",
    "need": "needs_beliefs",
    "belief": "needs_beliefs",
    "avoidance": "needs_beliefs",
    "protective_strategy": "needs_beliefs",
    "conflict": "needs_beliefs",
    "causal_relationship": "needs_beliefs",
}
PATTERN_CATEGORY_BY_TYPE: Mapping[PatternType, PatternCategory] = {
    "hidden_driver": "hidden_driver",
    "recurring_loop": "recurring_loop",
    "inner_tension": "inner_tension",
}


@dataclass(frozen=True, slots=True)
class FeedbackDecision:
    status: ReviewStatus
    evidence_weight: EvidenceWeight


@dataclass(frozen=True, slots=True)
class ReviewItemRecord:
    id: UUID
    user_id: UUID
    entry_id: UUID | None
    entry_signal_id: UUID | None
    pattern_candidate_id: UUID | None
    scope: ReviewScope
    item_type: ReviewItemType
    category: ReviewItemCategory
    statement_envelope: dict[str, object]
    source_quote_envelope: dict[str, object] | None
    source_entry_ids: tuple[UUID, ...]
    source_dates: tuple[date, ...]
    inference_level: InferenceLevel
    model_confidence: float
    review_status: ReviewStatus
    user_feedback: dict[str, object] | None
    corrected_statement_envelope: dict[str, object] | None
    feedback_note_envelope: dict[str, object] | None
    evidence_weight: EvidenceWeight
    reflection_eligible: bool
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime


ENTRY_INSIGHT_FEEDBACK_DECISIONS: Mapping[
    EntryInsightVerdict, FeedbackDecision
] = {
    "accurate": FeedbackDecision(status="confirmed", evidence_weight=1.0),
    "partly_accurate": FeedbackDecision(
        status="partially_confirmed", evidence_weight=0.5
    ),
    "not_accurate": FeedbackDecision(status="rejected", evidence_weight=0.0),
}
PATTERN_FEEDBACK_DECISIONS: Mapping[PatternVerdict, FeedbackDecision] = {
    "resonates": FeedbackDecision(status="confirmed", evidence_weight=1.0),
    "partly_true": FeedbackDecision(
        status="partially_confirmed", evidence_weight=0.5
    ),
    "not_true": FeedbackDecision(status="rejected", evidence_weight=0.0),
}


def category_allowed_for_scope(
    *,
    scope: ReviewScope,
    category: ReviewCategoryFilter,
) -> bool:
    if category == "all":
        return True
    if scope == "entry_insight":
        return category in ENTRY_INSIGHT_CATEGORIES
    return category in PATTERN_CATEGORIES


def feedback_decision(
    *,
    scope: ReviewScope,
    verdict: ReviewVerdict,
) -> FeedbackDecision:
    if scope == "entry_insight":
        if verdict not in ENTRY_INSIGHT_VERDICTS:
            raise ValueError("verdict is not valid for an entry insight")
        return ENTRY_INSIGHT_FEEDBACK_DECISIONS[
            cast(EntryInsightVerdict, verdict)
        ]
    if verdict not in PATTERN_VERDICTS:
        raise ValueError("verdict is not valid for a pattern")
    return PATTERN_FEEDBACK_DECISIONS[cast(PatternVerdict, verdict)]
