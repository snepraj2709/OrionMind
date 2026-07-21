from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.processing.schemas import ModelEntryExtraction


@dataclass(frozen=True, slots=True)
class ThemeDefinition:
    key: str
    name: str


class ExtractionProvider(Protocol):
    def extract(
        self,
        *,
        content: str,
        themes: tuple[ThemeDefinition, ...],
    ) -> ModelEntryExtraction: ...


@dataclass(frozen=True, slots=True)
class ProcessingRequest:
    user_id: UUID
    entry_id: UUID
    processing_token: UUID
    theme_config_id: UUID
    content: str
    past_import: bool = False
