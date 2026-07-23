from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.modules.processing.schemas import EntryKind, NeedTag, ThemeKey


ReflectionRange = Literal["7d", "30d", "all"]
ReflectionState = Literal[
    "available",
    "first_reflection_pending",
    "stale",
    "insufficient_reflective_content",
    "technical_failure",
]
ProcessingState = Literal["idle", "pending", "failed"]
FeedbackResponse = Literal["resonates", "partly", "rejected"]
Confidence = Literal["preliminary", "emerging", "recurring"]
ReasonCode = Literal[
    "NOT_ENOUGH_REFLECTIVE_CONTENT",
    "MINIMUM_BASIS_NOT_MET",
    "DRIVER_NOT_REPEATED",
    "LOOP_NOT_REPEATED",
    "BOTH_SIDES_NOT_SUPPORTED",
    "INSUFFICIENT_EVIDENCE",
]
ReflectionSectionStatus = Literal[
    "available",
    "processing",
    "insufficient_evidence",
    "unavailable",
]
UnavailableReasonCode = Literal["TECHNICAL_FAILURE"]
UnitScore = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
PositiveCount = Annotated[int, Field(ge=1)]


class StrictPublicModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class FeedbackRequest(StrictPublicModel):
    response: FeedbackResponse


class FeedbackResult(StrictPublicModel):
    snapshot_id: UUID
    insight_id: UUID
    response: FeedbackResponse
    updated_at: datetime


class SnapshotMetadata(StrictPublicModel):
    id: UUID
    version: int = Field(ge=1)
    generated_at: datetime
    source_version: int = Field(ge=1)
    is_stale: bool


class AnalysisBasis(StrictPublicModel):
    window: Literal["90d"] = "90d"
    valid_entry_count: int = Field(ge=0)
    excluded_entry_count: int = Field(ge=0)
    distinct_entry_dates: int = Field(ge=0)
    reflective_word_count: int = Field(ge=0)
    current_range_from: date | None = None
    current_range_to: date | None = None
    excluded_reasons: dict[EntryKind, PositiveCount] | None = None


class EvidenceItem(StrictPublicModel):
    id: UUID
    entry_date: date
    source_label: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=1, max_length=4000)
    interpretation: str = Field(min_length=1, max_length=1000)
    theme: ThemeKey | None = None
    supports: str = Field(min_length=1, max_length=200)


class InsufficientInsight(StrictPublicModel):
    status: Literal["insufficient_evidence"] = "insufficient_evidence"
    reason_code: ReasonCode
    message: str = Field(min_length=1, max_length=500)


class ProcessingInsight(StrictPublicModel):
    status: Literal["processing"] = "processing"
    message: str = Field(min_length=1, max_length=500)


class UnavailableInsight(StrictPublicModel):
    status: Literal["unavailable"] = "unavailable"
    reason_code: UnavailableReasonCode
    message: str = Field(min_length=1, max_length=500)
    retryable: bool


class AvailableInsight(StrictPublicModel):
    status: Literal["available"] = "available"
    id: UUID
    confidence: Confidence
    score: UnitScore
    evidence_entry_count: PositiveCount
    evidence: list[EvidenceItem]
    feedback: FeedbackResponse | None


class AvailableHiddenDriver(AvailableInsight):
    statement: str = Field(min_length=1, max_length=1000)
    underlying_need: str = Field(min_length=1, max_length=200)
    drivers: list[str] = Field(max_length=5)


class LoopStep(StrictPublicModel):
    id: UUID
    text: str = Field(min_length=1, max_length=1000)
    evidence: list[EvidenceItem]


class AvailableRecurringLoop(AvailableInsight):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=1000)
    steps: list[LoopStep] = Field(min_length=3, max_length=6)
    protection: str = Field(min_length=1, max_length=1000)
    interruption: str = Field(min_length=1, max_length=1000)


class InnerTension(StrictPublicModel):
    id: UUID
    confidence: Confidence
    score: UnitScore
    evidence_entry_count: PositiveCount
    left_title: NeedTag
    left_body: str = Field(min_length=1, max_length=1000)
    right_title: NeedTag
    right_body: str = Field(min_length=1, max_length=1000)
    integration: str = Field(min_length=1, max_length=1000)
    dates: list[date]
    evidence: list[EvidenceItem]
    feedback: FeedbackResponse | None


class AvailableInnerTensions(StrictPublicModel):
    status: Literal["available"] = "available"
    tensions: list[InnerTension] = Field(min_length=1, max_length=5)


HiddenDriverSection = Annotated[
    AvailableHiddenDriver | InsufficientInsight, Field(discriminator="status")
]
RecurringLoopSection = Annotated[
    AvailableRecurringLoop | InsufficientInsight, Field(discriminator="status")
]
InnerTensionsSection = Annotated[
    AvailableInnerTensions | InsufficientInsight, Field(discriminator="status")
]


class ReflectionData(StrictPublicModel):
    hidden_driver: HiddenDriverSection
    recurring_loop: RecurringLoopSection
    inner_tensions: InnerTensionsSection


class ReflectionResponse(StrictPublicModel):
    range: ReflectionRange
    reflection_state: ReflectionState
    processing_state: ProcessingState
    snapshot: SnapshotMetadata | None
    analysis_basis: AnalysisBasis
    data: ReflectionData
