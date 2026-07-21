from __future__ import annotations

import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.reflection_engine.preflight import (
    ModelAccessPreflightError,
    ModelAccessTarget,
    check_reflection_model_access,
)
from app.shared.config.settings import get_settings
from app.shared.integrations.openai import build_openai_client
from app.shared.observability.logging import configure_logging


def main() -> None:
    settings = get_settings()
    configure_logging(json_logs=settings.LOG_FORMAT == "json")
    api_key = settings.OPENAI_API_KEY.get_secret_value().strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required for the access preflight.")
    targets = (
        ModelAccessTarget("entry_analysis", settings.OPENAI_ENTRY_ANALYSIS_MODEL),
        ModelAccessTarget("synthesis", settings.OPENAI_REFLECTION_SYNTHESIS_MODEL),
        ModelAccessTarget("critic", settings.OPENAI_REFLECTION_CRITIC_MODEL),
    )
    try:
        check_reflection_model_access(build_openai_client(api_key), targets)
    except ModelAccessPreflightError as exc:
        roles = ", ".join(exc.failed_roles)
        raise SystemExit(f"Reflection model access unavailable for: {roles}.") from None


if __name__ == "__main__":
    main()
