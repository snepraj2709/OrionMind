from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from app.modules.reflections.aggregate import _nonnegative_int, _positive_int


ReflectionState = Literal[
    "available",
    "first_reflection_pending",
    "stale",
    "insufficient_reflective_content",
]
ProcessingState = Literal["idle", "pending", "failed"]


@dataclass(frozen=True, slots=True)
class PersistedReflectionState:
    latest_accepted: int
    failed: bool
    pending: bool

    @classmethod
    def parse(
        cls,
        *,
        state: Mapping[str, object],
        job: Mapping[str, object],
    ) -> PersistedReflectionState:
        latest_accepted = _nonnegative_int(
            state.get("latest_accepted_source_version", 0),
            "latest accepted source version",
        )
        last_error = state.get("last_processing_error_code")
        if last_error is not None and not isinstance(last_error, str):
            raise ValueError("reflection processing error state is invalid")
        job_status = job.get("status")
        if job_status not in {None, "pending", "running", "completed", "failed"}:
            raise ValueError("reflection job status is invalid")
        return cls(
            latest_accepted=latest_accepted,
            failed=job_status == "failed" or last_error is not None,
            pending=job_status in {"pending", "running"},
        )

    def without_snapshot(self) -> tuple[ReflectionState, ProcessingState]:
        reflection_state: ReflectionState = (
            "first_reflection_pending"
            if self.pending or self.latest_accepted > 0
            else "insufficient_reflective_content"
        )
        processing_state: ProcessingState = (
            "pending" if reflection_state == "first_reflection_pending" else "idle"
        )
        return reflection_state, processing_state

    def with_snapshot(
        self,
        snapshot: Mapping[str, object],
    ) -> tuple[int, ReflectionState, ProcessingState, bool]:
        snapshot_source = _positive_int(
            snapshot.get("source_version"),
            "snapshot source version",
        )
        stored_status = snapshot.get("status")
        if stored_status not in {"available", "stale"}:
            raise ValueError("snapshot status is invalid")
        newer_entries = self.latest_accepted > snapshot_source
        stale = (
            self.failed
            or self.pending
            or newer_entries
            or stored_status == "stale"
        )
        reflection_state: ReflectionState = "stale" if stale else "available"
        processing_state: ProcessingState = (
            "failed" if self.failed else "pending" if stale else "idle"
        )
        return snapshot_source, reflection_state, processing_state, stale
