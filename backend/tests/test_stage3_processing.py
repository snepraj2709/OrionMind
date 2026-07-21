from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.processing.provider import OpenAIExtractionProvider, ProviderUnavailableError
from app.modules.processing.schemas import ModelEntryExtraction
from app.modules.processing.service import _provider_content, materialize_extraction
from app.modules.processing.source_segments import create_source_segments
from app.modules.processing.types import ThemeDefinition


THEMES = tuple(
    ThemeDefinition(key=key, name=name)
    for key, name in (
        ("career", "Career"),
        ("money", "Money"),
        ("health", "Health"),
        ("love_life", "Love Life"),
        ("family_friends", "Family & Friends"),
        ("personal_growth", "Personal Growth"),
        ("fun_recreation", "Fun & Recreation"),
        ("home_lifestyle", "Home & Lifestyle"),
    )
)


def extraction(*, mode=None, themes=None, ideas=None, memories=None, confidence=0.8):
    return ModelEntryExtraction.model_validate(
        {
            "ideas": ideas or [],
            "memories": memories or [],
            "theme": {"mode": mode, "themes": themes or []},
            "reflection": {
                "filled_energy": {"activity": "the walk", "confidence": confidence},
                "drained_energy": None,
                "learned_about_self": None,
            },
        }
    )


@pytest.mark.parametrize(
    ("mode", "items", "scores"),
    [
        (None, [], []),
        ("dominant", [("career", "primary", "segment_0001")], [1.0]),
        (
            "dominant",
            [("career", "primary", "segment_0001"), ("health", "secondary", "segment_0002")],
            [0.6265, 0.3735],
        ),
        (
            "balanced",
            [
                ("career", "primary", "segment_0001"),
                ("health", "secondary", "segment_0002"),
                ("money", "tertiary", "segment_0003"),
            ],
            [0.4, 0.35, 0.25],
        ),
    ],
)
def test_zero_one_two_three_theme_normalization(mode, items, scores) -> None:
    content = "A walk energized me. Work felt meaningful. I reviewed my budget."
    model = extraction(
        mode=mode,
        themes=[
            {"key": key, "tier": tier, "evidence_segment_id": segment}
            for key, tier, segment in items
        ],
    )
    result = materialize_extraction(
        model,
        content=content,
        allowed_keys={item.key for item in THEMES},
        reflection_threshold=0.8,
    )
    assert [item.score for item in result.theme.themes] == scores


@pytest.mark.parametrize(
    "theme",
    [
        {"mode": "balanced", "themes": [{"key": "career", "tier": "primary", "evidence_segment_id": "segment_0001"}]},
        {"mode": None, "themes": [{"key": "career", "tier": "primary", "evidence_segment_id": "segment_0001"}]},
        {"mode": "dominant", "themes": [{"key": "career", "tier": "secondary", "evidence_segment_id": "segment_0001"}]},
        {"mode": "dominant", "themes": [
            {"key": "career", "tier": "primary", "evidence_segment_id": "segment_0001"},
            {"key": "career", "tier": "secondary", "evidence_segment_id": "segment_0002"},
        ]},
    ],
)
def test_invalid_modes_tiers_and_duplicate_keys_are_rejected(theme) -> None:
    with pytest.raises(ValidationError):
        ModelEntryExtraction.model_validate(
            {
                "ideas": [],
                "memories": [],
                "theme": theme,
                "reflection": {
                    "filled_energy": None,
                    "drained_energy": None,
                    "learned_about_self": None,
                },
            }
        )


def test_unknown_theme_and_segment_references_are_rejected() -> None:
    content = "Work felt meaningful."
    unknown_theme = extraction(
        mode="dominant",
        themes=[{"key": "unknown", "tier": "primary", "evidence_segment_id": "segment_0001"}],
    )
    with pytest.raises(ValueError, match="outside fixed config"):
        materialize_extraction(
            unknown_theme,
            content=content,
            allowed_keys={item.key for item in THEMES},
            reflection_threshold=0.8,
        )
    unknown_segment = extraction(ideas=[{"source_segment_id": "segment_9999"}])
    with pytest.raises(ValueError, match="source segment"):
        materialize_extraction(
            unknown_segment,
            content=content,
            allowed_keys={item.key for item in THEMES},
            reflection_threshold=0.8,
        )


def test_source_spans_are_exact_and_reflection_threshold_is_inclusive() -> None:
    content = "  I should call my mentor.\n\nLast year I moved to Pune.  "
    segments = create_source_segments(content)
    assert [segment.text(content) for segment in segments] == [
        "I should call my mentor.",
        "Last year I moved to Pune.",
    ]
    model = extraction(
        ideas=[{"source_segment_id": "segment_0001"}],
        memories=[{"source_segment_id": "segment_0002"}],
        confidence=0.8,
    )
    result = materialize_extraction(
        model,
        content=content,
        allowed_keys={item.key for item in THEMES},
        reflection_threshold=0.8,
    )
    assert result.ideas[0].content == "I should call my mentor."
    assert result.memories[0].content == "Last year I moved to Pune."
    assert result.reflection.filled_energy is not None
    below = materialize_extraction(
        extraction(confidence=0.79999),
        content="A long walk energized me.",
        allowed_keys={item.key for item in THEMES},
        reflection_threshold=0.8,
    )
    assert below.reflection.filled_energy is None


def test_provider_input_cap_preserves_full_source_boundary_separation() -> None:
    source = "😀" * 60_000
    limited = _provider_content(source)
    assert len(limited) == 50_000
    assert len(limited.encode("utf-8")) == 200_000
    assert len(source) == 60_000


class Calls:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.models = []

    def parse(self, **kwargs):
        self.models.append(kwargs["model"])
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=outcome))]
        )


class Client:
    def __init__(self, calls: Calls):
        self.calls = calls
        self.options = []
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=calls))

    def with_options(self, **kwargs):
        self.options.append(kwargs)
        return self


class Retryable(Exception):
    status_code = 429


def provider(client: Client) -> OpenAIExtractionProvider:
    return OpenAIExtractionProvider(
        client,
        primary_model="primary",
        fallback_model="fallback",
        connect_timeout=1,
        response_timeout=2,
        total_timeout=10,
    )


def test_primary_success_disables_sdk_retries_and_uses_no_fallback() -> None:
    calls = Calls([extraction()])
    client = Client(calls)
    result = provider(client).extract(content="Work felt meaningful.", themes=THEMES)
    assert result.theme.themes == []
    assert calls.models == ["primary"]
    assert client.options[0]["max_retries"] == 0


def test_only_retryable_primary_failure_uses_one_fallback() -> None:
    calls = Calls([Retryable(), extraction()])
    result = provider(Client(calls)).extract(content="Work felt meaningful.", themes=THEMES)
    assert result.theme.themes == []
    assert calls.models == ["primary", "fallback"]


def test_nonretryable_and_malformed_outputs_do_not_fallback() -> None:
    for outcome in (ValueError("bad request"), {"unexpected": "provider payload"}):
        calls = Calls([outcome])
        with pytest.raises(ProviderUnavailableError):
            provider(Client(calls)).extract(content="Work felt meaningful.", themes=THEMES)
        assert calls.models == ["primary"]


def test_trivial_content_performs_zero_provider_calls() -> None:
    calls = Calls([])
    result = provider(Client(calls)).extract(content="mic test", themes=THEMES)
    assert result.theme.mode is None
    assert calls.models == []
