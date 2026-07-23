from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.reflection_engine.evaluation import (
    ReviewReflectionEvaluationDataset,
    evaluate_review_reflection_dataset,
)
from scripts.run_reflection_evaluation import main


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "review_reflection_evaluation_v1.json"
)
FORBIDDEN_KEYS = {
    "correction",
    "entry_id",
    "journal",
    "note",
    "quote",
    "statement",
    "user_id",
}


def _raw_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_synthetic_review_reflection_fixture_covers_and_passes_every_dimension() -> None:
    dataset = ReviewReflectionEvaluationDataset.model_validate(_raw_fixture())
    result = evaluate_review_reflection_dataset(dataset)

    assert result.case_count == 24
    assert result.passed is True
    assert {
        item.dimension: (item.passed_count, item.case_count)
        for item in result.dimensions
    } == {
        "garbage_leakage": (3, 3),
        "evidence_attribution": (12, 12),
        "abstention": (6, 6),
        "feedback_sensitivity": (3, 3),
    }
    serialized = json.dumps(_raw_fixture(), sort_keys=True)
    assert not any(f'"{key}"' in serialized for key in FORBIDDEN_KEYS)


@pytest.mark.parametrize(
    ("case_index", "field", "value", "failed_dimension"),
    (
        (0, "expected_review_item_count", 1, "garbage_leakage"),
        (
            3,
            "expected_reason_codes",
            ["EVIDENCE_OWNER_MISMATCH"],
            "evidence_attribution",
        ),
        (15, "expected_status", "available", "abstention"),
        (
            22,
            "expected_effective_confidence",
            0.8,
            "feedback_sensitivity",
        ),
    ),
)
def test_synthetic_evaluation_reports_each_failed_invariant(
    case_index: int,
    field: str,
    value: object,
    failed_dimension: str,
) -> None:
    raw = deepcopy(_raw_fixture())
    cases = raw["cases"]
    assert isinstance(cases, list)
    case = cases[case_index]
    assert isinstance(case, dict)
    case[field] = value

    result = evaluate_review_reflection_dataset(
        ReviewReflectionEvaluationDataset.model_validate(raw)
    )

    assert result.passed is False
    failed = next(
        item for item in result.dimensions if item.dimension == failed_dimension
    )
    assert failed.passed_count == failed.case_count - 1


def test_synthetic_evaluation_schema_rejects_content() -> None:
    raw = _raw_fixture()
    cases = raw["cases"]
    assert isinstance(cases, list)
    first = cases[0]
    assert isinstance(first, dict)
    first["journal"] = "private text"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReviewReflectionEvaluationDataset.model_validate(raw)


@pytest.mark.parametrize(
    ("case_index", "field", "value", "message"),
    (
        (2, "eligibility_result", "excluded", "every eligibility result"),
        (
            14,
            "scenario",
            "offset_out_of_bounds",
            "every evidence attribution boundary",
        ),
        (
            20,
            "selected_pattern_types",
            [],
            "every section outcome",
        ),
        (23, "evidence_weight", 0.5, "every feedback weight"),
    ),
)
def test_synthetic_evaluation_schema_rejects_incomplete_matrices(
    case_index: int,
    field: str,
    value: object,
    message: str,
) -> None:
    raw = _raw_fixture()
    cases = raw["cases"]
    assert isinstance(cases, list)
    case = cases[case_index]
    assert isinstance(case, dict)
    case[field] = value

    with pytest.raises(ValidationError, match=message):
        ReviewReflectionEvaluationDataset.model_validate(raw)


@pytest.mark.parametrize(
    ("case_index", "field", "value"),
    (
        (0, "proposed_review_item_count", "2"),
        (3, "expected_reason_codes", ()),
        (15, "selected_pattern_types", ()),
        (22, "evidence_weight", "0.5"),
    ),
)
def test_synthetic_evaluation_schema_rejects_coerced_types(
    case_index: int,
    field: str,
    value: object,
) -> None:
    raw = _raw_fixture()
    cases = raw["cases"]
    assert isinstance(cases, list)
    case = cases[case_index]
    assert isinstance(case, dict)
    case[field] = value

    with pytest.raises(ValidationError):
        ReviewReflectionEvaluationDataset.model_validate(raw)


@pytest.mark.parametrize("version", (True, 1.0, "1"))
def test_synthetic_evaluation_schema_requires_an_exact_integer_version(
    version: object,
) -> None:
    raw = _raw_fixture()
    raw["version"] = version

    with pytest.raises(ValidationError):
        ReviewReflectionEvaluationDataset.model_validate(raw)


def test_review_reflection_evaluation_cli_emits_aggregate_metadata_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["--review-reflection", str(FIXTURE)])
    result = json.loads(capsys.readouterr().out)

    assert result["passed"] is True
    assert result["case_count"] == 24
    assert set(result) == {"case_count", "dimensions", "passed"}
    serialized = json.dumps(result, sort_keys=True)
    assert not any(f'"{key}"' in serialized for key in FORBIDDEN_KEYS)
