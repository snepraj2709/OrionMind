from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DraftData:
    id: UUID
    envelope: dict
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ThemeData:
    key: str
    name: str
    color_hex: str
    tier: str
    score: float | None = None


@dataclass(frozen=True, slots=True)
class ClassificationData:
    theme_config_id: UUID
    source: str
    mode: str | None
    themes: tuple[ThemeData, ...]


@dataclass(frozen=True, slots=True)
class CandidateData:
    id: UUID
    content: str
    status: str
    entry_id: UUID
    entry_date: date
    created_at: datetime
    decided_at: datetime | None


@dataclass(frozen=True, slots=True)
class ReflectionData:
    id: UUID
    reflection_type: str
    activity: str
    confidence_score: float
    status: str
    entry_id: UUID
    entry_date: date
    created_at: datetime
    decided_at: datetime | None


@dataclass(frozen=True, slots=True)
class EntryData:
    id: UUID
    envelope: dict
    input_type: str
    entry_date: date
    original_theme_config_id: UUID
    processing_status: str
    processing_error_code: str | None
    created_at: datetime
    classification: ClassificationData | None = None
    ideas: tuple[CandidateData, ...] = field(default_factory=tuple)
    memories: tuple[CandidateData, ...] = field(default_factory=tuple)
    reflections: tuple[ReflectionData, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class EntrySummaryData:
    entry: EntryData
    plaintext: str
    themes: tuple[ThemeData, ...]


@dataclass(frozen=True, slots=True)
class EntryPageData:
    items: tuple[EntrySummaryData, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class SubmissionClaim:
    entry_id: UUID
    processing_token: UUID | None
    created: bool
    reclaimed: bool


@dataclass(frozen=True, slots=True)
class EntryOperation:
    entry: EntryData
    plaintext: str
    status_code: int
