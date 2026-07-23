from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.reflection_engine.evaluation import (
    EvaluationDatasetRejected,
    FrozenEvaluationDataset,
    ReviewReflectionEvaluationDataset,
    evaluate_frozen_dataset,
    evaluate_review_reflection_dataset,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate consented frozen Reflection analyzer results.",
        allow_abbrev=False,
    )
    parser.add_argument("dataset", type=Path)
    parser.add_argument(
        "--review-reflection",
        action="store_true",
        help="Evaluate the synthetic Review-to-Reflection metadata matrix.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        raw = args.dataset.read_text(encoding="utf-8")
        if args.review_reflection:
            review_dataset = ReviewReflectionEvaluationDataset.model_validate_json(
                raw
            )
        else:
            dataset = FrozenEvaluationDataset.model_validate_json(raw)
    except (OSError, ValidationError):
        dataset_name = (
            "Review-to-Reflection"
            if args.review_reflection
            else "frozen"
        )
        raise SystemExit(
            f"The {dataset_name} evaluation dataset is invalid."
        ) from None
    if args.review_reflection:
        review_result = evaluate_review_reflection_dataset(review_dataset)
        print(review_result.model_dump_json())
        if not review_result.passed:
            raise SystemExit(1)
        return
    try:
        frozen_result = evaluate_frozen_dataset(dataset)
    except EvaluationDatasetRejected as exc:
        raise SystemExit(str(exc)) from None
    print(frozen_result.model_dump_json())
    if not frozen_result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
