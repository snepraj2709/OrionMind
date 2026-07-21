from __future__ import annotations

from uuid import UUID

import pytest

from app.modules.processing.quality import (
    QualityHistory,
    compute_quality_features,
    finalize_quality,
)
from app.modules.processing.schemas import EntryQualityResult
from app.shared.security.encryption import AesGcmContentCipher


USER = UUID("a1111111-1111-4111-8111-111111111111")


def cipher() -> AesGcmContentCipher:
    return AesGcmContentCipher(
        encryption_keys={"entry-key": b"e" * 32},
        active_encryption_key_id="entry-key",
        fingerprint_keys={"fingerprint-key": b"f" * 32},
        active_fingerprint_key_id="fingerprint-key",
    )


def quality(**changes) -> EntryQualityResult:
    return EntryQualityResult.model_validate(
        {
            "entry_kind": "personal_reflection",
            "lived_experience_score": 0.8,
            "self_reference_score": 0.8,
            "emotional_information_score": 0.8,
            "causal_reasoning_score": 0.8,
            "personal_relevance_score": 0.8,
            "confidence": 0.9,
            "eligibility": "accepted",
            "exclusion_reason_codes": [],
            **changes,
        }
    )


def test_short_valid_reflection_reaches_semantic_acceptance() -> None:
    result = compute_quality_features(
        "Felt dismissed after the call, so I avoided replying.",
        user_id=USER,
        cipher=cipher(),
    )
    assert result.features.word_count == 9
    assert result.features.hard_exclusion_codes == []
    assert finalize_quality(quality(), deterministic=result.features).eligibility == "accepted"
    two_words = compute_quality_features(
        "Work mattered.", user_id=USER, cipher=cipher()
    )
    assert two_words.features.repeated_ngram_ratio == 0
    assert two_words.features.hard_exclusion_codes == []


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("", "EMPTY_CONTENT"),
        ("hello testing mic", "TEST_OR_NOISE"),
        ("the and or", "NO_MEANINGFUL_CONTENT"),
    ],
)
def test_deterministic_garbage_is_excluded_without_semantic_help(
    content: str, reason: str
) -> None:
    result = compute_quality_features(content, user_id=USER, cipher=cipher())
    assert reason in result.features.hard_exclusion_codes
    decision = finalize_quality(quality(), deterministic=result.features)
    assert decision.eligibility == "excluded"
    assert reason in decision.exclusion_reason_codes


def test_exact_and_near_duplicates_join_the_accepted_cluster() -> None:
    service = cipher()
    original = compute_quality_features(
        "I felt calm after the meeting.", user_id=USER, cipher=service
    )
    history = (
        QualityHistory(
            duplicate_cluster_key=original.duplicate_cluster_key,
            ngram_sketch=original.ngram_sketch,
            eligibility="accepted",
        ),
    )
    exact = compute_quality_features(
        "I felt calm after the meeting.",
        user_id=USER,
        cipher=service,
        history=history,
    )
    near = compute_quality_features(
        "I felt calm after the meeting!",
        user_id=USER,
        cipher=service,
        history=history,
    )
    assert exact.features.exact_duplicate is True
    assert exact.features.hard_exclusion_codes == ["EXACT_DUPLICATE"]
    assert near.features.near_duplicate_similarity == 1
    assert near.features.hard_exclusion_codes == ["NEAR_DUPLICATE"]
    assert near.duplicate_cluster_key == original.duplicate_cluster_key
    assert all(len(item) == 16 for item in near.ngram_sketch)


def test_repetition_rule_does_not_reject_causal_or_emotional_short_text() -> None:
    causal = compute_quality_features(
        "Felt hurt so felt hurt so felt hurt so I paused.",
        user_id=USER,
        cipher=cipher(),
    )
    assert "REPEATED_NGRAMS" not in causal.features.hard_exclusion_codes
    copied = compute_quality_features(
        '> "A copied technical paragraph belongs to somebody else."',
        user_id=USER,
        cipher=cipher(),
    )
    assert copied.features.copied_text_ratio > 0.9
    assert "REPEATED_NGRAMS" not in copied.features.hard_exclusion_codes


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, "accepted"),
        ({"confidence": 0.69}, "uncertain"),
        ({"entry_kind": "test_or_noise", "confidence": 0.9}, "excluded"),
        ({"entry_kind": "informational_text", "confidence": 0.9}, "excluded"),
        ({"entry_kind": "copied_or_quoted_text", "confidence": 0.9}, "excluded"),
        ({"entry_kind": "task_or_note", "confidence": 0.9}, "excluded"),
        (
            {
                "entry_kind": "unclear",
                "lived_experience_score": 0.45,
                "self_reference_score": 0.4,
                "emotional_information_score": 0.4,
                "causal_reasoning_score": 0.4,
                "personal_relevance_score": 0.4,
                "eligibility": "uncertain",
            },
            "uncertain",
        ),
        (
            {
                "entry_kind": "creative_writing",
                "lived_experience_score": 0.1,
                "self_reference_score": 0.1,
                "emotional_information_score": 0.1,
                "causal_reasoning_score": 0.1,
                "personal_relevance_score": 0.1,
                "eligibility": "excluded",
            },
            "excluded",
        ),
    ],
)
def test_semantic_quality_decision_boundaries(changes, expected: str) -> None:
    deterministic = compute_quality_features(
        "I reflected on how the work affected me.",
        user_id=USER,
        cipher=cipher(),
    ).features
    assert finalize_quality(quality(**changes), deterministic=deterministic).eligibility == expected
