from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.processing.schemas import Eligibility, LoopRole, NeedTag, SignalType, ThemeKey


PatternType = Literal["hidden_driver", "recurring_loop", "inner_tension"]
CandidateStatus = Literal["candidate", "published", "weakened", "superseded", "rejected"]
EvidenceRole = Literal["supporting", "counter"]
ConfidenceLabel = Literal["preliminary", "emerging", "recurring"]


class StrictReflectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


UnitFloat = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class AnalysisBasis(StrictReflectionModel):
    source_version: int = Field(ge=0)
    basis_start: date | None
    basis_end: date | None
    valid_entry_count: int = Field(ge=0)
    distinct_entry_dates: int = Field(ge=0)
    reflective_word_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if (self.basis_start is None) != (self.basis_end is None):
            raise ValueError("basis dates must both be present or absent")
        if self.basis_start is not None and self.basis_start > self.basis_end:
            raise ValueError("basis window is invalid")
        return self


class CandidateSignal(StrictReflectionModel):
    id: UUID
    user_id: UUID
    entry_id: UUID
    entry_user_id: UUID
    analysis_id: UUID
    analysis_user_id: UUID
    analysis_entry_id: UUID
    analysis_source_version: int = Field(gt=0)
    analysis_eligibility: Eligibility
    entry_date: date
    signal_type: SignalType
    normalized_label_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_label: str = Field(min_length=1, max_length=200)
    interpretation: str = Field(min_length=1, max_length=1000)
    source_quote: str = Field(min_length=1, max_length=4000, repr=False)
    entry_text: str = Field(min_length=1, max_length=200_000, repr=False)
    themes: list[ThemeKey] = Field(max_length=3)
    need_tags: list[NeedTag] = Field(max_length=4)
    loop_role: LoopRole | None
    confidence: UnitFloat
    source_start: int = Field(ge=0)
    source_end: int = Field(gt=0)
    occurred_on: date
    duplicate_cluster_key: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if self.source_end <= self.source_start:
            raise ValueError("signal offsets are invalid")
        if len(self.themes) != len(set(self.themes)):
            raise ValueError("signal themes must be distinct")
        if len(self.need_tags) != len(set(self.need_tags)):
            raise ValueError("signal need tags must be distinct")
        return self

    @property
    def cluster_key(self) -> str:
        return self.duplicate_cluster_key or str(self.id)


class PreviousCandidate(StrictReflectionModel):
    id: UUID
    pattern_type: PatternType
    canonical_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: CandidateStatus
    score: UnitFloat
    version: int = Field(ge=1)
    first_seen_at: datetime
    last_seen_at: datetime
    last_source_version: int = Field(ge=0)
    rejected_at: datetime | None
    rejected_source_version: int | None = Field(default=None, ge=0)
    payload: dict[str, object]


class HiddenDriverScoreComponents(StrictReflectionModel):
    recurrence: UnitFloat
    temporal_spread: UnitFloat
    context_diversity: UnitFloat
    evidence_strength: UnitFloat
    signal_type_diversity: UnitFloat
    stability: UnitFloat
    contradiction: UnitFloat
    duplication: UnitFloat
    deterministic_score_before_stability: UnitFloat


class LoopScoreComponents(StrictReflectionModel):
    recurrence: UnitFloat
    transition_coverage: UnitFloat
    temporal_spread: UnitFloat
    context_diversity: UnitFloat
    evidence_strength: UnitFloat
    stability: UnitFloat
    contradiction: UnitFloat
    duplication: UnitFloat
    deterministic_score_before_stability: UnitFloat


class TensionScoreComponents(StrictReflectionModel):
    left_support: UnitFloat
    right_support: UnitFloat
    direct_conflict: UnitFloat
    temporal_alternation: UnitFloat
    context_diversity: UnitFloat
    evidence_strength: UnitFloat
    stability: UnitFloat
    contradiction: UnitFloat
    duplication: UnitFloat
    deterministic_score_before_stability: UnitFloat


ScoreComponents = HiddenDriverScoreComponents | LoopScoreComponents | TensionScoreComponents


class HiddenDriverStructure(StrictReflectionModel):
    canonical_need: NeedTag
    statement: str = Field(min_length=1, max_length=1000)
    underlying_need: str = Field(min_length=1, max_length=200)
    supporting_entries: int = Field(ge=0)
    distinct_dates: int = Field(ge=0)
    distinct_signal_types: int = Field(ge=0)


class LoopStepStructure(StrictReflectionModel):
    loop_role: LoopRole
    normalized_label_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    support_signal_ids: list[UUID] = Field(min_length=1)


class RecurringLoopStructure(StrictReflectionModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=1000)
    steps: list[LoopStepStructure] = Field(min_length=3, max_length=6)
    transition_keys: list[str] = Field(min_length=3, max_length=36)
    observed_chains: int = Field(ge=0)
    supporting_entries: int = Field(ge=0)
    supported_transitions: int = Field(ge=0)
    distinct_dates: int = Field(ge=0)


class InnerTensionStructure(StrictReflectionModel):
    left_need: NeedTag
    right_need: NeedTag
    left_statement: str = Field(min_length=1, max_length=1000)
    right_statement: str = Field(min_length=1, max_length=1000)
    integration: str = Field(min_length=1, max_length=1000)
    left_support_signal_ids: list[UUID] = Field(min_length=1)
    right_support_signal_ids: list[UUID] = Field(min_length=1)
    left_supporting_entries: int = Field(ge=0)
    right_supporting_entries: int = Field(ge=0)
    distinct_dates: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_pair(self) -> Self:
        if self.left_need >= self.right_need:
            raise ValueError("tension needs must be canonically ordered")
        return self


CandidateStructure = HiddenDriverStructure | RecurringLoopStructure | InnerTensionStructure


class CandidateEvidenceLink(StrictReflectionModel):
    candidate_id: UUID
    signal_id: UUID
    evidence_role: EvidenceRole
    evidence_weight: UnitFloat


class ConstructedCandidate(StrictReflectionModel):
    id: UUID
    pattern_type: PatternType
    canonical_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: CandidateStatus
    score: UnitFloat
    score_components: ScoreComponents
    structure: CandidateStructure
    support_signal_ids: list[UUID] = Field(min_length=1)
    counter_signal_ids: list[UUID]
    support_clusters: list[str] = Field(min_length=1)
    publication_gate_passed: bool
    confidence_label: ConfidenceLabel
    first_seen_at: datetime
    last_seen_at: datetime
    version: int = Field(ge=1)
    rejected_at: datetime | None
    rejected_source_version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_candidate_shape(self) -> Self:
        expected_structure = {
            "hidden_driver": HiddenDriverStructure,
            "recurring_loop": RecurringLoopStructure,
            "inner_tension": InnerTensionStructure,
        }[self.pattern_type]
        expected_components = {
            "hidden_driver": HiddenDriverScoreComponents,
            "recurring_loop": LoopScoreComponents,
            "inner_tension": TensionScoreComponents,
        }[self.pattern_type]
        if not isinstance(self.structure, expected_structure):
            raise ValueError("candidate structure does not match pattern type")
        if not isinstance(self.score_components, expected_components):
            raise ValueError("score components do not match pattern type")
        if len(self.support_signal_ids) != len(set(self.support_signal_ids)):
            raise ValueError("support signals must be distinct")
        if len(self.counter_signal_ids) != len(set(self.counter_signal_ids)):
            raise ValueError("counter signals must be distinct")
        if set(self.support_signal_ids) & set(self.counter_signal_ids):
            raise ValueError("support and counter signals must be disjoint")
        if len(self.support_clusters) != len(set(self.support_clusters)):
            raise ValueError("support clusters must be distinct")
        return self


class CandidateBatch(StrictReflectionModel):
    basis: AnalysisBasis
    basis_eligible: bool
    candidates: list[ConstructedCandidate]
    evidence: list[CandidateEvidenceLink]
    discarded_reason_codes: list[str]

    @model_validator(mode="after")
    def validate_links(self) -> Self:
        candidate_ids = {candidate.id for candidate in self.candidates}
        if any(link.candidate_id not in candidate_ids for link in self.evidence):
            raise ValueError("evidence references an unknown candidate")
        identities = {
            (link.candidate_id, link.signal_id, link.evidence_role)
            for link in self.evidence
        }
        if len(identities) != len(self.evidence):
            raise ValueError("candidate evidence links must be distinct")
        return self
