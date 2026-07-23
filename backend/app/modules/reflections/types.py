from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.modules.reflections.schemas import FeedbackResponse, ReflectionRange


@dataclass(frozen=True, slots=True)
class ReflectionQuery:
    user_id: UUID
    range: ReflectionRange


@dataclass(frozen=True, slots=True)
class FeedbackCommand:
    user_id: UUID
    snapshot_id: UUID
    insight_id: UUID
    response: FeedbackResponse


@dataclass(frozen=True, slots=True)
class SavedFeedback:
    snapshot_id: UUID
    insight_id: UUID
    response: FeedbackResponse
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RecalculationRequest:
    outcome: Literal["accepted", "already_current", "not_eligible", "unavailable"]
    job_id: UUID | None
    source_version: int
    valid_entry_count: int
    distinct_entry_dates: int
    reflective_word_count: int
