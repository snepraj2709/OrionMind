from __future__ import annotations

import json

import pytest

from scripts.run_reflection_hardening_e2e import (
    LiveRunError,
    _assert_report_safe,
    _pooler_database_overrides,
    load_dataset,
)


def dataset() -> dict[str, object]:
    entries = [
        {
            "caseId": f"baseline-{index}",
            "phase": "baseline",
            "entryDate": f"2026-07-{index:02d}",
            "content": "synthetic reflective fixture",
            "expected": "accepted",
        }
        for index in range(1, 4)
    ]
    entries.extend(
        {
            "caseId": case_id,
            "phase": "excluded",
            "entryDate": "2026-07-10",
            "content": "" if case_id == "blank" else "synthetic exclusion fixture",
            "expected": "api_rejected" if case_id == "blank" else "excluded",
        }
        for case_id in (
            "blank",
            "hello-testing-mic",
            "exact-duplicate",
            "near-duplicate",
            "copied-informational",
            "task-only",
        )
    )
    entries.extend(
        {
            "caseId": case_id,
            "phase": "update",
            "entryDate": "2026-07-20",
            "content": "synthetic counterevidence fixture",
            "expected": "accepted",
        }
        for case_id in (
            "contradiction-one",
            "contradiction-two",
            "prompt-injection",
        )
    )
    return {"entries": entries}


def test_load_dataset_requires_all_bounded_cases(tmp_path) -> None:
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(dataset()))

    entries = load_dataset(path)

    assert len(entries) == 12
    assert {entry.phase for entry in entries} == {"baseline", "excluded", "update"}

    invalid = dataset()
    invalid["entries"] = [
        entry
        for entry in invalid["entries"]  # type: ignore[index]
        if entry["caseId"] != "prompt-injection"
    ]
    path.write_text(json.dumps(invalid))
    with pytest.raises(LiveRunError, match="missing or duplicated"):
        load_dataset(path)


def test_report_safety_rejects_content_bearing_keys() -> None:
    _assert_report_safe({"entryId": "opaque", "counts": [1, 2]})

    with pytest.raises(LiveRunError, match="contains content"):
        _assert_report_safe({"entries": [{"content": "must not be reported"}]})


def test_pooler_override_preserves_roles_and_credentials_in_memory() -> None:
    env = {
        "SUPABASE_URL": "https://projectref.supabase.co",
        "APP_DATABASE_URL": "postgresql+psycopg://app:app-secret@db.projectref.supabase.co:5432/postgres?sslmode=require",
        "WORKER_DATABASE_URL": "postgresql+psycopg://worker:worker-secret@db.projectref.supabase.co:5432/postgres?sslmode=require",
        "ADMIN_APP_DATABASE_URL": "postgresql://admin:admin-secret@db.projectref.supabase.co:5432/postgres?sslmode=require",
    }

    overrides = _pooler_database_overrides(
        env, "aws-0-ap-northeast-1.pooler.supabase.com"
    )

    assert set(overrides) == {
        "APP_DATABASE_URL",
        "WORKER_DATABASE_URL",
        "ADMIN_APP_DATABASE_URL",
    }
    assert "app.projectref:app-secret" in overrides["APP_DATABASE_URL"]
    assert "worker.projectref:worker-secret" in overrides["WORKER_DATABASE_URL"]
    assert "admin.projectref:admin-secret" in overrides["ADMIN_APP_DATABASE_URL"]
    assert all(
        "@aws-0-ap-northeast-1.pooler.supabase.com:5432/" in value
        for value in overrides.values()
    )
    assert all("sslmode=require" in value for value in overrides.values())


def test_pooler_override_rejects_non_supabase_host() -> None:
    with pytest.raises(LiveRunError, match="pooler host is invalid"):
        _pooler_database_overrides(
            {"SUPABASE_URL": "https://projectref.supabase.co"},
            "database.example.test",
        )


def test_pooler_override_rejects_invalid_project_or_database_url() -> None:
    with pytest.raises(LiveRunError, match="project reference is invalid"):
        _pooler_database_overrides(
            {"SUPABASE_URL": "https://database.example.test"},
            "aws-0-ap-northeast-1.pooler.supabase.com",
        )

    with pytest.raises(LiveRunError, match="cannot be routed"):
        _pooler_database_overrides(
            {
                "SUPABASE_URL": "https://projectref.supabase.co",
                "APP_DATABASE_URL": "not a database URL",
            },
            "aws-0-ap-northeast-1.pooler.supabase.com",
        )
