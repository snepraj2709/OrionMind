from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from app.modules.reflection_engine.schemas import (
    ReflectionCriticOutput,
    ReflectionSynthesisOutput,
)


class ReflectionProvider(Protocol):
    def synthesize(
        self,
        *,
        payload: str,
        safety_identifier: str,
    ) -> ReflectionSynthesisOutput | Mapping[str, object]: ...

    def critique(
        self,
        *,
        payload: str,
        safety_identifier: str,
    ) -> ReflectionCriticOutput | Mapping[str, object]: ...
