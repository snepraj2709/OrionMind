from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from app.modules.processing.embeddings import (
    EMBEDDING_DIMENSIONS,
    OpenAISignalEmbeddingProvider,
)
from app.modules.processing.provider import ProviderResponseError


class Embeddings:
    def __init__(self, response) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class Client:
    def __init__(self, response) -> None:
        self.embeddings = Embeddings(response)

    def with_options(self, **_kwargs):
        return self


def provider(response):
    client = Client(response)
    return OpenAISignalEmbeddingProvider(
        client,
        model="text-embedding-3-small",
        connect_timeout=1,
        response_timeout=1,
        total_timeout=2,
    ), client


def test_signal_embeddings_are_batched_fixed_dimension_and_content_safe_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[0] = 1.0
    response = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=vector)],
        usage=SimpleNamespace(prompt_tokens=17),
    )
    instance, client = provider(response)
    private_text = "normalized reflection containing private content"
    caplog.set_level(logging.INFO)

    result = instance.embed(
        texts=(private_text,),
        safety_identifier="safe-owner-fingerprint",
    )

    assert result == (tuple(vector),)
    assert client.embeddings.calls == [
        {
            "model": "text-embedding-3-small",
            "input": [private_text],
            "dimensions": EMBEDDING_DIMENSIONS,
            "encoding_format": "float",
        }
    ]
    assert private_text not in caplog.text
    record = next(
        item
        for item in caplog.records
        if getattr(item, "orion_event", None) == "signal_embedding_attempt"
    )
    assert record.orion_fields["input_tokens"] == 17


def test_signal_embedding_response_requires_one_finite_fixed_dimension_vector() -> None:
    response = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=[0.0])],
        usage=None,
    )
    instance, _client = provider(response)

    with pytest.raises(ProviderResponseError, match="response is invalid"):
        instance.embed(texts=("safe",), safety_identifier="fingerprint")


@pytest.mark.parametrize("invalid_value", [True, "0.0"])
def test_signal_embedding_response_rejects_non_numeric_values(
    invalid_value: object,
) -> None:
    vector: list[object] = [0.0] * EMBEDDING_DIMENSIONS
    vector[0] = invalid_value
    response = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=vector)],
        usage=None,
    )
    instance, _client = provider(response)

    with pytest.raises(ProviderResponseError, match="response is invalid"):
        instance.embed(texts=("safe",), safety_identifier="fingerprint")
