from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.shared.observability.logging import safe_log


logger = logging.getLogger("orion.reflection.preflight")
MODEL_ROLES = frozenset({"entry_analysis", "embedding", "synthesis", "critic"})


@dataclass(frozen=True, slots=True)
class ModelAccessTarget:
    role: str
    model_id: str


class ModelAccessPreflightError(RuntimeError):
    def __init__(self, failed_roles: Sequence[str]) -> None:
        self.failed_roles = tuple(failed_roles)
        super().__init__("reflection model access preflight failed")


def check_reflection_model_access(
    client: Any,
    targets: Sequence[ModelAccessTarget],
) -> tuple[ModelAccessTarget, ...]:
    """Use only Models.retrieve; never submit content or create a response."""

    if (
        len(targets) != 4
        or {target.role for target in targets} != MODEL_ROLES
        or any(not target.model_id.strip() for target in targets)
    ):
        raise ValueError("reflection model access targets are invalid")
    failed: list[str] = []
    for target in targets:
        try:
            client.models.retrieve(target.model_id)
        except Exception:
            failed.append(target.role)
            safe_log(
                logger,
                "reflection_model_access",
                model_role=target.role,
                model_id=target.model_id,
                access_status="unavailable",
            )
        else:
            safe_log(
                logger,
                "reflection_model_access",
                model_role=target.role,
                model_id=target.model_id,
                access_status="available",
            )
    if failed:
        raise ModelAccessPreflightError(failed)
    return tuple(targets)
