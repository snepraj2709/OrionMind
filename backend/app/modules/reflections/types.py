from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
class SynthesisRequest:
    job_id: UUID
    source_version: int
