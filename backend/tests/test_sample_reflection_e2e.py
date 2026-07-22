from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.shared.observability.reflection import token_usage
from scripts.run_sample_reflection_e2e import (
    LiveRunError,
    available_insight_count,
    atomic_write_json,
    build_settings,
    estimate_call_cost,
    failure_report,
    latency_summary,
    load_sample_entries,
    model_usage_report,
    parse_args,
    pipeline_event_report,
    schedule_synthesis,
    verify_worker_database,
)


ROOT = Path(__file__).resolve().parents[2]


def test_canonical_dataset_is_exactly_30_unique_entries() -> None:
    entries, digest = load_sample_entries(ROOT / "data/sample-entries.json")

    assert len(entries) == 30
    assert len({entry.entry_date for entry in entries}) == 30
    assert entries[0].entry_date.isoformat() == "2026-06-01"
    assert entries[-1].entry_date.isoformat() == "2026-06-30"
    assert len(digest) == 64
    assert all(entry.content.strip() for entry in entries)


def test_dataset_validation_rejects_unknown_fields(tmp_path: Path) -> None:
    sample = tmp_path / "sample.json"
    sample.write_text(
        json.dumps(
            [
                {
                    "entry_date": "01 June 2026",
                    "content": ["Reflective content"],
                    "unexpected": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LiveRunError, match="invalid shape") as exc_info:
        load_sample_entries(sample)

    assert exc_info.value.code == "INVALID_DATASET"


def test_worker_database_is_required_for_live_runner(
    tmp_path: Path,
) -> None:
    environment = tmp_path / ".env"
    environment.write_text(
        "APP_DATABASE_URL=postgresql+psycopg://postgres:secret@db.example.test:5432/postgres\n"
        "WORKER_DATABASE_URL=\n",
        encoding="utf-8",
    )

    with pytest.raises(LiveRunError) as exc_info:
        build_settings(environment, uuid4())

    assert exc_info.value.code == "WORKER_DATABASE_CONFIG_MISSING"


def test_worker_database_must_use_a_distinct_login(tmp_path: Path) -> None:
    environment = tmp_path / ".env"
    database_url = (
        "postgresql+psycopg://postgres:secret@db.example.test:5432/postgres"
    )
    environment.write_text(
        f"APP_DATABASE_URL={database_url}\nWORKER_DATABASE_URL={database_url}\n",
        encoding="utf-8",
    )

    with pytest.raises(LiveRunError) as exc_info:
        build_settings(environment, uuid4())

    assert exc_info.value.code == "WORKER_DATABASE_NOT_DISTINCT"


def test_worker_database_preflight_requires_worker_role(monkeypatch) -> None:
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _statement):
            raise RuntimeError("role denied")

    class Engine:
        def begin(self):
            return Connection()

    sessions = SimpleNamespace(worker_engine=Engine(), dispose=lambda: None)
    monkeypatch.setattr(
        "scripts.run_sample_reflection_e2e.build_database_sessions",
        lambda _settings: sessions,
    )

    with pytest.raises(LiveRunError) as exc_info:
        verify_worker_database(SimpleNamespace())

    assert exc_info.value.code == "WORKER_DATABASE_ROLE_UNAVAILABLE"


def test_worker_database_preflight_controls_invalid_url(tmp_path: Path) -> None:
    environment = tmp_path / ".env"
    environment.write_text(
        "APP_DATABASE_URL=postgresql+psycopg://app:secret@db.example.test/postgres\n"
        "WORKER_DATABASE_URL=orion-worker.railway.internal\n",
        encoding="utf-8",
    )

    settings = build_settings(environment, uuid4())
    with pytest.raises(LiveRunError) as exc_info:
        verify_worker_database(settings)

    assert exc_info.value.code == "WORKER_DATABASE_ROLE_UNAVAILABLE"


def test_worker_database_preflight_accepts_worker_role(monkeypatch) -> None:
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _statement):
            return None

        def scalar(self, _statement):
            return "orion_worker"

    class Engine:
        def begin(self):
            return Connection()

    disposed = []
    sessions = SimpleNamespace(
        worker_engine=Engine(), dispose=lambda: disposed.append(True)
    )
    monkeypatch.setattr(
        "scripts.run_sample_reflection_e2e.build_database_sessions",
        lambda _settings: sessions,
    )

    verify_worker_database(SimpleNamespace())

    assert disposed == [True]


def test_token_usage_reads_cache_and_reasoning_details() -> None:
    response = SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=2_000,
            input_tokens_details={
                "cached_tokens": 1_000,
                "cache_write_tokens": 500,
            },
            output_tokens=100,
            output_tokens_details=SimpleNamespace(reasoning_tokens=40),
        )
    )

    usage = token_usage(response)

    assert usage.input_tokens == 2_000
    assert usage.cached_input_tokens == 1_000
    assert usage.cache_write_input_tokens == 500
    assert usage.output_tokens == 100
    assert usage.reasoning_output_tokens == 40


def test_default_luna_price_uses_each_usage_bucket() -> None:
    cost = estimate_call_cost(
        {
            "serviceTier": "default",
            "model": "gpt-5.6-luna",
            "inputTokens": 2_000,
            "cachedInputTokens": 1_000,
            "cacheWriteInputTokens": 500,
            "outputTokens": 100,
        }
    )

    assert cost == pytest.approx(0.001825)


def test_model_report_distinguishes_model_roles_and_conditional_sol() -> None:
    base = {
        "prompt_version": "v1",
        "status": "success",
        "retry_class": "none",
        "service_tier": "default",
        "duration_ms": 100,
        "input_tokens": 1_000,
        "cached_input_tokens": 0,
        "cache_write_input_tokens": 0,
        "output_tokens": 100,
        "reasoning_output_tokens": 20,
    }
    events = [
        {
            "event": "entry_analysis_attempt",
            "model_role": "entry_analysis",
            "model_id": "gpt-5.6-luna",
            **base,
        },
        {
            "event": "reflection_model_attempt",
            "model_role": "synthesis",
            "model_id": "gpt-5.6-terra",
            **base,
        },
    ]

    report = model_usage_report(events)
    by_role = {item["role"]: item for item in report["roles"]}

    assert by_role["entry_analysis"]["calls"] == 1
    assert by_role["synthesis"]["calls"] == 1
    assert by_role["critic"]["calls"] == 0
    assert by_role["critic"]["eligibleCandidates"] == 0
    assert by_role["critic"]["outcome"] == "not_invoked"
    assert report["pricingComplete"] is True
    assert report["estimatedTotalCostUsd"] == pytest.approx(0.0056)


def test_pipeline_event_report_surfaces_safe_discard_reasons() -> None:
    report = pipeline_event_report(
        [
            {
                "event": "entry_analysis_materialized",
                "status": "accepted",
                "entry_kind": "personal_reflection",
            },
            {
                "event": "reflection_candidate_observed",
                "pattern_type": "hidden_driver",
                "outcome": "publishable",
            },
            {
                "event": "reflection_proposal_discarded",
                "reason_code": "EVIDENCE_ROLE_MISMATCH",
            },
        ]
    )

    assert report == {
        "entryAnalysisOutcomes": {"accepted:personal_reflection": 1},
        "candidateOutcomes": {"hidden_driver:publishable": 1},
        "proposalDiscardReasons": {"EVIDENCE_ROLE_MISMATCH": 1},
    }


def test_reflective_dataset_requires_an_available_insight_section() -> None:
    empty = {
        "data": {
            "hiddenDriver": {"status": "insufficient_evidence"},
            "recurringLoop": {"status": "insufficient_evidence"},
            "innerTensions": {"status": "insufficient_evidence"},
        }
    }
    available = {
        "data": {
            **empty["data"],
            "hiddenDriver": {"status": "available"},
        }
    }

    assert available_insight_count(empty) == 0
    assert available_insight_count(available) == 1


def test_unknown_service_tier_never_silently_undercounts_cost() -> None:
    report = model_usage_report(
        [
            {
                "event": "entry_analysis_attempt",
                "model_role": "entry_analysis",
                "model_id": "gpt-5.6-luna",
                "prompt_version": "v1",
                "status": "success",
                "retry_class": "none",
                "service_tier": "unknown",
                "duration_ms": 1,
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "cache_write_input_tokens": 0,
                "output_tokens": 10,
                "reasoning_output_tokens": 0,
            }
        ]
    )

    assert report["pricingComplete"] is False
    assert report["estimatedTotalCostUsd"] is None


def test_latency_summary_uses_nearest_rank_percentiles() -> None:
    assert latency_summary([10, 40, 20, 30]) == {
        "min": 10,
        "average": 25,
        "p50": 20,
        "p95": 40,
        "max": 40,
    }
    assert latency_summary([]) is None


def test_failure_report_is_controlled_and_atomic(tmp_path: Path) -> None:
    args = parse_args(
        [
            "--input",
            "data/sample-entries.json",
            "--output",
            str(tmp_path / "result.json"),
            "--frontend-env",
            ".env",
            "--backend-env",
            "backend/.env",
        ]
    )
    report = failure_report(
        args,
        started_at=datetime(2026, 7, 22, tzinfo=UTC),
        error=LiveRunError("SAFE_CODE", "A controlled failure."),
        elapsed_seconds=1.25,
    )

    atomic_write_json(args.output, report)
    stored = json.loads(args.output.read_text(encoding="utf-8"))

    assert stored["status"] == "failed"
    assert stored["errors"] == [
        {"code": "SAFE_CODE", "message": "A controlled failure."}
    ]
    assert stored["modelUsage"]["estimatedTotalCostUsd"] == 0.0
    assert "password" not in args.output.read_text(encoding="utf-8").lower()


def test_schedule_synthesis_uses_timestamp_aware_job_service() -> None:
    class Result:
        def mappings(self):
            return self

        def one(self):
            return {"timezone": "UTC", "last_schedule_local_date": None}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, *_args, **_kwargs):
            return Result()

    class Engine:
        def connect(self):
            return Connection()

    class Scheduler:
        def __init__(self) -> None:
            self.now = None
            self.uow = None

        def schedule_reflections(self, *, uow, now):
            self.uow = uow
            self.now = now
            return 1

    scheduler = Scheduler()
    unit_of_work = object()
    application = SimpleNamespace(
        state=SimpleNamespace(
            database_sessions=SimpleNamespace(
                application_engine=Engine(),
                unit_of_work_factory=unit_of_work,
            ),
            job_service=scheduler,
        )
    )

    assert schedule_synthesis(application, uuid4()) == 1
    assert scheduler.uow is unit_of_work
    assert scheduler.now.hour == 18
    assert scheduler.now.minute == 5
