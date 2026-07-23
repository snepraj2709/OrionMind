from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


ThemeTier = Literal["primary", "secondary", "tertiary"]
ThemeMode = Literal["dominant", "balanced"]
ThemeKey = Literal[
    "career",
    "money",
    "health",
    "love_life",
    "family_friends",
    "personal_growth",
    "fun_recreation",
    "home_lifestyle",
]
SignalType = Literal[
    "event",
    "emotion",
    "energy_gain",
    "energy_loss",
    "self_knowledge",
    "desire",
    "explicit_preference",
    "need",
    "avoidance",
    "belief",
    "self_statement",
    "action",
    "outcome",
    "conflict",
    "protective_strategy",
    "realization",
    "causal_relationship",
]
NeedTag = Literal[
    "autonomy",
    "competence",
    "mastery",
    "belonging",
    "recognition",
    "security",
    "stability",
    "novelty",
    "exploration",
    "meaning",
    "contribution",
    "creative_expression",
    "rest",
    "physical_vitality",
    "clarity",
    "control",
]
LoopRole = Literal[
    "trigger",
    "initial_reward",
    "interpretation",
    "emotional_response",
    "action",
    "avoidance",
    "short_term_protection",
    "long_term_cost",
    "recovery",
    "reinforcement",
]
EntryKind = Literal[
    "personal_reflection",
    "personal_event",
    "personal_observation",
    "task_or_note",
    "informational_text",
    "creative_writing",
    "test_or_noise",
    "copied_or_quoted_text",
    "unclear",
]
Eligibility = Literal["accepted", "uncertain", "excluded"]
DeterministicExclusionCode = Literal[
    "EMPTY_CONTENT",
    "TEST_OR_NOISE",
    "EXACT_DUPLICATE",
    "NEAR_DUPLICATE",
    "REPEATED_NGRAMS",
    "NO_MEANINGFUL_CONTENT",
]
QualityReasonCode = Literal[
    "EMPTY_CONTENT",
    "TEST_OR_NOISE",
    "EXACT_DUPLICATE",
    "NEAR_DUPLICATE",
    "REPEATED_NGRAMS",
    "NO_MEANINGFUL_CONTENT",
    "INFORMATIONAL_TEXT",
    "COPIED_OR_QUOTED_TEXT",
    "TASK_OR_NOTE",
    "CREATIVE_WRITING",
    "UNCLEAR",
    "LOW_REFLECTIVE_SCORE",
    "LOW_CONFIDENCE",
]
TIER_ORDER: tuple[ThemeTier, ...] = ("primary", "secondary", "tertiary")


class StrictExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SegmentReference(StrictExtractionModel):
    source_segment_id: str = Field(pattern=r"^segment_[0-9]{4,}$", max_length=64)


class ModelThemeAssignment(StrictExtractionModel):
    key: ThemeKey
    tier: ThemeTier
    evidence_segment_id: str = Field(pattern=r"^segment_[0-9]{4,}$", max_length=64)


class ModelThemeClassification(StrictExtractionModel):
    mode: ThemeMode | None
    themes: list[ModelThemeAssignment] = Field(max_length=3)

    @model_validator(mode="after")
    def normalize_shape(self) -> Self:
        unique: list[ModelThemeAssignment] = []
        keys: set[str] = set()
        evidence_segments: set[str] = set()
        for item in self.themes:
            if item.key in keys or item.evidence_segment_id in evidence_segments:
                continue
            keys.add(item.key)
            evidence_segments.add(item.evidence_segment_id)
            unique.append(item)
        self.themes = [
            item.model_copy(update={"tier": TIER_ORDER[index]})
            for index, item in enumerate(unique)
        ]
        count = len(self.themes)
        if count == 0:
            self.mode = None
        elif count == 1 or self.mode is None:
            # List order already expresses the model's primary choice. A
            # dominant mode is therefore the structural interpretation that
            # preserves that choice without inventing a new theme or evidence.
            self.mode = "dominant"
        return self


class ReflectionItem(StrictExtractionModel):
    activity: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


class ReflectionExtraction(StrictExtractionModel):
    filled_energy: ReflectionItem | None
    drained_energy: ReflectionItem | None
    learned_about_self: ReflectionItem | None


class ModelEntryExtraction(StrictExtractionModel):
    ideas: list[SegmentReference] = Field(max_length=10)
    memories: list[SegmentReference] = Field(max_length=10)
    theme: ModelThemeClassification
    reflection: ReflectionExtraction

    @model_validator(mode="after")
    def distinct_candidate_segments(self) -> Self:
        references = [item.source_segment_id for item in (*self.ideas, *self.memories)]
        if len(references) != len(set(references)):
            raise ValueError("a segment may produce at most one candidate")
        return self


class DeterministicQualityFeatures(StrictExtractionModel):
    word_count: int = Field(ge=0)
    meaningful_token_count: int = Field(ge=0)
    unique_token_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    repeated_ngram_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    alphabetic_character_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    exact_duplicate: bool
    near_duplicate_similarity: float | None = Field(default=None, ge=0, le=1)
    repeated_recent_entry_count: int = Field(ge=0)
    copied_text_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    hard_exclusion_codes: list[DeterministicExclusionCode] = Field(max_length=10)

    @model_validator(mode="after")
    def unique_exclusion_codes(self) -> Self:
        if len(self.hard_exclusion_codes) != len(set(self.hard_exclusion_codes)):
            raise ValueError("hard exclusion codes must be distinct")
        return self


class EntryQualityResult(StrictExtractionModel):
    entry_kind: EntryKind
    lived_experience_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    self_reference_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    emotional_information_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    causal_reasoning_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    personal_relevance_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    eligibility: Eligibility
    exclusion_reason_codes: list[QualityReasonCode] = Field(max_length=10)

    @model_validator(mode="after")
    def unique_reason_codes(self) -> Self:
        if len(self.exclusion_reason_codes) != len(set(self.exclusion_reason_codes)):
            raise ValueError("quality reason codes must be distinct")
        return self


class ModelAtomicSignal(StrictExtractionModel):
    signal_type: SignalType
    normalized_label: str = Field(min_length=1, max_length=200)
    interpretation: str = Field(min_length=1, max_length=1000)
    source_quote: str = Field(min_length=1, max_length=4000)
    source_start: int = Field(ge=0)
    source_end: int = Field(gt=0)
    themes: list[ThemeKey] = Field(max_length=3)
    need_tags: list[NeedTag] = Field(max_length=4)
    loop_role: LoopRole | None
    inference_level: Literal["direct", "inferred"]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_signal_shape(self) -> Self:
        if self.source_end <= self.source_start:
            raise ValueError("signal source offsets are invalid")
        if len(self.themes) != len(set(self.themes)):
            raise ValueError("signal themes must be distinct")
        if len(self.need_tags) != len(set(self.need_tags)):
            raise ValueError("signal need tags must be distinct")
        return self


class ModelEntryAnalysis(StrictExtractionModel):
    quality: EntryQualityResult
    signals: list[ModelAtomicSignal] = Field(max_length=30)
    legacy: ModelEntryExtraction

    @model_validator(mode="after")
    def validate_signal_collection(self) -> Self:
        if self.quality.eligibility != "accepted" and self.signals:
            raise ValueError("ineligible model analysis must not contain signals")
        identities: set[tuple[str, str, str]] = set()
        for signal in self.signals:
            identity = (
                signal.signal_type,
                signal.source_quote,
                signal.normalized_label.casefold(),
            )
            if identity in identities:
                raise ValueError("signals must be distinct")
            identities.add(identity)
        return self


class CandidateExtraction(StrictExtractionModel):
    content: str = Field(min_length=1, max_length=4000)


class ThemeAssignment(StrictExtractionModel):
    key: str = Field(min_length=1, max_length=64)
    tier: ThemeTier
    evidence: str = Field(min_length=1, max_length=4000)
    score: float = Field(gt=0, le=1, allow_inf_nan=False)


class ThemeClassification(StrictExtractionModel):
    mode: ThemeMode | None
    themes: list[ThemeAssignment] = Field(max_length=3)


class EntryExtraction(StrictExtractionModel):
    ideas: list[CandidateExtraction] = Field(max_length=10)
    memories: list[CandidateExtraction] = Field(max_length=10)
    theme: ThemeClassification
    reflection: ReflectionExtraction
