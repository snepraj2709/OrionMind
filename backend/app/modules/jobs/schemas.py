from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


JobType: TypeAlias = Literal["entry_processing", "reflection_synthesis"]
JobStatus: TypeAlias = Literal["pending", "running", "completed", "failed"]
JobExecutionMode: TypeAlias = Literal["user", "backfill", "shadow", "publish"]


class ProcessingJob(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: UUID
    user_id: UUID
    entry_id: UUID | None
    job_type: JobType
    execution_mode: JobExecutionMode
    priority: int = Field(ge=0, le=100)
    source_version: str = Field(min_length=1, max_length=200)
    status: JobStatus
    run_after: datetime
    attempts: int = Field(ge=0, le=3)
    worker_id: str | None = Field(default=None, min_length=1, max_length=100)
    claim_token: UUID | None = None
    heartbeat_at: datetime | None = None
    last_error_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "ProcessingJob":
        if (self.job_type == "entry_processing") != (self.entry_id is not None):
            raise ValueError("job type and entry must agree")
        expected_priority = {
            "user": 100,
            "publish": 80,
            "shadow": 60,
            "backfill": 10,
        }[self.execution_mode]
        if self.priority != expected_priority:
            raise ValueError("job priority does not match its execution mode")
        if self.job_type == "entry_processing" and self.execution_mode not in {
            "user",
            "backfill",
        }:
            raise ValueError("entry job execution mode is invalid")
        if self.job_type == "reflection_synthesis" and self.execution_mode not in {
            "shadow",
            "publish",
        }:
            raise ValueError("synthesis job execution mode is invalid")
        if self.job_type == "entry_processing" and self.source_version != str(self.entry_id):
            raise ValueError("entry source version must equal the entry id")
        if self.job_type == "reflection_synthesis" and (
            not self.source_version.isdigit()
            or self.source_version.startswith("0")
        ):
            raise ValueError("synthesis source version must be numeric")
        if self.status == "pending" and any(
            value is not None
            for value in (self.worker_id, self.claim_token, self.heartbeat_at, self.completed_at)
        ):
            raise ValueError("pending job contains claim state")
        if self.status == "running" and any(
            value is None for value in (self.worker_id, self.claim_token, self.heartbeat_at)
        ):
            raise ValueError("running job is missing claim state")
        if self.status in {"completed", "failed"} and (
            self.worker_id is not None
            or self.claim_token is None
            or self.heartbeat_at is not None
            or self.completed_at is None
        ):
            raise ValueError("terminal job has invalid claim state")
        return self
