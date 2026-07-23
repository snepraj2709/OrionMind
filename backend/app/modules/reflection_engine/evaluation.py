from __future__ import annotations

from datetime import date
from math import isclose
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.processing.materialization import expected_review_item_count
from app.modules.processing.schemas import Eligibility, ThemeKey
from app.modules.reflection_engine.evidence import (
    EvidenceRejectionCode,
    evidence_presence_rejection_codes,
    evidence_signal_rejection_codes,
)
from app.modules.reflection_engine.schemas import (
    PatternType,
    review_weighted_confidence,
)
from app.modules.reflection_engine.synthesis import synthesis_section_status


Polarity = Literal["positive", "negative", "mixed", "neutral", "none"]


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FrozenSpan(EvaluationModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> "FrozenSpan":
        if self.end <= self.start:
            raise ValueError("evaluation span is invalid")
        return self


class FrozenExtraction(EvaluationModel):
    idea_spans: list[FrozenSpan] = Field(max_length=100)
    memory_spans: list[FrozenSpan] = Field(max_length=100)
    top_theme: ThemeKey | None
    invalid_structured_output: bool
    reflection_polarity: dict[
        Literal["filled_energy", "drained_energy", "learned_about_self"],
        Polarity,
    ]

    @model_validator(mode="after")
    def unique_spans(self) -> "FrozenExtraction":
        for spans in (self.idea_spans, self.memory_spans):
            identities = [(item.start, item.end) for item in spans]
            if len(identities) != len(set(identities)):
                raise ValueError("evaluation spans must be unique")
        return self


class FrozenEvaluationRecord(EvaluationModel):
    entry_id: UUID
    consent_granted: bool
    expected: FrozenExtraction
    combined_analyzer: FrozenExtraction
    legacy_invalid_structured_output: bool


class FrozenEvaluationDataset(EvaluationModel):
    version: Literal[1]
    records: list[FrozenEvaluationRecord]

    @model_validator(mode="after")
    def unique_entries(self) -> "FrozenEvaluationDataset":
        identifiers = [item.entry_id for item in self.records]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("evaluation entry IDs must be unique")
        return self


class EvaluationResult(EvaluationModel):
    record_count: int
    exact_span_precision: float
    top_theme_agreement: float
    combined_invalid_structured_outputs: int
    legacy_invalid_structured_outputs: int
    reflection_polarity_regressions: int
    passed: bool


class EvaluationDatasetRejected(ValueError):
    pass


def evaluate_frozen_dataset(dataset: FrozenEvaluationDataset) -> EvaluationResult:
    if len(dataset.records) < 100:
        raise EvaluationDatasetRejected(
            "evaluation requires at least 100 frozen records"
        )
    if any(not record.consent_granted for record in dataset.records):
        raise EvaluationDatasetRejected(
            "evaluation data must have explicit consent for every record"
        )

    predicted = 0
    matched = 0
    expected_span_count = 0
    theme_matches = 0
    combined_invalid = 0
    legacy_invalid = 0
    polarity_regressions = 0
    for record in dataset.records:
        for expected_spans, actual_spans in (
            (record.expected.idea_spans, record.combined_analyzer.idea_spans),
            (record.expected.memory_spans, record.combined_analyzer.memory_spans),
        ):
            expected = {(item.start, item.end) for item in expected_spans}
            actual = {(item.start, item.end) for item in actual_spans}
            expected_span_count += len(expected)
            predicted += len(actual)
            matched += len(expected & actual)
        theme_matches += int(
            record.combined_analyzer.top_theme == record.expected.top_theme
        )
        combined_invalid += int(record.combined_analyzer.invalid_structured_output)
        legacy_invalid += int(record.legacy_invalid_structured_output)
        for name, expected_polarity in record.expected.reflection_polarity.items():
            if (
                record.combined_analyzer.reflection_polarity.get(name)
                != expected_polarity
            ):
                polarity_regressions += 1

    exact_span_precision = (
        matched / predicted
        if predicted
        else 1.0 if expected_span_count == 0 else 0.0
    )
    top_theme_agreement = theme_matches / len(dataset.records)
    passed = (
        exact_span_precision >= 0.90
        and top_theme_agreement >= 0.95
        and combined_invalid <= legacy_invalid
        and polarity_regressions == 0
    )
    return EvaluationResult(
        record_count=len(dataset.records),
        exact_span_precision=exact_span_precision,
        top_theme_agreement=top_theme_agreement,
        combined_invalid_structured_outputs=combined_invalid,
        legacy_invalid_structured_outputs=legacy_invalid,
        reflection_polarity_regressions=polarity_regressions,
        passed=passed,
    )


ReviewEvaluationDimension = Literal[
    "garbage_leakage",
    "evidence_attribution",
    "abstention",
    "feedback_sensitivity",
]


class ReviewEvaluationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        strict=True,
    )


GarbageEligibility = Literal["accepted", "excluded", "uncertain"]
EvidenceAttributionScenario = Literal[
    "exact",
    "missing",
    "signal_owner_mismatch",
    "entry_owner_mismatch",
    "analysis_owner_mismatch",
    "entry_mismatch",
    "analysis_uncertain",
    "analysis_excluded",
    "outside_basis",
    "basis_unavailable",
    "offset_out_of_bounds",
    "offset_mismatch",
]


class GarbageLeakageEvaluationCase(ReviewEvaluationModel):
    dimension: Literal["garbage_leakage"]
    eligibility_result: GarbageEligibility
    proposed_review_item_count: int = Field(ge=0)
    expected_review_item_count: int = Field(ge=0)


class EvidenceAttributionEvaluationCase(ReviewEvaluationModel):
    dimension: Literal["evidence_attribution"]
    scenario: EvidenceAttributionScenario
    expected_reason_codes: list[EvidenceRejectionCode] = Field(max_length=2)

    @model_validator(mode="after")
    def unique_expected_reason_codes(self) -> Self:
        if len(self.expected_reason_codes) != len(
            set(self.expected_reason_codes)
        ):
            raise ValueError("expected evidence reason codes must be unique")
        return self


class AbstentionEvaluationCase(ReviewEvaluationModel):
    dimension: Literal["abstention"]
    pattern_type: PatternType
    selected_pattern_types: list[PatternType] = Field(max_length=3)
    expected_status: Literal["available", "insufficient_evidence"]

    @model_validator(mode="after")
    def unique_selected_pattern_types(self) -> Self:
        if len(self.selected_pattern_types) != len(
            set(self.selected_pattern_types)
        ):
            raise ValueError("selected pattern types must be unique")
        return self


class FeedbackSensitivityEvaluationCase(ReviewEvaluationModel):
    dimension: Literal["feedback_sensitivity"]
    evidence_weight: float = Field(ge=0, le=1, allow_inf_nan=False)
    model_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    expected_effective_confidence: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def closed_weight_bucket(self) -> "FeedbackSensitivityEvaluationCase":
        if self.evidence_weight not in {0.0, 0.5, 1.0}:
            raise ValueError("evaluation evidence weight is invalid")
        return self


ReviewReflectionEvaluationCase = Annotated[
    GarbageLeakageEvaluationCase
    | EvidenceAttributionEvaluationCase
    | AbstentionEvaluationCase
    | FeedbackSensitivityEvaluationCase,
    Field(discriminator="dimension"),
]


class ReviewReflectionEvaluationDataset(ReviewEvaluationModel):
    version: int = Field(ge=1, le=1, strict=True)
    cases: list[ReviewReflectionEvaluationCase] = Field(
        min_length=24,
        max_length=24,
    )

    @model_validator(mode="after")
    def complete_synthetic_matrix(self) -> "ReviewReflectionEvaluationDataset":
        dimensions = {item.dimension for item in self.cases}
        required: set[ReviewEvaluationDimension] = {
            "garbage_leakage",
            "evidence_attribution",
            "abstention",
            "feedback_sensitivity",
        }
        if dimensions != required:
            raise ValueError("evaluation must cover every Review dimension")
        garbage_eligibility = {
            item.eligibility_result
            for item in self.cases
            if isinstance(item, GarbageLeakageEvaluationCase)
        }
        if garbage_eligibility != {"accepted", "excluded", "uncertain"}:
            raise ValueError("evaluation must cover every eligibility result")
        evidence_scenarios = {
            item.scenario
            for item in self.cases
            if isinstance(item, EvidenceAttributionEvaluationCase)
        }
        required_evidence_scenarios: set[EvidenceAttributionScenario] = {
            "exact",
            "missing",
            "signal_owner_mismatch",
            "entry_owner_mismatch",
            "analysis_owner_mismatch",
            "entry_mismatch",
            "analysis_uncertain",
            "analysis_excluded",
            "outside_basis",
            "basis_unavailable",
            "offset_out_of_bounds",
            "offset_mismatch",
        }
        if evidence_scenarios != required_evidence_scenarios:
            raise ValueError(
                "evaluation must cover every evidence attribution boundary"
            )
        abstention_coverage = {
            (
                item.pattern_type,
                item.pattern_type in item.selected_pattern_types,
            )
            for item in self.cases
            if isinstance(item, AbstentionEvaluationCase)
        }
        required_abstention_coverage = {
            (pattern_type, selected)
            for pattern_type in (
                "hidden_driver",
                "recurring_loop",
                "inner_tension",
            )
            for selected in (False, True)
        }
        if abstention_coverage != required_abstention_coverage:
            raise ValueError("evaluation must cover every section outcome")
        feedback_weights = {
            item.evidence_weight
            for item in self.cases
            if isinstance(item, FeedbackSensitivityEvaluationCase)
        }
        if feedback_weights != {0.0, 0.5, 1.0}:
            raise ValueError("evaluation must cover every feedback weight")
        return self


class ReviewEvaluationDimensionResult(ReviewEvaluationModel):
    dimension: ReviewEvaluationDimension
    case_count: int = Field(ge=1)
    passed_count: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_pass_count(self) -> "ReviewEvaluationDimensionResult":
        if self.passed_count > self.case_count:
            raise ValueError("evaluation pass count is invalid")
        return self


class ReviewReflectionEvaluationResult(ReviewEvaluationModel):
    case_count: int = Field(ge=24)
    dimensions: list[ReviewEvaluationDimensionResult] = Field(
        min_length=4,
        max_length=4,
    )
    passed: bool

    @model_validator(mode="after")
    def complete_consistent_result(self) -> Self:
        if {item.dimension for item in self.dimensions} != {
            "garbage_leakage",
            "evidence_attribution",
            "abstention",
            "feedback_sensitivity",
        }:
            raise ValueError("evaluation result dimensions are invalid")
        if sum(item.case_count for item in self.dimensions) != self.case_count:
            raise ValueError("evaluation result case count is invalid")
        expected_passed = all(
            item.passed_count == item.case_count for item in self.dimensions
        )
        if self.passed is not expected_passed:
            raise ValueError("evaluation result pass state is invalid")
        return self


_SYNTHETIC_USER_ID = UUID("11111111-1111-4111-8111-111111111111")
_SYNTHETIC_OTHER_USER_ID = UUID(
    "22222222-2222-4222-8222-222222222222"
)
_SYNTHETIC_ENTRY_ID = UUID("33333333-3333-4333-8333-333333333333")
_SYNTHETIC_OTHER_ENTRY_ID = UUID(
    "44444444-4444-4444-8444-444444444444"
)
_SYNTHETIC_ENTRY_TEXT = "synthetic evidence"
_SYNTHETIC_BASIS_START = date(2026, 1, 1)
_SYNTHETIC_BASIS_END = date(2026, 1, 31)


def _synthetic_evidence_reasons(
    scenario: EvidenceAttributionScenario,
) -> tuple[EvidenceRejectionCode, ...]:
    if scenario == "missing":
        return evidence_presence_rejection_codes(signal_present=False)
    entry_date = (
        date(2025, 12, 31)
        if scenario == "outside_basis"
        else date(2026, 1, 15)
    )
    source_start = 10
    source_end = (
        len(_SYNTHETIC_ENTRY_TEXT) + 1
        if scenario == "offset_out_of_bounds"
        else 18
    )
    source_quote = "synthetic" if scenario == "offset_mismatch" else "evidence"
    analysis_eligibility: Eligibility = "accepted"
    if scenario == "analysis_uncertain":
        analysis_eligibility = "uncertain"
    elif scenario == "analysis_excluded":
        analysis_eligibility = "excluded"
    return evidence_signal_rejection_codes(
        expected_user_id=_SYNTHETIC_USER_ID,
        signal_user_id=(
            _SYNTHETIC_OTHER_USER_ID
            if scenario == "signal_owner_mismatch"
            else _SYNTHETIC_USER_ID
        ),
        entry_user_id=(
            _SYNTHETIC_OTHER_USER_ID
            if scenario == "entry_owner_mismatch"
            else _SYNTHETIC_USER_ID
        ),
        analysis_user_id=(
            _SYNTHETIC_OTHER_USER_ID
            if scenario == "analysis_owner_mismatch"
            else _SYNTHETIC_USER_ID
        ),
        entry_id=_SYNTHETIC_ENTRY_ID,
        analysis_entry_id=(
            _SYNTHETIC_OTHER_ENTRY_ID
            if scenario == "entry_mismatch"
            else _SYNTHETIC_ENTRY_ID
        ),
        analysis_eligibility=analysis_eligibility,
        entry_date=entry_date,
        basis_start=(
            None
            if scenario == "basis_unavailable"
            else _SYNTHETIC_BASIS_START
        ),
        basis_end=(
            None
            if scenario == "basis_unavailable"
            else _SYNTHETIC_BASIS_END
        ),
        entry_text=_SYNTHETIC_ENTRY_TEXT,
        source_quote=source_quote,
        source_start=source_start,
        source_end=source_end,
    )


def evaluate_review_reflection_dataset(
    dataset: ReviewReflectionEvaluationDataset,
) -> ReviewReflectionEvaluationResult:
    outcomes: dict[ReviewEvaluationDimension, list[bool]] = {
        "garbage_leakage": [],
        "evidence_attribution": [],
        "abstention": [],
        "feedback_sensitivity": [],
    }
    for item in dataset.cases:
        if isinstance(item, GarbageLeakageEvaluationCase):
            actual_review_item_count = expected_review_item_count(
                analysis_accepted=item.eligibility_result == "accepted",
                proposed_review_item_count=item.proposed_review_item_count,
            )
            passed = (
                actual_review_item_count
                == item.expected_review_item_count
            )
        elif isinstance(item, EvidenceAttributionEvaluationCase):
            passed = (
                _synthetic_evidence_reasons(item.scenario)
                == tuple(item.expected_reason_codes)
            )
        elif isinstance(item, AbstentionEvaluationCase):
            actual_status = synthesis_section_status(
                pattern_type=item.pattern_type,
                selected_pattern_types=item.selected_pattern_types,
            )
            passed = actual_status == item.expected_status
        else:
            actual_confidence = review_weighted_confidence(
                model_confidence=item.model_confidence,
                evidence_weight=item.evidence_weight,
            )
            passed = isclose(
                actual_confidence,
                item.expected_effective_confidence,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        outcomes[item.dimension].append(passed)

    dimensions = [
        ReviewEvaluationDimensionResult(
            dimension=dimension,
            case_count=len(results),
            passed_count=sum(results),
        )
        for dimension, results in outcomes.items()
    ]
    return ReviewReflectionEvaluationResult(
        case_count=len(dataset.cases),
        dimensions=dimensions,
        passed=all(
            item.passed_count == item.case_count for item in dimensions
        ),
    )
