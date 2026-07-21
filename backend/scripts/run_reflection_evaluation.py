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
    evaluate_frozen_dataset,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate consented frozen Reflection analyzer results.",
        allow_abbrev=False,
    )
    parser.add_argument("dataset", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        dataset = FrozenEvaluationDataset.model_validate_json(
            args.dataset.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError):
        raise SystemExit("The frozen evaluation dataset is invalid.") from None
    try:
        result = evaluate_frozen_dataset(dataset)
    except EvaluationDatasetRejected as exc:
        raise SystemExit(str(exc)) from None
    print(result.model_dump_json())
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
