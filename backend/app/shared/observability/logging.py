from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.shared.observability.reflection import (
    ENTRY_KINDS,
    JOB_ERROR_CODES,
    SIGNAL_TYPES,
    VALIDATOR_REASON_CODES,
)


_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,127}$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_HEX_HASH = re.compile(r"^[0-9a-f]{64}$")
_EVENTS = frozenset(
    {
        "entry_analysis_attempt",
        "entry_analysis_materialized",
        "entry_analysis_validation_failed",
        "processing_job_finished",
        "processing_recovery_complete",
        "processing_recovery_failed",
        "processing_attempt_failed",
        "processing_backfill_planned",
        "processing_backfill_status",
        "processing_queue_observed",
        "reflection_api_response",
        "reflection_candidate_observed",
        "reflection_feedback_saved",
        "reflection_model_access",
        "reflection_model_attempt",
        "reflection_proposal_discarded",
        "reflection_scheduler_complete",
        "reflection_scheduler_failed",
        "reflection_synthesis_requested",
        "request_complete",
        "unhandled_request_error",
    }
)
_ENUM_FIELDS: dict[str, frozenset[str]] = {
    "job_type": frozenset({"entry_processing", "reflection_synthesis"}),
    "status": frozenset(
        {
            "accepted",
            "completed",
            "excluded",
            "failed",
            "invalid",
            "pending",
            "planned",
            "paused",
            "running",
            "stale",
            "success",
            "uncertain",
        }
    ),
    "execution_mode": frozenset({"user", "shadow", "publish"}),
    "model_role": frozenset({"entry_analysis", "synthesis", "critic"}),
    "retry_class": frozenset({"none", "retryable", "terminal"}),
    "reflection_state": frozenset(
        {
            "available",
            "first_reflection_pending",
            "insufficient_reflective_content",
            "stale",
            "technical_failure",
            "unavailable",
        }
    ),
    "processing_state": frozenset({"failed", "idle", "pending", "unavailable"}),
    "response": frozenset({"resonates", "partly", "rejected"}),
    "pattern_type": frozenset({"hidden_driver", "recurring_loop", "inner_tension"}),
    "outcome": frozenset(
        {"constructed", "discarded", "publishable", "selected", "unavailable"}
    ),
    "access_status": frozenset({"available", "unavailable"}),
    "entry_kind": ENTRY_KINDS,
    "error_code": JOB_ERROR_CODES,
    "exclusion_reason_code": frozenset(
        {
            "NONE",
            "EMPTY_CONTENT",
            "TEST_OR_NOISE",
            "EXACT_DUPLICATE",
            "NEAR_DUPLICATE",
            "REPEATED_NGRAMS",
            "NO_MEANINGFUL_CONTENT",
            "INFORMATIONAL_TEXT",
            "COPIED_OR_QUOTED_TEXT",
            "TASK_OR_NOTE",
            "CREATIVE_WRITING",
            "UNCLEAR",
            "LOW_REFLECTIVE_SCORE",
            "LOW_CONFIDENCE",
        }
    ),
    "reason_code": VALIDATOR_REASON_CODES,
    "signal_type": SIGNAL_TYPES,
    "throttle_reason": frozenset(
        {"NONE", "QUEUE_DEPTH", "OLDEST_PENDING_AGE"}
    ),
    "validation_stage": frozenset(
        {"source_offsets", "quality", "legacy_extraction", "signals"}
    ),
}
_INTEGER_FIELDS = frozenset(
    {
        "attempt",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "candidate_count",
        "checked",
        "duration_ms",
        "eligible",
        "enqueued",
        "input_tokens",
        "oldest_pending_seconds",
        "output_tokens",
        "planned_count",
        "queue_depth",
        "recovered",
        "reasoning_output_tokens",
        "signal_count",
        "source_version",
        "stale_recoveries",
        "status_code",
        "terminal_failures",
    }
)
_UUID_FIELDS = frozenset(
    {"candidate_id", "entry_id", "job_id", "run_id", "snapshot_id"}
)
_TOKEN_FIELDS = frozenset(
    {
        "model_id",
        "prompt_version",
        "service_tier",
        "validation_code",
        "validation_path",
    }
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        event = getattr(record, "orion_event", None)
        fields = getattr(record, "orion_fields", None)
        if isinstance(event, str) and isinstance(fields, dict):
            payload["event"] = event
            payload.update(fields)
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"{record.levelname} {record.name} {record.getMessage()}"
        fields = getattr(record, "orion_fields", None)
        if not isinstance(fields, dict) or not fields:
            return base
        suffix = " ".join(f"{key}={value}" for key, value in sorted(fields.items()))
        return f"{base} {suffix}"


def safe_log(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit only contract-approved, non-content operational fields."""

    if event not in _EVENTS:
        raise ValueError("observability event is not allowlisted")
    normalized = {name: _safe_field(name, value) for name, value in fields.items()}
    logger.log(
        level,
        event,
        extra={"orion_event": event, "orion_fields": normalized},
    )


def _safe_field(name: str, value: Any) -> str | int | bool:
    allowed = _ENUM_FIELDS.get(name)
    if allowed is not None:
        if not isinstance(value, str) or value not in allowed:
            raise ValueError(f"observability field {name} is invalid")
        return value
    if name in _INTEGER_FIELDS:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"observability field {name} is invalid")
        if name == "status_code" and not 100 <= value <= 599:
            raise ValueError("observability status code is invalid")
        return value
    if name in _UUID_FIELDS:
        try:
            return str(value if isinstance(value, UUID) else UUID(str(value)))
        except ValueError as exc:
            raise ValueError(f"observability field {name} is invalid") from exc
    if name in _TOKEN_FIELDS:
        if not isinstance(value, str) or _TOKEN.fullmatch(value) is None:
            raise ValueError(f"observability field {name} is invalid")
        return value
    if name in {"worker_hash", "user_hash"}:
        if not isinstance(value, str) or _HEX_HASH.fullmatch(value) is None:
            raise ValueError(f"observability field {name} is invalid")
        return value
    if name == "request_id":
        if not isinstance(value, str) or _REQUEST_ID.fullmatch(value) is None:
            raise ValueError("observability request ID is invalid")
        return value
    if name == "method":
        if value not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}:
            raise ValueError("observability method is invalid")
        return str(value)
    if name == "route":
        if (
            not isinstance(value, str)
            or len(value) > 200
            or (value != "<unmatched>" and not value.startswith("/"))
            or any(character.isspace() for character in value)
        ):
            raise ValueError("observability route is invalid")
        return value
    if name in {"provider_called", "throttled"}:
        if not isinstance(value, bool):
            raise ValueError(f"observability field {name} is invalid")
        return value
    raise ValueError(f"observability field {name} is not allowlisted")


def configure_logging(*, json_logs: bool) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if json_logs else TextFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for transport_logger in ("httpx", "httpcore"):
        logging.getLogger(transport_logger).setLevel(logging.WARNING)
