from __future__ import annotations

import json
from pathlib import Path

from scripts.run_sample_reflection_offline import run_offline


ROOT = Path(__file__).resolve().parents[2]
SAMPLE_ENTRIES = ROOT / "data" / "sample-entries.json"


def test_offline_fixture_exercises_all_entries_and_snapshot_sections() -> None:
    result = run_offline(SAMPLE_ENTRIES)

    assert result["status"] == "passed"
    assert result["proofMode"] == "offline_fixture"
    assert result["dataset"]["entryCount"] == 30
    assert len(result["entryBreakdown"]) == 30
    assert all(
        item["analysisEligibility"] == "accepted"
        and item["hardExclusionCodes"] == []
        and item["modelCalls"] == 0
        for item in result["entryBreakdown"]
    )
    assert result["providerBoundary"]["externalModelCalls"] == 0
    assert result["providerBoundary"]["externalDatabaseWrites"] == 0
    assert result["pipeline"]["publishedCandidateCount"] == 3
    assert result["pipeline"]["snapshotEvidenceCount"] > 0
    assert {
        (item["patternType"], item["status"])
        for item in result["insights"]
    } == {
        ("hidden_driver", "available"),
        ("recurring_loop", "available"),
        ("inner_tension", "available"),
    }


def test_offline_result_contains_no_entry_text_or_external_proof_claim() -> None:
    source = json.loads(SAMPLE_ENTRIES.read_text(encoding="utf-8"))
    result = run_offline(SAMPLE_ENTRIES)
    encoded = json.dumps(result)

    assert all(item["content"][0][:40] not in encoded for item in source)
    assert "sourceQuote" not in encoded
    assert "live" not in result["proofMode"]
    assert any("No OpenAI request" in item for item in result["limitations"])
