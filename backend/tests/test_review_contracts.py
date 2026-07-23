from __future__ import annotations

from datetime import datetime, timezone
from typing import get_args
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.processing.schemas import SignalType
from app.modules.reflections.schemas import (
    AvailableHiddenDriver,
    ProcessingInsight,
    ReflectionSectionStatus,
    UnavailableInsight,
)
from app.modules.review.schemas import (
    REVIEW_CORRECTION_MAX_LENGTH,
    REVIEW_NOTE_MAX_LENGTH,
    REVIEW_SOURCE_QUOTE_MAX_LENGTH,
    REVIEW_STATEMENT_MAX_LENGTH,
    EntryInsightFeedback,
    PatternFeedback,
    ReviewFeedbackRequest,
    ReviewItemsResponse,
    ReviewListQuery,
)
from app.modules.review.types import (
    ENTRY_INSIGHT_CATEGORIES,
    ENTRY_INSIGHT_CATEGORY_BY_TYPE,
    ENTRY_INSIGHT_TYPES,
    ENTRY_INSIGHT_VERDICTS,
    PATTERN_CATEGORIES,
    PATTERN_CATEGORY_BY_TYPE,
    PATTERN_TYPES,
    PATTERN_VERDICTS,
    REVIEW_STATUSES,
    EntryInsightCategory,
    EntryInsightType,
    EntryInsightVerdict,
    FeedbackDecision,
    InferenceLevel,
    PatternCategory,
    PatternType,
    PatternVerdict,
    ReviewCategoryFilter,
    ReviewScope,
    ReviewStatus,
    feedback_decision,
)


ITEM_ID = UUID("81111111-1111-4111-8111-111111111111")
ENTRY_ID = UUID("82222222-2222-4222-8222-222222222222")
PATTERN_ENTRY_ID = UUID("83333333-3333-4333-8333-333333333333")
UPDATED_AT = datetime(2026, 7, 23, 10, 30, tzinfo=timezone.utc)


def entry_item_payload() -> dict[str, object]:
    return {
        "id": str(ITEM_ID),
        "scope": "entry_insight",
        "type": "energy_loss",
        "category": "energy",
        "statement": "Preparing at the last minute drained your energy.",
        "sourceQuote": "The rushed preparation was exhausting.",
        "sourceEntryIds": [str(ENTRY_ID)],
        "sourceDates": ["2026-07-20"],
        "inferenceLevel": "direct",
        "confidence": 0.94,
        "status": "pending",
        "feedback": None,
    }


def pattern_item_payload() -> dict[str, object]:
    return {
        "id": str(ITEM_ID),
        "scope": "pattern",
        "type": "hidden_driver",
        "category": "hidden_driver",
        "statement": "Perfection may protect you from being evaluated.",
        "sourceQuote": None,
        "sourceEntryIds": [str(ENTRY_ID), str(PATTERN_ENTRY_ID)],
        "sourceDates": ["2026-07-20", "2026-07-22"],
        "inferenceLevel": "synthesized",
        "confidence": 0.82,
        "status": "partially_confirmed",
        "feedback": {
            "verdict": "partly_true",
            "correctedStatement": None,
            "note": "This fits only around work.",
            "evidenceWeight": 0.5,
            "updatedAt": "2026-07-23T10:30:00Z",
        },
    }


def test_review_vocabulary_is_closed_and_processing_retains_all_signal_types() -> None:
    assert ENTRY_INSIGHT_TYPES == (
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
    assert PATTERN_TYPES == ("hidden_driver", "recurring_loop", "inner_tension")
    assert ENTRY_INSIGHT_CATEGORIES == (
        "energy",
        "self_knowledge",
        "needs_beliefs",
    )
    assert PATTERN_CATEGORIES == (
        "hidden_driver",
        "recurring_loop",
        "inner_tension",
    )
    assert REVIEW_STATUSES == (
        "pending",
        "confirmed",
        "partially_confirmed",
        "rejected",
    )
    assert ENTRY_INSIGHT_VERDICTS == (
        "accurate",
        "partly_accurate",
        "not_accurate",
    )
    assert PATTERN_VERDICTS == ("resonates", "partly_true", "not_true")
    assert set(ENTRY_INSIGHT_TYPES).issubset(set(get_args(SignalType)))
    assert {
        "event",
        "emotion",
        "desire",
        "self_statement",
        "action",
        "outcome",
    }.issubset(set(get_args(SignalType)))
    assert set(ENTRY_INSIGHT_CATEGORY_BY_TYPE) == set(ENTRY_INSIGHT_TYPES)
    assert set(PATTERN_CATEGORY_BY_TYPE) == set(PATTERN_TYPES)
    assert get_args(ReviewScope) == ("entry_insight", "pattern")
    assert get_args(EntryInsightType) == ENTRY_INSIGHT_TYPES
    assert get_args(PatternType) == PATTERN_TYPES
    assert get_args(EntryInsightCategory) == ENTRY_INSIGHT_CATEGORIES
    assert get_args(PatternCategory) == PATTERN_CATEGORIES
    assert get_args(ReviewCategoryFilter) == (
        "all",
        *ENTRY_INSIGHT_CATEGORIES,
        *PATTERN_CATEGORIES,
    )
    assert get_args(ReviewStatus) == REVIEW_STATUSES
    assert get_args(InferenceLevel) == ("direct", "inferred", "synthesized")
    assert get_args(EntryInsightVerdict) == ENTRY_INSIGHT_VERDICTS
    assert get_args(PatternVerdict) == PATTERN_VERDICTS


@pytest.mark.parametrize(
    ("scope", "verdict", "expected"),
    [
        ("entry_insight", "accurate", FeedbackDecision("confirmed", 1.0)),
        (
            "entry_insight",
            "partly_accurate",
            FeedbackDecision("partially_confirmed", 0.5),
        ),
        ("entry_insight", "not_accurate", FeedbackDecision("rejected", 0.0)),
        ("pattern", "resonates", FeedbackDecision("confirmed", 1.0)),
        ("pattern", "partly_true", FeedbackDecision("partially_confirmed", 0.5)),
        ("pattern", "not_true", FeedbackDecision("rejected", 0.0)),
    ],
)
def test_feedback_mapping_is_exact(scope, verdict, expected: FeedbackDecision) -> None:
    assert feedback_decision(scope=scope, verdict=verdict) == expected


@pytest.mark.parametrize(
    ("scope", "verdict"),
    [
        ("entry_insight", "resonates"),
        ("entry_insight", "partly_true"),
        ("entry_insight", "not_true"),
        ("pattern", "accurate"),
        ("pattern", "partly_accurate"),
        ("pattern", "not_accurate"),
    ],
)
def test_feedback_rejects_every_cross_scope_verdict(scope, verdict) -> None:
    request = ReviewFeedbackRequest(verdict=verdict)
    with pytest.raises(ValueError, match="not valid"):
        request.decision_for_scope(scope)


@pytest.mark.parametrize(
    ("scope", "category"),
    [
        ("entry_insight", "energy"),
        ("entry_insight", "self_knowledge"),
        ("entry_insight", "needs_beliefs"),
        ("pattern", "hidden_driver"),
        ("pattern", "recurring_loop"),
        ("pattern", "inner_tension"),
    ],
)
def test_list_query_accepts_scope_categories_and_applies_defaults(
    scope: str, category: str
) -> None:
    query = ReviewListQuery(scope=scope, category=category)
    assert query.status == "pending"
    assert query.page == 1
    assert query.page_size == 20
    assert query.model_dump() == {
        "scope": scope,
        "category": category,
        "status": "pending",
        "page": 1,
        "page_size": 20,
    }


@pytest.mark.parametrize(
    ("scope", "category"),
    [
        ("entry_insight", "hidden_driver"),
        ("entry_insight", "recurring_loop"),
        ("entry_insight", "inner_tension"),
        ("pattern", "energy"),
        ("pattern", "self_knowledge"),
        ("pattern", "needs_beliefs"),
    ],
)
def test_list_query_rejects_every_cross_scope_category(
    scope: str, category: str
) -> None:
    with pytest.raises(ValidationError, match="category is not valid"):
        ReviewListQuery(scope=scope, category=category)


@pytest.mark.parametrize(
    "payload",
    [
        {"scope": "entry_insight", "page": 0},
        {"scope": "entry_insight", "page_size": 0},
        {"scope": "entry_insight", "page_size": 101},
        {"scope": "entry_insight", "pageSize": 20},
        {"scope": "entry_insight", "unexpected": True},
    ],
)
def test_list_query_rejects_unknown_or_out_of_bounds_values(
    payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        ReviewListQuery.model_validate(payload)


def test_feedback_text_limits_and_blank_normalization_are_locked() -> None:
    request = ReviewFeedbackRequest(
        verdict="accurate",
        correctedStatement="   ",
        note="\n",
    )
    assert request.corrected_statement is None
    assert request.note is None

    for field, maximum in (
        ("correctedStatement", REVIEW_CORRECTION_MAX_LENGTH),
        ("note", REVIEW_NOTE_MAX_LENGTH),
    ):
        with pytest.raises(ValidationError):
            ReviewFeedbackRequest.model_validate(
                {"verdict": "accurate", field: "x" * (maximum + 1)}
            )

    with pytest.raises(ValidationError):
        ReviewFeedbackRequest.model_validate(
            {"verdict": "accurate", "unexpected": True}
        )


def test_entry_and_pattern_items_serialize_with_exact_public_casing() -> None:
    response = ReviewItemsResponse.model_validate(
        {
            "items": [entry_item_payload(), pattern_item_payload()],
            "pagination": {"page": 1, "pageSize": 20, "total": 2},
        }
    )

    body = response.model_dump(mode="json", by_alias=True)
    assert body == {
        "items": [entry_item_payload(), pattern_item_payload()],
        "pagination": {"page": 1, "pageSize": 20, "total": 2},
    }
    assert "itemType" not in body["items"][0]
    assert "source_entry_ids" not in body["items"][0]


@pytest.mark.parametrize(
    "mutation",
    [
        {"category": "self_knowledge"},
        {"inferenceLevel": "synthesized"},
        {"confidence": 1.01},
        {"statement": "x" * (REVIEW_STATEMENT_MAX_LENGTH + 1)},
        {"sourceQuote": "x" * (REVIEW_SOURCE_QUOTE_MAX_LENGTH + 1)},
        {"status": "confirmed"},
        {"sourceEntryIds": [str(ENTRY_ID), str(PATTERN_ENTRY_ID)]},
        {"unexpected": True},
    ],
)
def test_entry_item_rejects_invalid_category_shape_bounds_and_fields(
    mutation: dict[str, object]
) -> None:
    payload = {**entry_item_payload(), **mutation}
    with pytest.raises(ValidationError):
        ReviewItemsResponse.model_validate(
            {
                "items": [payload],
                "pagination": {"page": 1, "pageSize": 20, "total": 1},
            }
        )


def test_feedback_response_rejects_inconsistent_weight() -> None:
    with pytest.raises(ValidationError, match="evidence weight"):
        EntryInsightFeedback(
            verdict="partly_accurate",
            corrected_statement=None,
            note=None,
            evidence_weight=1.0,
            updated_at=UPDATED_AT,
        )
    with pytest.raises(ValidationError, match="evidence weight"):
        PatternFeedback(
            verdict="not_true",
            corrected_statement=None,
            note=None,
            evidence_weight=0.5,
            updated_at=UPDATED_AT,
        )


def test_reflection_section_state_vocabulary_is_strict_and_additive() -> None:
    assert get_args(ReflectionSectionStatus) == (
        "available",
        "processing",
        "insufficient_evidence",
        "unavailable",
    )
    processing = ProcessingInsight(
        message="Your reflection is being recalculated."
    )
    unavailable = UnavailableInsight(
        reasonCode="TECHNICAL_FAILURE",
        message="This section is temporarily unavailable.",
        retryable=True,
    )
    available = AvailableHiddenDriver(
        id=ITEM_ID,
        confidence="emerging",
        score=0.74,
        evidence_entry_count=3,
        evidence=[],
        feedback=None,
        statement="A possible pattern.",
        underlying_need="competence",
        drivers=[],
    )

    assert processing.model_dump(mode="json", by_alias=True) == {
        "status": "processing",
        "message": "Your reflection is being recalculated.",
    }
    assert unavailable.model_dump(mode="json", by_alias=True) == {
        "status": "unavailable",
        "reasonCode": "TECHNICAL_FAILURE",
        "message": "This section is temporarily unavailable.",
        "retryable": True,
    }
    assert available.status == "available"

    with pytest.raises(ValidationError):
        ProcessingInsight.model_validate(
            {"status": "processing", "message": "Working.", "extra": True}
        )
