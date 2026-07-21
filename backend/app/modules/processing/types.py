from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from datetime import date

from app.modules.processing.schemas import (
    DeterministicQualityFeatures,
    EntryExtraction,
    ModelEntryAnalysis,
)


@dataclass(frozen=True, slots=True)
class ThemeDefinition:
    key: str
    name: str


class EntryAnalysisProvider(Protocol):
    def analyze(
        self,
        *,
        redacted_text: str,
        themes: tuple[ThemeDefinition, ...],
        deterministic_features: DeterministicQualityFeatures,
        entry_date: date,
        safety_identifier: str,
    ) -> ModelEntryAnalysis: ...


@dataclass(frozen=True, slots=True)
class ProcessingRequest:
    user_id: UUID
    entry_id: UUID
    processing_token: UUID
    theme_config_id: UUID
    content: str
    past_import: bool = False


@dataclass(frozen=True, slots=True)
class PreparedEntryAnalysis:
    analysis: dict[str, object]
    signals: tuple[dict[str, object], ...]
    extraction: EntryExtraction
