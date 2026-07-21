from __future__ import annotations

from typing import Any, Protocol


class OpenAIClientFactory(Protocol):
    def __call__(self) -> Any: ...


def build_openai_client(api_key: str) -> Any:
    from openai import OpenAI

    return OpenAI(api_key=api_key, max_retries=0)
