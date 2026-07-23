from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.processing.materialization import _materialize_signals
from app.modules.processing.redaction import OffsetMap
from app.modules.processing.schemas import ModelEntryAnalysis
from app.modules.review.types import (
    ENTRY_INSIGHT_CATEGORIES,
    ENTRY_INSIGHT_CATEGORY_BY_TYPE,
    ENTRY_INSIGHT_TYPES,
)
from app.shared.security.encryption import AesGcmContentCipher


USER = UUID("c1111111-1111-4111-8111-111111111111")
ENTRY_DATE = date(2026, 7, 23)
CONTENT = "I learned that quiet planning helps me feel capable."


def cipher() -> AesGcmContentCipher:
    return AesGcmContentCipher(
        encryption_keys={"review-key": b"r" * 32},
        active_encryption_key_id="review-key",
        fingerprint_keys={"fingerprint-key": b"f" * 32},
        active_fingerprint_key_id="fingerprint-key",
    )


def analysis(signal_type: str = "self_knowledge") -> ModelEntryAnalysis:
    return ModelEntryAnalysis.model_validate(
        {
            "quality": {
                "entry_kind": "personal_reflection",
                "lived_experience_score": 0.9,
                "self_reference_score": 0.9,
                "emotional_information_score": 0.8,
                "causal_reasoning_score": 0.8,
                "personal_relevance_score": 0.9,
                "confidence": 0.92,
                "eligibility": "accepted",
                "exclusion_reason_codes": [],
            },
            "signals": [
                {
                    "signal_type": signal_type,
                    "normalized_label": "quiet planning supports capability",
                    "interpretation": "Quiet planning helps the writer feel capable.",
                    "source_quote": CONTENT,
                    "source_start": 0,
                    "source_end": len(CONTENT),
                    "themes": ["personal_growth"],
                    "need_tags": ["competence"],
                    "loop_role": "interpretation",
                    "inference_level": "inferred",
                    "confidence": 0.91,
                }
            ],
            "legacy": {
                "ideas": [],
                "memories": [],
                "theme": {"mode": None, "themes": []},
                "reflection": {
                    "filled_energy": None,
                    "drained_energy": None,
                    "learned_about_self": None,
                },
            },
        }
    )


@pytest.mark.parametrize("signal_type", ENTRY_INSIGHT_TYPES)
def test_every_entry_insight_type_maps_to_its_frozen_category(
    signal_type: str,
) -> None:
    service = cipher()
    row = _materialize_signals(
        analysis(signal_type),
        user_id=USER,
        original_content=CONTENT,
        redacted_text=CONTENT,
        offset_map=OffsetMap(()),
        duplicate_cluster_key=None,
        cipher=service,
        entry_date=ENTRY_DATE,
        model_id="test-model",
        prompt_version="entry-analysis-v3",
        embeddings=((1.0, 0.0),),
        embedding_model_id="test-embedding",
    )[0]
    review_item = row["review_item"]

    assert isinstance(review_item, dict)
    assert review_item["category"] == ENTRY_INSIGHT_CATEGORY_BY_TYPE[signal_type]
    assert review_item["category"] in ENTRY_INSIGHT_CATEGORIES
    assert row["occurred_on"] == ENTRY_DATE.isoformat()
    assert CONTENT not in str(row)
    assert service.decrypt_json(
        review_item["statement_envelope"],
        user_id=USER,
        record_id=UUID(review_item["id"]),
        purpose="review_item_statement",
    ) == "Quiet planning helps the writer feel capable."
    assert service.decrypt_json(
        review_item["source_quote_envelope"],
        user_id=USER,
        record_id=UUID(review_item["id"]),
        purpose="review_item_source_quote",
    ) == CONTENT


@pytest.mark.parametrize(
    "signal_type",
    ("event", "emotion", "desire", "self_statement", "action", "outcome"),
)
def test_non_reviewable_legacy_signal_types_create_no_review_input(
    signal_type: str,
) -> None:
    row = _materialize_signals(
        analysis(signal_type),
        user_id=USER,
        original_content=CONTENT,
        redacted_text=CONTENT,
        offset_map=OffsetMap(()),
        duplicate_cluster_key=None,
        cipher=cipher(),
        entry_date=ENTRY_DATE,
        model_id="test-model",
        prompt_version="entry-analysis-v3",
        embeddings=((1.0, 0.0),),
    )[0]

    assert "review_item" not in row


@pytest.mark.parametrize(
    "extra",
    (
        {"id": "d1111111-1111-4111-8111-111111111111"},
        {"entry_id": "d1111111-1111-4111-8111-111111111111"},
        {"occurred_on": "1999-01-01"},
    ),
)
def test_model_cannot_supply_local_identity_or_date(extra: dict[str, str]) -> None:
    payload = analysis().model_dump()
    payload["signals"][0].update(extra)

    with pytest.raises(ValidationError):
        ModelEntryAnalysis.model_validate(payload)


def test_synthesized_inference_is_reserved_for_patterns() -> None:
    payload = analysis().model_dump()
    payload["signals"][0]["inference_level"] = "synthesized"

    with pytest.raises(ValidationError):
        ModelEntryAnalysis.model_validate(payload)
