from __future__ import annotations

import json
import math
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text

from scripts.reflection_e2e.types import LiveRunError


PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"
PRICE_PER_MILLION_USD: dict[str, dict[str, tuple[Decimal, ...]]] = {
    "default": {
        "gpt-5.6-luna": tuple(map(Decimal, ("1", "0.1", "1.25", "6"))),
        "text-embedding-3-small": tuple(map(Decimal, ("0.02", "0", "0", "0"))),
        "gpt-5.6-terra": tuple(map(Decimal, ("2.5", "0.25", "3.125", "15"))),
        "gpt-5.6-sol": tuple(map(Decimal, ("5", "0.5", "6.25", "30"))),
    },
    "flex": {
        "gpt-5.6-luna": tuple(map(Decimal, ("0.5", "0.05", "0.625", "3"))),
        "gpt-5.6-terra": tuple(map(Decimal, ("1.25", "0.125", "1.5625", "7.5"))),
        "gpt-5.6-sol": tuple(map(Decimal, ("2.5", "0.25", "3.125", "15"))),
    },
    "priority": {
        "gpt-5.6-luna": tuple(map(Decimal, ("2", "0.2", "2.5", "12"))),
        "gpt-5.6-terra": tuple(map(Decimal, ("5", "0.5", "6.25", "30"))),
        "gpt-5.6-sol": tuple(map(Decimal, ("10", "1", "12.5", "60"))),
    },
}
MODEL_ROLES = {
    "entry_analysis": "gpt-5.6-luna",
    "embedding": "text-embedding-3-small",
    "synthesis": "gpt-5.6-terra",
    "critic": "gpt-5.6-sol",
}


def pipeline_event_report(events: list[dict[str, Any]]) -> dict[str, Any]:
    proposal_discards = Counter(
        str(event.get("reason_code", "UNKNOWN"))
        for event in events
        if event.get("event") == "reflection_proposal_discarded"
    )
    candidate_outcomes = Counter(
        (str(event.get("pattern_type", "unknown")), str(event.get("outcome", "unknown")))
        for event in events
        if event.get("event") == "reflection_candidate_observed"
    )
    entry_outcomes = Counter(
        (str(event.get("status", "unknown")), str(event.get("entry_kind", "unknown")))
        for event in events
        if event.get("event") == "entry_analysis_materialized"
    )
    return {
        "entryAnalysisOutcomes": {
            f"{status}:{kind}": count
            for (status, kind), count in sorted(entry_outcomes.items())
        },
        "candidateOutcomes": {
            f"{pattern_type}:{outcome}": count
            for (pattern_type, outcome), count in sorted(candidate_outcomes.items())
        },
        "proposalDiscardReasons": dict(sorted(proposal_discards.items())),
    }


def available_insight_count(response: dict[str, Any]) -> int:
    data = response.get("data")
    if not isinstance(data, dict):
        return 0
    return sum(
        1
        for key in ("hiddenDriver", "recurringLoop", "innerTensions")
        if isinstance(data.get(key), dict) and data[key].get("status") == "available"
    )


def _grouped_counts(session: Any, sql: str, user_id: UUID) -> dict[str, int]:
    rows = session.execute(text(sql), {"user_id": user_id}).mappings()
    return {str(row["key"]): int(row["count"]) for row in rows}


def _two_key_counts(session: Any, sql: str, user_id: UUID) -> dict[str, int]:
    rows = session.execute(text(sql), {"user_id": user_id}).mappings()
    return {
        f"{row['first']}:{row['second']}": int(row["count"]) for row in rows
    }


def model_usage_report(events: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = [
        event
        for event in events
        if event.get("event")
        in {
            "entry_analysis_attempt",
            "signal_embedding_attempt",
            "reflection_model_attempt",
        }
    ]
    calls: list[dict[str, Any]] = []
    by_role: dict[str, list[dict[str, Any]]] = {
        role: [] for role in MODEL_ROLES
    }
    for ordinal, event in enumerate(attempts, start=1):
        role = str(event["model_role"])
        measured = {
            "ordinal": ordinal,
            "role": role,
            "model": str(event["model_id"]),
            "promptVersion": str(event["prompt_version"]),
            "status": str(event["status"]),
            "retryClass": str(event["retry_class"]),
            "serviceTier": str(event["service_tier"]),
            "durationMs": int(event["duration_ms"]),
            "inputTokens": int(event["input_tokens"]),
            "cachedInputTokens": int(event["cached_input_tokens"]),
            "cacheWriteInputTokens": int(event["cache_write_input_tokens"]),
            "outputTokens": int(event["output_tokens"]),
            "reasoningOutputTokens": int(event["reasoning_output_tokens"]),
        }
        measured["estimatedCostUsd"] = estimate_call_cost(measured)
        calls.append(measured)
        by_role.setdefault(role, []).append(measured)
    roles = []
    pricing_complete = all(call["estimatedCostUsd"] is not None for call in calls)
    for role, model in MODEL_ROLES.items():
        selected = by_role.get(role, [])
        durations = [int(call["durationMs"]) for call in selected]
        roles.append(
            {
                "role": role,
                "model": model,
                "usedAt": {
                    "entry_analysis": "entry_processing",
                    "embedding": "accepted_signal_persistence",
                    "synthesis": "reflection_synthesis",
                    "critic": "conditional_candidate_review",
                }[role],
                "routingRule": (
                    "abs(score-threshold) <= 0.05 or contradiction >= 0.20"
                    if role == "critic"
                    else None
                ),
                "eligibleCandidates": len(selected) if role == "critic" else None,
                "calls": len(selected),
                "successfulCalls": sum(call["status"] == "success" for call in selected),
                "inputTokens": sum(int(call["inputTokens"]) for call in selected),
                "cachedInputTokens": sum(
                    int(call["cachedInputTokens"]) for call in selected
                ),
                "cacheWriteInputTokens": sum(
                    int(call["cacheWriteInputTokens"]) for call in selected
                ),
                "outputTokens": sum(int(call["outputTokens"]) for call in selected),
                "reasoningOutputTokens": sum(
                    int(call["reasoningOutputTokens"]) for call in selected
                ),
                "modelWallTimeMs": sum(durations),
                "latencyMs": latency_summary(durations),
                "estimatedCostUsd": (
                    _money(
                        sum(
                            (
                                Decimal(str(call["estimatedCostUsd"]))
                                for call in selected
                                if call["estimatedCostUsd"] is not None
                            ),
                            start=Decimal(0),
                        )
                    )
                    if all(
                        call["estimatedCostUsd"] is not None for call in selected
                    )
                    else None
                ),
                "outcome": "not_invoked" if not selected else "measured",
            }
        )
    total = sum(
        (
            Decimal(str(call["estimatedCostUsd"]))
            for call in calls
            if call["estimatedCostUsd"] is not None
        ),
        start=Decimal(0),
    )
    return {
        "pricing": {
            "currency": "USD",
            "unit": "per_1m_tokens",
            "source": PRICING_SOURCE,
            "retrievedAt": datetime.now(UTC).isoformat(),
            "note": (
                "Estimate from response usage; the OpenAI billing dashboard is authoritative. "
                "Regional data-residency uplift is not included."
            ),
        },
        "roles": roles,
        "calls": calls,
        "pricingComplete": pricing_complete,
        "estimatedTotalCostUsd": _money(total) if pricing_complete else None,
    }


MODEL_ATTEMPT_FIELDS = (
    "event",
    "model_role",
    "model_id",
    "prompt_version",
    "status",
    "retry_class",
    "service_tier",
    "duration_ms",
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)


def _validated_model_attempt(
    value: dict[str, Any], *, allowed_roles: set[str]
) -> dict[str, Any]:
    try:
        role = str(value["model_role"])
        event = str(value["event"])
        model = str(value["model_id"])
        status = str(value["status"])
    except KeyError as exc:
        raise LiveRunError(
            "CONTINUATION_TELEMETRY_INVALID",
            "Continuation telemetry is missing a required field.",
        ) from exc
    if (
        event
        not in {
            "entry_analysis_attempt",
            "signal_embedding_attempt",
            "reflection_model_attempt",
        }
        or role not in allowed_roles
        or model != MODEL_ROLES[role]
        or status != "success"
    ):
        raise LiveRunError(
            "CONTINUATION_TELEMETRY_INVALID",
            "Continuation telemetry does not match the required successful model roles.",
        )
    sanitized = {field: value[field] for field in MODEL_ATTEMPT_FIELDS if field in value}
    try:
        for field in (
            "duration_ms",
            "input_tokens",
            "cached_input_tokens",
            "cache_write_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        ):
            number = int(sanitized[field])
            if number < 0:
                raise ValueError(field)
            sanitized[field] = number
        for field in ("prompt_version", "retry_class", "service_tier"):
            sanitized[field] = str(sanitized[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveRunError(
            "CONTINUATION_TELEMETRY_INVALID",
            "Continuation telemetry contains invalid usage fields.",
        ) from exc
    return sanitized


def load_continuation_events(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        raise LiveRunError(
            "CONTINUATION_TELEMETRY_MISSING",
            "Safe continuation telemetry is required to finalize an existing run.",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveRunError(
            "CONTINUATION_TELEMETRY_INVALID",
            "Continuation telemetry could not be read.",
        ) from exc
    if not isinstance(payload, list) or len(payload) != 2:
        raise LiveRunError(
            "CONTINUATION_TELEMETRY_INVALID",
            "Continuation telemetry must contain exactly one Terra and one Sol attempt.",
        )
    events = [
        _validated_model_attempt(item, allowed_roles={"synthesis", "critic"})
        for item in payload
        if isinstance(item, dict)
    ]
    if len(events) != 2 or Counter(event["model_role"] for event in events) != {
        "synthesis": 1,
        "critic": 1,
    }:
        raise LiveRunError(
            "CONTINUATION_TELEMETRY_INVALID",
            "Continuation telemetry must contain exactly one Terra and one Sol attempt.",
        )
    return events


def prior_model_attempts(report: dict[str, Any]) -> list[dict[str, Any]]:
    usage = report.get("modelUsage")
    calls = usage.get("calls") if isinstance(usage, dict) else None
    if not isinstance(calls, list) or len(calls) != 30:
        raise LiveRunError(
            "PRIOR_RUN_INVALID",
            "The prior result does not contain the 30 measured Luna attempts.",
        )
    events: list[dict[str, Any]] = []
    for call in calls:
        if not isinstance(call, dict):
            raise LiveRunError(
                "PRIOR_RUN_INVALID", "A prior model-attempt record is invalid."
            )
        snake_case = {
            "event": "entry_analysis_attempt",
            "model_role": call.get("role"),
            "model_id": call.get("model"),
            "prompt_version": call.get("promptVersion"),
            "status": call.get("status"),
            "retry_class": call.get("retryClass"),
            "service_tier": call.get("serviceTier"),
            "duration_ms": call.get("durationMs"),
            "input_tokens": call.get("inputTokens"),
            "cached_input_tokens": call.get("cachedInputTokens"),
            "cache_write_input_tokens": call.get("cacheWriteInputTokens"),
            "output_tokens": call.get("outputTokens"),
            "reasoning_output_tokens": call.get("reasoningOutputTokens"),
        }
        events.append(
            _validated_model_attempt(snake_case, allowed_roles={"entry_analysis"})
        )
    return events


def estimate_call_cost(call: dict[str, Any]) -> float | None:
    tier = str(call["serviceTier"])
    if tier == "standard":
        tier = "default"
    model = str(call["model"])
    rates = PRICE_PER_MILLION_USD.get(tier, {}).get(model)
    if rates is None:
        return None
    input_tokens = int(call["inputTokens"])
    cached = int(call["cachedInputTokens"])
    cache_write = int(call["cacheWriteInputTokens"])
    output = int(call["outputTokens"])
    uncached = max(0, input_tokens - cached - cache_write)
    input_rate, cached_rate, cache_write_rate, output_rate = rates
    cost = (
        Decimal(uncached) * input_rate
        + Decimal(cached) * cached_rate
        + Decimal(cache_write) * cache_write_rate
        + Decimal(output) * output_rate
    ) / Decimal(1_000_000)
    return _money(cost)


def latency_summary(values: list[int]) -> dict[str, int] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "average": round(sum(ordered) / len(ordered)),
        "p50": _percentile(ordered, 0.50),
        "p95": _percentile(ordered, 0.95),
        "max": ordered[-1],
    }


def _percentile(ordered: list[int], percentile: float) -> int:
    index = max(0, math.ceil(len(ordered) * percentile) - 1)
    return ordered[index]


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))
