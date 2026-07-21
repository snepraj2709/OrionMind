from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.modules.reflection_engine.evidence import (
    EvidenceValidator,
    transition_key,
)
from app.modules.reflection_engine.repository import ReflectionEngineRepository
from app.modules.reflection_engine.schemas import (
    AnalysisBasis,
    CandidateSignal,
    ConstructedCandidate,
    HiddenDriverScoreComponents,
    HiddenDriverStructure,
    InnerTensionStructure,
    LoopScoreComponents,
    LoopStepStructure,
    PreviousCandidate,
    RecurringLoopStructure,
    TensionScoreComponents,
)
from app.modules.reflection_engine.scoring import (
    candidate_stability,
    clamp01,
    context_diversity,
    contradiction,
    duplication,
    evidence_strength,
    hidden_driver_publishable,
    inner_tension_publishable,
    overall_basis_eligible,
    progress,
    recurring_loop_publishable,
    score_hidden_driver,
    score_inner_tension,
    score_recurring_loop,
    temporal_spread,
)
from app.modules.reflection_engine.service import ReflectionEngineService
from app.shared.security.encryption import AesGcmContentCipher


USER = UUID("a1111111-1111-4111-8111-111111111111")
OTHER_USER = UUID("a2222222-2222-4222-8222-222222222222")
BASE_DATE = date(2026, 7, 1)
ZERO_HIDDEN_COMPONENTS = HiddenDriverScoreComponents(
    recurrence=0,
    temporal_spread=0,
    context_diversity=0,
    evidence_strength=0,
    signal_type_diversity=0,
    stability=0,
    contradiction=0,
    duplication=0,
    deterministic_score_before_stability=0,
)


def cipher() -> AesGcmContentCipher:
    return AesGcmContentCipher(
        encryption_keys={"entry-key": b"e" * 32},
        active_encryption_key_id="entry-key",
        fingerprint_keys={"fingerprint-key": b"f" * 32},
        active_fingerprint_key_id="fingerprint-key",
    )


def service() -> ReflectionEngineService:
    return ReflectionEngineService(
        repository=ReflectionEngineRepository(),
        cipher=cipher(),
    )


def basis(source_version: int = 20) -> AnalysisBasis:
    return AnalysisBasis(
        source_version=source_version,
        basis_start=BASE_DATE,
        basis_end=BASE_DATE + timedelta(days=89),
        valid_entry_count=5,
        distinct_entry_dates=5,
        reflective_word_count=500,
    )


def signal(
    index: int,
    *,
    user_id: UUID = USER,
    entry_id: UUID | None = None,
    entry_date: date | None = None,
    signal_type: str = "self_statement",
    need_tags: list[str] | None = None,
    loop_role: str | None = "interpretation",
    label_fingerprint: str | None = None,
    duplicate_cluster_key: str | None = None,
    confidence: float = 0.95,
    analysis_source_version: int | None = None,
    entry_text: str = "I value meaningful work.",
    source_quote: str = "I value meaningful work.",
    source_start: int = 0,
    source_end: int | None = None,
) -> CandidateSignal:
    owner_entry = entry_id or UUID(int=10_000 + index)
    occurred = entry_date or BASE_DATE + timedelta(days=index * 8)
    return CandidateSignal.model_validate(
        {
            "id": UUID(int=20_000 + index),
            "user_id": user_id,
            "entry_id": owner_entry,
            "entry_user_id": user_id,
            "analysis_id": UUID(int=30_000 + index),
            "analysis_user_id": user_id,
            "analysis_entry_id": owner_entry,
            "analysis_source_version": analysis_source_version or index + 1,
            "analysis_eligibility": "accepted",
            "entry_date": occurred,
            "signal_type": signal_type,
            "normalized_label_fingerprint": label_fingerprint or f"{index:064x}",
            "normalized_label": "meaningful work",
            "interpretation": "A possible supported interpretation.",
            "source_quote": source_quote,
            "entry_text": entry_text,
            "themes": [
                ("career", "personal_growth", "family_friends", "home_lifestyle")[
                    index % 4
                ]
            ],
            "need_tags": need_tags or ["competence"],
            "loop_role": loop_role,
            "confidence": confidence,
            "source_start": source_start,
            "source_end": source_end if source_end is not None else len(source_quote),
            "occurred_on": occurred,
            "duplicate_cluster_key": duplicate_cluster_key,
        }
    )


@pytest.mark.parametrize(
    ("value", "minimum", "strong", "expected"),
    [
        (0, 3, 10, 0),
        (1, 3, 10, 0.2),
        (3, 3, 10, 0.6),
        (6.5, 3, 10, 0.8),
        (10, 3, 10, 1),
        (20, 3, 10, 1),
        (2, 2, 2, 1),
    ],
)
def test_clamp_and_progress_exact_contract_boundaries(
    value: float, minimum: float, strong: float, expected: float
) -> None:
    assert progress(value, minimum, strong) == pytest.approx(expected)
    assert clamp01(-1) == 0
    assert clamp01(2) == 1


def test_common_formula_zero_boundary_and_saturation() -> None:
    assert temporal_spread(0, 0) == 0
    assert temporal_spread(2, 7) == pytest.approx(0.6)
    assert temporal_spread(6, 45) == 1
    assert context_diversity([]) == 0
    assert context_diversity(["career"]) == pytest.approx(0.3)
    assert context_diversity(["career", "money"]) == pytest.approx(0.6)
    assert context_diversity(["career", "money", "health", "love"]) == 1
    assert evidence_strength([]) == 0
    assert evidence_strength([0.2, 0.8]) == pytest.approx(0.5)
    assert evidence_strength([1, 1]) == 1
    assert contradiction([], []) == 0
    assert contradiction([0.75], [0.25]) == pytest.approx(0.25)
    assert contradiction([], [1]) == 1
    assert duplication(0, 0) == 1
    assert duplication(2, 4) == pytest.approx(0.5)
    assert duplication(4, 4) == 0


def test_stability_exact_new_existing_and_saturation_contract() -> None:
    assert candidate_stability(
        previous_support_clusters=None,
        current_support_clusters={"a"},
        previous_score=None,
        deterministic_score_before_stability=0.2,
    ) == 0.5
    assert candidate_stability(
        previous_support_clusters={"a", "b"},
        current_support_clusters={"b", "c"},
        previous_score=0.8,
        deterministic_score_before_stability=0.6,
    ) == pytest.approx(0.5 * (1 / 3) + 0.5 * 0.8)
    assert candidate_stability(
        previous_support_clusters={"a"},
        current_support_clusters={"a"},
        previous_score=0.7,
        deterministic_score_before_stability=0.7,
    ) == 1


def test_exact_score_weights_and_penalties() -> None:
    hidden, hidden_parts = score_hidden_driver(
        supporting_entries=3,
        distinct_dates=2,
        span_days=7,
        theme_keys={"career", "money"},
        support_confidences=[1, 1, 1],
        counter_confidences=[],
        distinct_signal_types=2,
        unique_duplicate_clusters=3,
        raw_support_signal_count=3,
        current_support_clusters={"a", "b", "c"},
    )
    expected_hidden = 0.30 * 0.6 + 0.20 * 0.6 + 0.15 * 0.6 + 0.15 + 0.10 * 0.6 + 0.10 * 0.5
    assert hidden == pytest.approx(expected_hidden)
    assert hidden_parts.stability == 0.5

    loop, _ = score_recurring_loop(
        observed_chains=3,
        supported_transitions=4,
        distinct_dates=2,
        span_days=7,
        theme_keys={"career", "money"},
        support_confidences=[1, 1, 1],
        counter_confidences=[],
        unique_duplicate_clusters=3,
        raw_support_signal_count=3,
        current_support_clusters={"a", "b", "c"},
    )
    expected_loop = 0.25 * 0.6 + 0.20 * 0.6 + 0.15 * 0.6 + 0.10 * 0.6 + 0.15 + 0.15 * 0.5
    assert loop == pytest.approx(expected_loop)

    tension, _ = score_inner_tension(
        left_supporting_entries=2,
        right_supporting_entries=2,
        left_mean_confidence=1,
        right_mean_confidence=1,
        direct_conflict_entry_count=1,
        need_side_switches=1,
        theme_keys={"career", "money"},
        support_confidences=[1, 1, 1, 1],
        counter_confidences=[],
        unique_duplicate_clusters=4,
        raw_support_signal_count=4,
        current_support_clusters={"a", "b", "c", "d"},
    )
    expected_tension = 0.20 * 0.72 + 0.20 * 0.72 + 0.15 * 0.6 + 0.10 * 0.6 + 0.10 * 0.6 + 0.10 + 0.15 * 0.5
    assert tension == pytest.approx(expected_tension)


def test_score_saturation_duplication_contradiction_and_strongest_removal() -> None:
    arguments = dict(
        supporting_entries=10,
        distinct_dates=6,
        span_days=45,
        theme_keys={"a", "b", "c", "d"},
        distinct_signal_types=5,
        unique_duplicate_clusters=10,
        raw_support_signal_count=10,
        current_support_clusters={str(index) for index in range(10)},
    )
    strong, _ = score_hidden_driver(
        **arguments,
        support_confidences=[1] * 10,
        counter_confidences=[],
    )
    contradicted, _ = score_hidden_driver(
        **arguments,
        support_confidences=[1] * 10,
        counter_confidences=[1] * 10,
    )
    strongest_present, _ = score_hidden_driver(
        **{**arguments, "supporting_entries": 3, "unique_duplicate_clusters": 3},
        support_confidences=[1, 0.5, 0.5],
        counter_confidences=[],
    )
    without_strongest, _ = score_hidden_driver(
        **{**arguments, "supporting_entries": 2, "unique_duplicate_clusters": 2},
        support_confidences=[0.5, 0.5],
        counter_confidences=[],
    )
    duplicated, _ = score_hidden_driver(
        **{**arguments, "raw_support_signal_count": 20},
        support_confidences=[1] * 10,
        counter_confidences=[],
    )
    assert strong == pytest.approx(0.95)
    assert contradicted < strong
    assert without_strongest < strongest_present
    assert duplicated < strong


def test_publication_gates_are_exact_at_every_boundary() -> None:
    assert not overall_basis_eligible(
        valid_entry_count=2, distinct_entry_dates=2, reflective_word_count=200
    )
    assert not overall_basis_eligible(
        valid_entry_count=3, distinct_entry_dates=1, reflective_word_count=200
    )
    assert not overall_basis_eligible(
        valid_entry_count=3, distinct_entry_dates=2, reflective_word_count=199
    )
    assert overall_basis_eligible(
        valid_entry_count=3, distinct_entry_dates=2, reflective_word_count=200
    )
    assert hidden_driver_publishable(
        supporting_entries=3, distinct_dates=2, distinct_signal_types=2, score=0.68
    )
    assert not hidden_driver_publishable(
        supporting_entries=3, distinct_dates=2, distinct_signal_types=2, score=0.67999
    )
    assert recurring_loop_publishable(
        observed_chains=3,
        supporting_entries=3,
        supported_transitions=4,
        distinct_dates=2,
        score=0.72,
    )
    assert not recurring_loop_publishable(
        observed_chains=3,
        supporting_entries=3,
        supported_transitions=3,
        distinct_dates=2,
        score=1,
    )
    assert inner_tension_publishable(
        left_supporting_entries=2,
        right_supporting_entries=2,
        distinct_dates=2,
        score=0.70,
    )
    assert not inner_tension_publishable(
        left_supporting_entries=2,
        right_supporting_entries=2,
        distinct_dates=2,
        score=0.69999,
    )


def hidden_candidate(signals: list[CandidateSignal], *, statement: str | None = None) -> ConstructedCandidate:
    return ConstructedCandidate(
        id=uuid4(),
        pattern_type="hidden_driver",
        canonical_key="f" * 64,
        status="candidate",
        score=0.8,
        score_components=ZERO_HIDDEN_COMPONENTS,
        structure=HiddenDriverStructure(
            canonical_need="competence",
            statement=statement or "A possible pattern across your entries may involve competence.",
            underlying_need="competence",
            supporting_entries=len({item.entry_id for item in signals}),
            distinct_dates=len({item.entry_date for item in signals}),
            distinct_signal_types=len({item.signal_type for item in signals}),
        ),
        support_signal_ids=[item.id for item in signals],
        counter_signal_ids=[],
        support_clusters=[item.cluster_key for item in signals],
        publication_gate_passed=True,
        confidence_label="preliminary",
        first_seen_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        version=1,
        rejected_at=None,
        rejected_source_version=None,
    )


def test_signal_owner_offsets_quote_and_closed_catalog_validation() -> None:
    validator = EvidenceValidator()
    cross_owner = signal(1, user_id=OTHER_USER)
    assert "EVIDENCE_OWNER_MISMATCH" in validator.validate_signal(
        cross_owner, user_id=USER, basis_start=BASE_DATE, basis_end=BASE_DATE + timedelta(days=89)
    )
    wrong_entry = signal(7).model_copy(update={"analysis_entry_id": uuid4()})
    assert "EVIDENCE_ENTRY_MISMATCH" in validator.validate_signal(
        wrong_entry,
        user_id=USER,
        basis_start=BASE_DATE,
        basis_end=BASE_DATE + timedelta(days=89),
    )
    bad_offset = signal(2, source_end=100)
    assert "EVIDENCE_OFFSET_OUT_OF_BOUNDS" in validator.validate_signal(
        bad_offset, user_id=USER, basis_start=BASE_DATE, basis_end=BASE_DATE + timedelta(days=89)
    )
    bad_quote = signal(3, source_quote="not the original quote")
    assert "EVIDENCE_OFFSET_MISMATCH" in validator.validate_signal(
        bad_quote, user_id=USER, basis_start=BASE_DATE, basis_end=BASE_DATE + timedelta(days=89)
    )
    with pytest.raises(ValidationError):
        signal(4, loop_role="Interpretation")
    with pytest.raises(ValidationError):
        signal(5, signal_type="Belief")
    with pytest.raises(ValidationError):
        signal(6, need_tags=["Competence"])


def test_single_entry_dominance_duplicate_counter_and_unsafe_language_are_discarded() -> None:
    same_entry = UUID(int=500)
    signals = [
        signal(1, entry_id=same_entry, signal_type="belief"),
        signal(2, entry_id=same_entry, signal_type="emotion"),
        signal(3, signal_type="action"),
    ]
    candidate = hidden_candidate(signals, statement="You are always driven by competence.")
    reasons = EvidenceValidator().validate_candidate(
        candidate,
        user_id=USER,
        signals={item.id: item for item in signals},
        basis_start=BASE_DATE,
        basis_end=BASE_DATE + timedelta(days=89),
        expected_counter_signal_ids=[uuid4()],
    )
    assert "SINGLE_ENTRY_DOMINANCE" in reasons
    assert "COUNTEREVIDENCE_OMITTED" in reasons
    assert "UNSAFE_IDENTITY_LANGUAGE" in reasons
    diagnostic = hidden_candidate(
        signals,
        statement="A possible pattern across your entries may be an anxiety disorder.",
    )
    diagnostic_reasons = EvidenceValidator().validate_candidate(
        diagnostic,
        user_id=USER,
        signals={item.id: item for item in signals},
        basis_start=BASE_DATE,
        basis_end=BASE_DATE + timedelta(days=89),
    )
    assert "UNSAFE_DIAGNOSTIC_LANGUAGE" in diagnostic_reasons


def test_loop_requires_supported_adjacent_and_closing_transitions() -> None:
    roles = ["trigger", "interpretation", "action", "reinforcement"]
    signals = [
        signal(
            index,
            loop_role=role,
            label_fingerprint=f"{index:064x}",
            entry_date=BASE_DATE + timedelta(days=index),
        )
        for index, role in enumerate(roles, 1)
    ]
    steps = [
        LoopStepStructure(
            loop_role=item.loop_role,
            normalized_label_fingerprint=item.normalized_label_fingerprint,
            support_signal_ids=[item.id],
        )
        for item in signals
    ]
    keys = [
        transition_key(
            left.loop_role,
            left.normalized_label_fingerprint,
            right.loop_role,
            right.normalized_label_fingerprint,
        )
        for left, right in zip(steps, [*steps[1:], steps[0]])
    ]
    candidate = ConstructedCandidate(
        id=uuid4(),
        pattern_type="recurring_loop",
        canonical_key="a" * 64,
        status="candidate",
        score=0.8,
        score_components=LoopScoreComponents(
            recurrence=0,
            transition_coverage=0,
            temporal_spread=0,
            context_diversity=0,
            evidence_strength=0,
            stability=0,
            contradiction=0,
            duplication=0,
            deterministic_score_before_stability=0,
        ),
        structure=RecurringLoopStructure(
            title="A possible recurring loop",
            description="A possible recurring loop across your entries.",
            steps=steps,
            transition_keys=keys,
            observed_chains=3,
            supporting_entries=4,
            supported_transitions=4,
            distinct_dates=4,
        ),
        support_signal_ids=[item.id for item in signals],
        counter_signal_ids=[],
        support_clusters=[item.cluster_key for item in signals],
        publication_gate_passed=True,
        confidence_label="preliminary",
        first_seen_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        version=1,
        rejected_at=None,
        rejected_source_version=None,
    )
    validator = EvidenceValidator()
    complete = {key: (2, 2) for key in keys}
    assert validator.validate_candidate(
        candidate,
        user_id=USER,
        signals={item.id: item for item in signals},
        basis_start=BASE_DATE,
        basis_end=BASE_DATE + timedelta(days=89),
        transition_support=complete,
    ) == ()
    complete.pop(keys[-1])
    assert "LOOP_CLOSURE_UNSUPPORTED" in validator.validate_candidate(
        candidate,
        user_id=USER,
        signals={item.id: item for item in signals},
        basis_start=BASE_DATE,
        basis_end=BASE_DATE + timedelta(days=89),
        transition_support=complete,
    )
    complete = {key: (2, 2) for key in keys}
    complete.pop(keys[0])
    assert "LOOP_TRANSITION_UNSUPPORTED" in validator.validate_candidate(
        candidate,
        user_id=USER,
        signals={item.id: item for item in signals},
        basis_start=BASE_DATE,
        basis_end=BASE_DATE + timedelta(days=89),
        transition_support=complete,
    )


def test_loop_construction_groups_semantically_equal_roles_across_varied_labels() -> None:
    signals: list[CandidateSignal] = []
    roles = ("trigger", "interpretation", "avoidance", "reinforcement", "trigger")
    for entry_index in range(10):
        entry_id = UUID(int=90_000 + entry_index)
        entry_date = BASE_DATE + timedelta(days=entry_index * 5)
        for role_index, role in enumerate(roles):
            index = 1_000 + entry_index * len(roles) + role_index
            signals.append(
                signal(
                    index,
                    entry_id=entry_id,
                    entry_date=entry_date,
                    loop_role=role,
                    label_fingerprint=f"{index:064x}",
                    source_start=role_index * 6,
                    source_end=role_index * 6 + 5,
                    source_quote="cycle",
                    entry_text="cycle " * 30,
                )
            )

    loops = [
        item
        for item in service().construct_candidates(
            user_id=USER,
            basis=basis(source_version=100).model_copy(
                update={"valid_entry_count": 10, "distinct_entry_dates": 10}
            ),
            signals=signals,
        ).candidates
        if item.pattern_type == "recurring_loop"
    ]

    assert loops
    assert any(item.publication_gate_passed for item in loops)


def test_tension_requires_both_sides_and_integration_honoring_both() -> None:
    left = [signal(1, need_tags=["autonomy"]), signal(2, need_tags=["autonomy"])]
    right = [signal(3, need_tags=["competence"]), signal(4, need_tags=["competence"])]
    signals = [*left, *right]
    candidate = ConstructedCandidate(
        id=uuid4(),
        pattern_type="inner_tension",
        canonical_key="b" * 64,
        status="candidate",
        score=0.8,
        score_components=TensionScoreComponents(
            left_support=0,
            right_support=0,
            direct_conflict=0,
            temporal_alternation=0,
            context_diversity=0,
            evidence_strength=0,
            stability=0,
            contradiction=0,
            duplication=0,
            deterministic_score_before_stability=0,
        ),
        structure=InnerTensionStructure(
            left_need="autonomy",
            right_need="competence",
            left_statement="Some entries support autonomy.",
            right_statement="Some entries support competence.",
            integration="You may be trying to hold autonomy and competence together.",
            left_support_signal_ids=[item.id for item in left],
            right_support_signal_ids=[item.id for item in right],
            left_supporting_entries=2,
            right_supporting_entries=2,
            distinct_dates=4,
        ),
        support_signal_ids=[item.id for item in signals],
        counter_signal_ids=[],
        support_clusters=[item.cluster_key for item in signals],
        publication_gate_passed=True,
        confidence_label="preliminary",
        first_seen_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        version=1,
        rejected_at=None,
        rejected_source_version=None,
    )
    validator = EvidenceValidator()
    assert validator.validate_candidate(
        candidate,
        user_id=USER,
        signals={item.id: item for item in signals},
        basis_start=BASE_DATE,
        basis_end=BASE_DATE + timedelta(days=89),
    ) == ()
    assert not validator.integration_honors_both_sides(
        "Eliminate autonomy and keep competence.",
        left_need="autonomy",
        right_need="competence",
    )
    with pytest.raises(ValidationError):
        invalid = candidate.model_dump(mode="json")
        invalid["structure"]["right_support_signal_ids"] = []
        ConstructedCandidate.model_validate(invalid)


def test_date_shuffling_lowers_tension_alternation_without_changing_need_recurrence() -> None:
    common_label = "9" * 64
    ordered = [
        signal(
            1,
            signal_type="action",
            need_tags=["autonomy"],
            loop_role="action",
            label_fingerprint=common_label,
            entry_date=BASE_DATE,
        ),
        signal(
            2,
            signal_type="avoidance",
            need_tags=["competence"],
            loop_role="avoidance",
            label_fingerprint=common_label,
            entry_date=BASE_DATE + timedelta(days=1),
        ),
        signal(
            3,
            signal_type="action",
            need_tags=["autonomy"],
            loop_role="action",
            label_fingerprint=common_label,
            entry_date=BASE_DATE + timedelta(days=2),
        ),
        signal(
            4,
            signal_type="avoidance",
            need_tags=["competence"],
            loop_role="avoidance",
            label_fingerprint=common_label,
            entry_date=BASE_DATE + timedelta(days=3),
        ),
    ]
    shuffled_dates = [
        BASE_DATE,
        BASE_DATE + timedelta(days=2),
        BASE_DATE + timedelta(days=1),
        BASE_DATE + timedelta(days=3),
    ]
    shuffled = [
        item.model_copy(update={"entry_date": new_date, "occurred_on": new_date})
        for item, new_date in zip(ordered, shuffled_dates, strict=True)
    ]
    engine = service()
    alternating = next(
        item
        for item in engine.construct_candidates(
            user_id=USER, basis=basis(), signals=ordered
        ).candidates
        if item.pattern_type == "inner_tension"
    )
    grouped = next(
        item
        for item in engine.construct_candidates(
            user_id=USER, basis=basis(), signals=shuffled
        ).candidates
        if item.pattern_type == "inner_tension"
    )
    assert (
        alternating.structure.left_supporting_entries
        == grouped.structure.left_supporting_entries
    )
    assert (
        alternating.structure.right_supporting_entries
        == grouped.structure.right_supporting_entries
    )
    assert (
        alternating.score_components.temporal_alternation
        > grouped.score_components.temporal_alternation
    )


def test_hidden_construction_is_owner_scoped_deterministic_and_collapses_duplicates() -> None:
    signal_types = ["belief", "emotion", "action", "desire", "self_statement"]
    signals = [signal(index, signal_type=value) for index, value in enumerate(signal_types, 1)]
    signals[0] = signals[0].model_copy(update={"duplicate_cluster_key": "c" * 64})
    duplicate = signal(
        99,
        signal_type="belief",
        entry_date=BASE_DATE + timedelta(days=48),
        duplicate_cluster_key="c" * 64,
        label_fingerprint=signals[0].normalized_label_fingerprint,
    )
    first = service().construct_candidates(
        user_id=USER,
        basis=basis(),
        signals=[*signals, duplicate],
    )
    repeated = service().construct_candidates(
        user_id=USER,
        basis=basis(),
        signals=[*signals, duplicate],
    )
    other_owner_signals = [
        item.model_copy(
            update={
                "user_id": OTHER_USER,
                "entry_user_id": OTHER_USER,
                "analysis_user_id": OTHER_USER,
            }
        )
        for item in signals
    ]
    other = service().construct_candidates(
        user_id=OTHER_USER,
        basis=basis(),
        signals=other_owner_signals,
    )
    candidate = next(item for item in first.candidates if item.pattern_type == "hidden_driver")
    repeated_candidate = next(
        item for item in repeated.candidates if item.pattern_type == "hidden_driver"
    )
    other_candidate = next(item for item in other.candidates if item.pattern_type == "hidden_driver")
    assert candidate.id == repeated_candidate.id
    assert candidate.canonical_key == repeated_candidate.canonical_key
    assert len(candidate.support_signal_ids) == 5
    assert candidate.score_components.duplication == pytest.approx(1 - 5 / 6)
    assert candidate.canonical_key != other_candidate.canonical_key


def test_rejected_candidate_needs_three_new_entries_on_two_dates_and_full_gate() -> None:
    signals = [
        signal(index, signal_type=value, analysis_source_version=version)
        for index, (value, version) in enumerate(
            zip(
                ["belief", "emotion", "action", "desire", "self_statement"],
                [8, 9, 11, 12, 10],
                strict=True,
            ),
            1,
        )
    ]
    engine = service()
    initial = engine.construct_candidates(user_id=USER, basis=basis(12), signals=signals)
    built = next(item for item in initial.candidates if item.pattern_type == "hidden_driver")
    rejected = PreviousCandidate(
        id=built.id,
        pattern_type=built.pattern_type,
        canonical_key=built.canonical_key,
        status="rejected",
        score=built.score,
        version=1,
        first_seen_at=built.first_seen_at,
        last_seen_at=built.last_seen_at,
        last_source_version=10,
        rejected_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        rejected_source_version=10,
        payload={"support_clusters": built.support_clusters},
    )
    suppressed = engine.construct_candidates(
        user_id=USER,
        basis=basis(12),
        signals=signals,
        previous_candidates=[rejected],
    )
    assert next(item for item in suppressed.candidates if item.id == built.id).status == "rejected"
    reentry_signals = [
        item.model_copy(update={"analysis_source_version": 11 + index})
        if index < 3
        else item
        for index, item in enumerate(signals)
    ]
    reentered = engine.construct_candidates(
        user_id=USER,
        basis=basis(14),
        signals=reentry_signals,
        previous_candidates=[rejected],
    )
    result = next(item for item in reentered.candidates if item.id == built.id)
    assert result.publication_gate_passed is True
    assert result.status == "candidate"
    assert result.confidence_label == "preliminary"
