from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.processing.schemas import ThemeKey


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
