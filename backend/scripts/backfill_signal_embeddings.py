from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import _build_content_cipher, _build_signal_embedding_provider
from app.modules.processing.embedding_backfill import (
    EmbeddingBackfillRepository,
    EmbeddingBackfillService,
)
from app.shared.config.settings import Settings
from app.shared.database.session import build_database_sessions
from app.shared.observability.reflection import ReflectionTelemetry


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or execute the bounded, null-only signal embedding backfill.",
        allow_abbrev=False,
    )
    parser.add_argument("--backend-env", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-external-cost", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.execute and not args.acknowledge_external_cost:
        raise SystemExit("--execute requires --acknowledge-external-cost")
    settings = Settings(_env_file=args.backend_env)
    sessions = build_database_sessions(settings)
    try:
        service = EmbeddingBackfillService(
            repository=EmbeddingBackfillRepository(),
            cipher=_build_content_cipher(settings),
            provider=_build_signal_embedding_provider(
                settings, ReflectionTelemetry()
            ),
            model_id=settings.OPENAI_SIGNAL_EMBEDDING_MODEL,
        )
        result = (
            service.run_batch(
                uow=sessions.unit_of_work_factory, batch_size=args.batch_size
            )
            if args.execute
            else service.dry_run(
                uow=sessions.unit_of_work_factory, batch_size=args.batch_size
            )
        )
        print(result.model_dump_json(by_alias=True))
    finally:
        sessions.dispose()


if __name__ == "__main__":
    main()
