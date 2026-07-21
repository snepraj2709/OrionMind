from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntryDraftUpdate(StrictDTO):
    content: str = Field(max_length=200_000)


class EntryDraftResponse(StrictDTO):
    content: str | None
    updated_at: datetime | None


class TextEntryCreate(StrictDTO):
    content: str = Field(min_length=1, max_length=200_000)


class EntrySummaryTheme(StrictDTO):
    key: str
    name: str
    color_hex: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    tier: Literal["primary", "secondary", "tertiary"]


class EntrySummary(StrictDTO):
    id: UUID
    input_type: Literal["text", "audio"]
    entry_date: date
    processing_status: Literal["pending", "processing", "completed", "failed"]
    created_at: datetime
    content_preview: str = Field(max_length=200)
    themes: list[EntrySummaryTheme] = Field(max_length=3)


class EntryPage(StrictDTO):
    items: list[EntrySummary]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class ThemeScore(StrictDTO):
    key: str
    name: str
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    tier: Literal["primary", "secondary", "tertiary"]


class Classification(StrictDTO):
    theme_config_id: UUID
    source: Literal["initial", "backfill"]
    mode: Literal["dominant", "balanced"] | None
    themes: list[ThemeScore] = Field(max_length=3)

    @model_validator(mode="after")
    def validate_mode(self) -> Self:
        if not self.themes and self.mode is not None:
            raise ValueError("empty classification requires null mode")
        if len(self.themes) == 1 and self.mode != "dominant":
            raise ValueError("one theme requires dominant mode")
        return self


class Candidate(StrictDTO):
    id: UUID
    content: str = Field(max_length=4000)
    status: Literal["pending_approval", "approved", "rejected"]
    entry_id: UUID
    entry_date: date
    created_at: datetime
    decided_at: datetime | None


class Reflection(StrictDTO):
    id: UUID
    reflection_type: Literal["filled_energy", "drained_energy", "learned_about_self"]
    activity: str = Field(max_length=1000)
    confidence_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    status: Literal["pending_approval", "approved", "rejected"]
    entry_id: UUID
    entry_date: date
    created_at: datetime
    decided_at: datetime | None


class EntryDetail(StrictDTO):
    id: UUID
    content: str
    input_type: Literal["text", "audio"]
    entry_date: date
    original_theme_config_id: UUID
    processing_status: Literal["pending", "processing", "completed", "failed"]
    processing_error_code: str | None
    created_at: datetime
    classification: Classification | None
    ideas: list[Candidate]
    extracted_memories: list[Candidate]
    reflections: list[Reflection]

    @model_validator(mode="after")
    def completed_requires_classification(self) -> Self:
        if self.processing_status == "completed" and self.classification is None:
            raise ValueError("completed entry requires classification")
        return self
