from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

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


class SignalEmbeddingProvider(Protocol):
    def embed(
        self,
        *,
        texts: tuple[str, ...],
        safety_identifier: str,
    ) -> tuple[tuple[float, ...], ...]: ...


@dataclass(frozen=True, slots=True)
class PreparedEntryAnalysis:
    analysis: dict[str, object]
    signals: tuple[dict[str, object], ...]
    extraction: EntryExtraction
