from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


ThemeTier = Literal["primary", "secondary", "tertiary"]
ThemeMode = Literal["dominant", "balanced"]
TIER_ORDER: tuple[ThemeTier, ...] = ("primary", "secondary", "tertiary")


class StrictExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SegmentReference(StrictExtractionModel):
    source_segment_id: str = Field(pattern=r"^segment_[0-9]{4,}$", max_length=64)


class ModelThemeAssignment(StrictExtractionModel):
    key: str = Field(min_length=1, max_length=64)
    tier: ThemeTier
    evidence_segment_id: str = Field(pattern=r"^segment_[0-9]{4,}$", max_length=64)


class ModelThemeClassification(StrictExtractionModel):
    mode: ThemeMode | None
    themes: list[ModelThemeAssignment] = Field(max_length=3)

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        count = len(self.themes)
        if count == 0 and self.mode is not None:
            raise ValueError("empty classification requires null mode")
        if count == 1 and self.mode != "dominant":
            raise ValueError("one theme requires dominant mode")
        if count >= 2 and self.mode is None:
            raise ValueError("multiple themes require a mode")
        if [item.tier for item in self.themes] != list(TIER_ORDER[:count]):
            raise ValueError("theme tiers must be contiguous and ordered")
        if len({item.key for item in self.themes}) != count:
            raise ValueError("theme keys must be distinct")
        if len({item.evidence_segment_id for item in self.themes}) != count:
            raise ValueError("theme evidence segments must be distinct")
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
