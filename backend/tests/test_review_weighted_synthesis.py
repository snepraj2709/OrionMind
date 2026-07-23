from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.modules.reflection_engine.repository import PersistedCandidateSignal
from app.modules.reflection_engine.schemas import AnalysisBasis, PreviousCandidate
from app.modules.reflection_engine.service import ReflectionEngineService
from app.shared.security.encryption import AesGcmContentCipher


USER_ID = UUID("a1111111-1111-4111-8111-111111111111")


def cipher() -> AesGcmContentCipher:
    return AesGcmContentCipher(
        encryption_keys={"entry-key": b"e" * 32},
        active_encryption_key_id="entry-key",
        fingerprint_keys={"fingerprint-key": b"f" * 32},
        active_fingerprint_key_id="fingerprint-key",
    )


def persisted_signal(*, model_confidence: float, evidence_weight: float) -> dict[str, object]:
    entry_id = uuid4()
    signal_id = uuid4()
    service_cipher = cipher()
    return {
        "id": str(signal_id),
        "user_id": str(USER_ID),
        "entry_id": str(entry_id),
        "entry_user_id": str(USER_ID),
        "analysis_id": str(uuid4()),
        "analysis_user_id": str(USER_ID),
        "analysis_entry_id": str(entry_id),
        "analysis_source_version": 1,
        "analysis_eligibility": "accepted",
        "entry_date": "2026-07-20",
        "signal_type": "need",
        "normalized_label_fingerprint": "a" * 64,
        "payload_envelope": service_cipher.encrypt_json(
            {
                "normalized_label": "focused work",
                "interpretation": "The entry may reflect a need for competence.",
                "source_quote": "focused work",
            },
            user_id=USER_ID,
            record_id=signal_id,
            purpose="entry_signal_payload",
        ),
        "entry_content_envelope": service_cipher.encrypt(
            "focused work",
            user_id=USER_ID,
            record_id=entry_id,
        ),
        "themes": ["career"],
        "need_tags": ["competence"],
        "loop_role": None,
        "confidence": model_confidence * evidence_weight,
        "model_confidence": model_confidence,
        "evidence_weight": evidence_weight,
        "source_start": 0,
        "source_end": 12,
        "occurred_on": "2026-07-20",
        "duplicate_cluster_key": None,
    }


@pytest.mark.parametrize(
    ("model_confidence", "evidence_weight", "effective_confidence"),
    [(0.8, 1.0, 0.8), (0.8, 0.5, 0.4), (0.8, 0.0, 0.0)],
)
def test_effective_confidence_is_model_confidence_times_review_weight(
    model_confidence: float,
    evidence_weight: float,
    effective_confidence: float,
) -> None:
    signal = PersistedCandidateSignal.model_validate(
        persisted_signal(
            model_confidence=model_confidence,
            evidence_weight=evidence_weight,
        )
    )
    assert signal.confidence == pytest.approx(effective_confidence)

    invalid = persisted_signal(
        model_confidence=model_confidence,
        evidence_weight=evidence_weight,
    )
    invalid["confidence"] = min(1.0, effective_confidence + 0.1)
    with pytest.raises(ValidationError, match="not review-weighted"):
        PersistedCandidateSignal.model_validate(invalid)


def test_snapshot_metadata_and_pattern_review_rows_are_normalized() -> None:
    service = ReflectionEngineService(
        repository=object(),  # type: ignore[arg-type]
        cipher=cipher(),
        synthesis_model_id="test-synthesis-model",
    )
    signal_rows = [
        persisted_signal(model_confidence=0.9, evidence_weight=1.0)
        for _ in range(3)
    ]
    for index, row in enumerate(signal_rows):
        row["analysis_source_version"] = index + 1
        row["entry_date"] = (date(2026, 7, 20) + timedelta(days=index)).isoformat()
        row["occurred_on"] = row["entry_date"]
        row["normalized_label_fingerprint"] = f"{index + 1:064x}"
    raw = {
        "source_version": 3,
        "basis_start": "2026-04-24",
        "basis_end": "2026-07-22",
        "valid_entry_count": 3,
        "distinct_entry_dates": 3,
        "reflective_word_count": 150,
        "signals": signal_rows,
        "candidates": [],
    }
    basis, signals, _ = service._materialize_basis(raw, user_id=USER_ID)
    batch = service.construct_candidates(
        user_id=USER_ID,
        basis=basis,
        signals=signals,
    )
    hidden = next(
        candidate
        for candidate in batch.candidates
        if candidate.pattern_type == "hidden_driver"
    )
    snapshot, _, _ = service._snapshot_rows(
        user_id=USER_ID,
        raw={"next_snapshot_version": 1, "excluded_entry_count": 0},
        basis=AnalysisBasis(
            source_version=3,
            basis_start=date(2026, 4, 24),
            basis_end=date(2026, 7, 22),
            valid_entry_count=3,
            distinct_entry_dates=3,
            reflective_word_count=150,
        ),
        candidates=[hidden],
        signals={signal.id: signal for signal in signals},
    )
    reviews = service._pattern_review_rows(
        user_id=USER_ID,
        source_version=3,
        candidates=[hidden],
        signals={signal.id: signal for signal in signals},
    )

    assert snapshot["model_name"] == "test-synthesis-model"
    assert snapshot["prompt_version"] == "reflection-synthesis-v2"
    assert snapshot["generated_at"]
    assert reviews == [
        {
            **reviews[0],
            "pattern_candidate_id": str(hidden.id),
            "item_type": "hidden_driver",
            "category": "hidden_driver",
            "source_entry_ids": [
                str(signal.entry_id) for signal in signals
            ],
            "source_dates": [
                signal.entry_date.isoformat() for signal in signals
            ],
            "inference_level": "synthesized",
            "model_confidence": hidden.score,
            "metadata": {
                "model_id": "test-synthesis-model",
                "prompt_version": "reflection-synthesis-v2",
                "source": "reflection_synthesis",
                "source_version": 3,
                "candidate_version": hidden.version,
            },
        }
    ]


def test_pattern_review_sources_are_deterministically_bounded_to_100_entries() -> None:
    service = ReflectionEngineService(
        repository=object(),  # type: ignore[arg-type]
        cipher=cipher(),
    )
    signal_rows = [
        persisted_signal(model_confidence=0.9, evidence_weight=1.0)
        for _ in range(101)
    ]
    signal_types = ("need", "belief", "self_knowledge")
    for index, row in enumerate(signal_rows):
        entry_date = date(2026, 7, 20) + timedelta(days=index % 3)
        row["analysis_source_version"] = index + 1
        row["entry_date"] = entry_date.isoformat()
        row["occurred_on"] = entry_date.isoformat()
        row["signal_type"] = signal_types[index % len(signal_types)]
        row["normalized_label_fingerprint"] = f"{index + 1:064x}"
    raw = {
        "source_version": 101,
        "basis_start": "2026-04-24",
        "basis_end": "2026-07-22",
        "valid_entry_count": 101,
        "distinct_entry_dates": 3,
        "reflective_word_count": 2020,
        "signals": signal_rows,
        "candidates": [],
    }
    basis, signals, _ = service._materialize_basis(raw, user_id=USER_ID)
    batch = service.construct_candidates(
        user_id=USER_ID,
        basis=basis,
        signals=signals,
    )
    hidden = next(
        candidate
        for candidate in batch.candidates
        if candidate.pattern_type == "hidden_driver"
    )
    reviews = service._pattern_review_rows(
        user_id=USER_ID,
        source_version=101,
        candidates=[hidden],
        signals={signal.id: signal for signal in signals},
    )
    expected = sorted(
        signals,
        key=lambda signal: (signal.entry_date, str(signal.entry_id)),
    )[:100]

    assert reviews[0]["source_entry_ids"] == [
        str(signal.entry_id) for signal in expected
    ]
    assert reviews[0]["source_dates"] == sorted(
        {signal.entry_date.isoformat() for signal in expected}
    )


def test_pattern_review_weight_weakens_score_and_persisted_evidence() -> None:
    service = ReflectionEngineService(
        repository=object(),  # type: ignore[arg-type]
        cipher=cipher(),
    )
    raw = {
        "source_version": 3,
        "basis_start": "2026-04-24",
        "basis_end": "2026-07-22",
        "valid_entry_count": 3,
        "distinct_entry_dates": 3,
        "reflective_word_count": 150,
        "signals": [
            {
                **persisted_signal(model_confidence=0.9, evidence_weight=1.0),
                "analysis_source_version": index + 1,
                "entry_date": (
                    date(2026, 7, 20) + timedelta(days=index)
                ).isoformat(),
                "occurred_on": (
                    date(2026, 7, 20) + timedelta(days=index)
                ).isoformat(),
                "signal_type": ("need", "belief", "self_knowledge")[index],
                "normalized_label_fingerprint": f"{index + 1:064x}",
            }
            for index in range(3)
        ],
        "candidates": [],
    }
    basis, signals, _ = service._materialize_basis(raw, user_id=USER_ID)
    first = service.construct_candidates(
        user_id=USER_ID,
        basis=basis,
        signals=signals,
    )
    original = next(
        candidate
        for candidate in first.candidates
        if candidate.pattern_type == "hidden_driver"
    )
    existing_review_item_id = uuid4()
    prior = PreviousCandidate(
        id=original.id,
        pattern_type=original.pattern_type,
        canonical_key=original.canonical_key,
        status="weakened",
        score=original.score,
        version=original.version,
        first_seen_at=original.first_seen_at,
        last_seen_at=original.last_seen_at,
        last_source_version=2,
        rejected_at=None,
        rejected_source_version=None,
        review_weight=0.5,
        review_item_id=existing_review_item_id,
        payload={
            "support_clusters": original.support_clusters,
            "structure": original.structure.model_dump(mode="json"),
        },
    )
    weighted = service.construct_candidates(
        user_id=USER_ID,
        basis=basis,
        signals=signals,
        previous_candidates=[prior],
    )
    weakened = next(
        candidate
        for candidate in weighted.candidates
        if candidate.id == original.id
    )

    assert weakened.review_weight == 0.5
    assert weakened.review_item_id == existing_review_item_id
    assert weakened.score < original.score
    assert all(
        link.evidence_weight == pytest.approx(
            next(signal.confidence for signal in signals if signal.id == link.signal_id)
            * 0.5
        )
        for link in weighted.evidence
        if link.candidate_id == weakened.id
    )
    reviews = service._pattern_review_rows(
        user_id=USER_ID,
        source_version=3,
        candidates=[weakened],
        signals={signal.id: signal for signal in signals},
    )
    assert reviews[0]["id"] == str(existing_review_item_id)
