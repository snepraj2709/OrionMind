from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.modules.jobs.service import JobService
from app.modules.jobs.types import JobClaim
from app.modules.reflection_engine.provider import (
    OpenAIReflectionProvider,
    ReflectionProviderResponseError,
    ReflectionProviderUnavailableError,
)
from app.modules.reflection_engine.repository import StaleSynthesisClaimError
from app.modules.reflection_engine.schemas import (
    AnalysisBasis,
    CandidateSignal,
    ConstructedCandidate,
    HiddenDriverScoreComponents,
    HiddenDriverStructure,
    InnerTensionStructure,
    ReflectionCriticOutput,
    ReflectionSynthesisOutput,
    TensionScoreComponents,
)
from app.modules.reflection_engine.service import (
    ReflectionEngineService,
    _critic_allows_publication,
    _select_synthesis_candidates,
    _select_snapshot_candidates,
    critic_required,
)
from app.shared.security.encryption import AesGcmContentCipher


USER_ID = UUID("a1111111-1111-4111-8111-111111111111")


def cipher() -> AesGcmContentCipher:
    return AesGcmContentCipher(
        encryption_keys={"entry-key": b"e" * 32},
        active_encryption_key_id="entry-key",
        fingerprint_keys={"fingerprint-key": b"f" * 32},
        active_fingerprint_key_id="fingerprint-key",
    )


def hidden_candidate(*, score: float, contradiction: float = 0.0) -> ConstructedCandidate:
    signal_id = uuid4()
    return ConstructedCandidate(
        id=uuid4(),
        pattern_type="hidden_driver",
        canonical_key="a" * 64,
        status="candidate",
        score=score,
        score_components=HiddenDriverScoreComponents(
            recurrence=1,
            temporal_spread=1,
            context_diversity=1,
            evidence_strength=1,
            signal_type_diversity=1,
            stability=0.5,
            contradiction=contradiction,
            duplication=0,
            deterministic_score_before_stability=score,
        ),
        structure=HiddenDriverStructure(
            canonical_need="competence",
            statement="A possible pattern across your entries involves competence.",
            underlying_need="competence",
            supporting_entries=5,
            distinct_dates=5,
            distinct_signal_types=3,
        ),
        support_signal_ids=[signal_id],
        counter_signal_ids=[],
        support_clusters=[str(signal_id)],
        publication_gate_passed=True,
        confidence_label="emerging",
        first_seen_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        version=1,
        rejected_at=None,
        rejected_source_version=None,
    )


def tension_candidate(*, key: str, score: float) -> ConstructedCandidate:
    left_id = uuid4()
    right_id = uuid4()
    return ConstructedCandidate(
        id=uuid4(),
        pattern_type="inner_tension",
        canonical_key=key * 64,
        status="published",
        score=score,
        score_components=TensionScoreComponents(
            left_support=1,
            right_support=1,
            direct_conflict=1,
            temporal_alternation=1,
            context_diversity=1,
            evidence_strength=1,
            stability=0.5,
            contradiction=0,
            duplication=0,
            deterministic_score_before_stability=score,
        ),
        structure=InnerTensionStructure(
            left_need="autonomy",
            right_need="belonging",
            left_statement="Some entries support autonomy.",
            right_statement="Some entries support belonging.",
            integration="You may be trying to hold autonomy and belonging together.",
            left_support_signal_ids=[left_id],
            right_support_signal_ids=[right_id],
            left_supporting_entries=2,
            right_supporting_entries=2,
            distinct_dates=2,
        ),
        support_signal_ids=[left_id, right_id],
        counter_signal_ids=[],
        support_clusters=[str(left_id), str(right_id)],
        publication_gate_passed=True,
        confidence_label="emerging",
        first_seen_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        version=1,
        rejected_at=None,
        rejected_source_version=None,
    )


@pytest.mark.parametrize(
    ("score", "contradiction", "expected"),
    [
        (0.63, 0.00, True),
        (0.73, 0.00, True),
        (0.62999, 0.00, False),
        (0.73001, 0.00, False),
        (0.90, 0.19999, False),
        (0.90, 0.20, True),
    ],
)
def test_critic_activation_boundaries(
    score: float,
    contradiction: float,
    expected: bool,
) -> None:
    assert critic_required(
        hidden_candidate(score=score, contradiction=contradiction)
    ) is expected


def test_critic_is_publish_or_discard_only_and_cannot_repair_output() -> None:
    publish = ReflectionCriticOutput(
        entailed=True,
        overreaches=False,
        contradictory_evidence_ignored=False,
        diagnostic_language=False,
        evidence_diversity_adequate=True,
        recommended_action="publish",
    )
    assert _critic_allows_publication(publish) is True
    assert _critic_allows_publication(
        publish.model_copy(update={"recommended_action": "discard"})
    ) is False
    assert _critic_allows_publication(
        publish.model_copy(update={"overreaches": True})
    ) is False
    with pytest.raises(ValidationError):
        ReflectionCriticOutput.model_validate(
            {**publish.model_dump(), "score": 1, "replacement_evidence": [str(uuid4())]}
        )


class Calls:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[dict[str, object]] = []

    def parse(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(status="completed", output_parsed=self.outcomes.pop(0))


class Client:
    def __init__(self, calls: Calls) -> None:
        self.responses = calls
        self.options: list[dict[str, object]] = []

    def with_options(self, **kwargs):
        self.options.append(kwargs)
        return self


def test_terra_and_sol_use_exact_responses_shape_without_provider_storage() -> None:
    synthesis = ReflectionSynthesisOutput(
        hidden_drivers=[], recurring_loops=[], inner_tensions=[], abstentions=[]
    )
    critique = ReflectionCriticOutput(
        entailed=True,
        overreaches=False,
        contradictory_evidence_ignored=False,
        diagnostic_language=False,
        evidence_diversity_adequate=True,
        recommended_action="publish",
    )
    calls = Calls([synthesis, critique])
    client = Client(calls)
    provider = OpenAIReflectionProvider(
        client,
        synthesis_model="gpt-5.6-terra",
        critic_model="gpt-5.6-sol",
        connect_timeout=1,
        response_timeout=2,
        total_timeout=10,
    )
    provider.synthesize(payload="SYNTHESIS_INPUT\n{}", safety_identifier="a" * 64)
    provider.critique(payload="CRITIC_INPUT\n{}", safety_identifier="a" * 64)
    assert [item["model"] for item in calls.requests] == [
        "gpt-5.6-terra",
        "gpt-5.6-sol",
    ]
    assert [item["text_format"] for item in calls.requests] == [
        ReflectionSynthesisOutput,
        ReflectionCriticOutput,
    ]
    assert all(item["store"] is False for item in calls.requests)
    assert all(item["truncation"] == "disabled" for item in calls.requests)
    assert all(item["safety_identifier"] == "a" * 64 for item in calls.requests)
    assert all("tools" not in item for item in calls.requests)
    assert all(options["max_retries"] == 0 for options in client.options)


class Repository:
    def __init__(self, raw: dict[str, object]) -> None:
        self.raw = raw
        self.applied: dict[str, object] | None = None
        self.shadow: dict[str, object] | None = None

    def load_synthesis_basis(self, _session, **_kwargs) -> dict[str, object]:
        return self.raw

    def apply_snapshot(self, _session, **kwargs):
        self.applied = kwargs
        return UUID(str(kwargs["snapshot"]["id"]))

    def complete_shadow(self, _session, **kwargs):
        self.shadow = kwargs
        return kwargs["claim"].job_id


class UnitOfWork:
    @contextmanager
    def for_worker(self):
        yield SimpleNamespace(session=object())


class JobRepository:
    def __init__(self, claim: JobClaim) -> None:
        self.current_claim = claim
        self.claimed = False
        self.failures: list[tuple[str, bool]] = []
        self.scheduler_calls: list[datetime] = []

    def claim(self, _session, *, worker_id: str):
        assert worker_id == "reflection-worker"
        if self.claimed:
            return None
        self.claimed = True
        return self.current_claim

    def renew(self, _session, *, claim: JobClaim, worker_id: str) -> bool:
        return claim == self.current_claim and worker_id == "reflection-worker"

    def fail(
        self,
        _session,
        *,
        claim: JobClaim,
        worker_id: str,
        error_code: str,
        retryable: bool,
    ):
        assert claim == self.current_claim and worker_id == "reflection-worker"
        self.failures.append((error_code, retryable))
        return "pending" if retryable else "failed"

    def schedule_reflections(
        self, _session, *, now: datetime, execution_mode: str, user_ids
    ) -> int:
        assert execution_mode == "publish"
        assert set(user_ids) == {USER_ID}
        self.scheduler_calls.append(now)
        return 2


class ReflectionRunner:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def run_synthesis_job(self, **_kwargs) -> UUID:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return uuid4()


def job_claim() -> JobClaim:
    return JobClaim(
        job_id=uuid4(),
        user_id=USER_ID,
        entry_id=None,
        job_type="reflection_synthesis",
        execution_mode="publish",
        source_version="10",
        claim_token=uuid4(),
        attempts=1,
    )


def test_scheduler_flag_and_synthesis_dispatch_stay_in_worker_service() -> None:
    claim = job_claim()
    repository = JobRepository(claim)
    runner = ReflectionRunner()
    service = JobService(
        repository=repository,
        processing=object(),  # type: ignore[arg-type]
        reflection=runner,  # type: ignore[arg-type]
        cipher=cipher(),
        reflection_engine_enabled=True,
        reflection_scheduler_enabled=True,
        reflection_rollout_mode="publish",
        reflection_rollout_user_ids={USER_ID},
        heartbeat_interval_seconds=0.01,
    )
    now = datetime(2026, 7, 21, 12, 30, tzinfo=timezone.utc)
    assert service.schedule_reflections(uow=UnitOfWork(), now=now) == 2
    assert repository.scheduler_calls == [now]
    assert service.run_one(
        worker_id="reflection-worker", uow=UnitOfWork()
    ) is True
    assert runner.calls == 1
    assert repository.failures == []

    disabled_repository = JobRepository(job_claim())
    disabled = JobService(
        repository=disabled_repository,
        processing=object(),  # type: ignore[arg-type]
        cipher=cipher(),
    )
    assert disabled.schedule_reflections(uow=UnitOfWork(), now=now) == 0
    assert disabled_repository.scheduler_calls == []


@pytest.mark.parametrize(
    ("rollout_mode", "rollout_users"),
    [
        ("shadow", {USER_ID}),
        ("publish", {UUID("a2222222-2222-4222-8222-222222222222")}),
    ],
)
def test_synthesis_claims_fail_closed_when_rollout_no_longer_matches(
    rollout_mode: str,
    rollout_users: set[UUID],
) -> None:
    repository = JobRepository(job_claim())
    runner = ReflectionRunner()
    service = JobService(
        repository=repository,
        processing=object(),  # type: ignore[arg-type]
        reflection=runner,  # type: ignore[arg-type]
        cipher=cipher(),
        reflection_engine_enabled=True,
        reflection_rollout_mode=rollout_mode,  # type: ignore[arg-type]
        reflection_rollout_user_ids=rollout_users,
    )
    assert service.run_one(
        worker_id="reflection-worker", uow=UnitOfWork()
    ) is True
    assert runner.calls == 0
    assert repository.failures == [("REFLECTION_ROLLOUT_BLOCKED", False)]


class RateLimited(Exception):
    status_code = 429


@pytest.mark.parametrize(
    ("error", "expected_failure"),
    [
        (
            ReflectionProviderUnavailableError("secret provider body"),
            ("REFLECTION_PROVIDER_UNAVAILABLE", True),
        ),
        (
            ReflectionProviderResponseError("secret invalid output"),
            ("INVALID_SYNTHESIS", False),
        ),
        (StaleSynthesisClaimError("lost claim"), None),
    ],
)
def test_synthesis_retry_terminal_and_stale_claim_classification(
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    expected_failure: tuple[str, bool] | None,
) -> None:
    if isinstance(error, ReflectionProviderUnavailableError):
        try:
            raise RateLimited("secret transport response")
        except RateLimited as cause:
            error.__cause__ = cause
    claim = job_claim()
    repository = JobRepository(claim)
    service = JobService(
        repository=repository,
        processing=object(),  # type: ignore[arg-type]
        reflection=ReflectionRunner(error),  # type: ignore[arg-type]
        cipher=cipher(),
        reflection_engine_enabled=True,
        reflection_rollout_mode="publish",
        reflection_rollout_user_ids={USER_ID},
        heartbeat_interval_seconds=0.01,
    )
    assert service.run_one(
        worker_id="reflection-worker", uow=UnitOfWork()
    ) is True
    assert repository.failures == ([] if expected_failure is None else [expected_failure])
    assert "secret" not in caplog.text


class SynthesisProvider:
    def __init__(self, *, unsafe: bool = False, fabricated: bool = False) -> None:
        self.unsafe = unsafe
        self.fabricated = fabricated
        self.synthesis_payloads: list[str] = []
        self.critic_payloads: list[str] = []

    def synthesize(self, *, payload: str, safety_identifier: str):
        assert len(safety_identifier) == 64
        self.synthesis_payloads.append(payload)
        decoded = json.loads(payload.split("\n", 1)[1])
        candidate = decoded["candidates"][0]
        evidence = [
            {
                "signal_id": item["signal_id"],
                "evidence_role": item["evidence_role"],
            }
            for item in candidate["evidence"]
        ]
        if self.fabricated:
            evidence = [
                {"signal_id": str(uuid4()), "evidence_role": "supporting"}
            ]
        statement = (
            "You are always driven by competence."
            if self.unsafe
            else "A possible pattern across your entries may involve competence."
        )
        return {
            "hidden_drivers": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "canonical_need": "competence",
                    "statement": statement,
                    "underlying_need": "competence",
                    "evidence": evidence,
                }
            ],
            "recurring_loops": [],
            "inner_tensions": [],
            "abstentions": [],
        }

    def critique(self, *, payload: str, safety_identifier: str):
        self.critic_payloads.append(payload)
        return ReflectionCriticOutput(
            entailed=True,
            overreaches=False,
            contradictory_evidence_ignored=False,
            diagnostic_language=False,
            evidence_diversity_adequate=True,
            recommended_action="publish",
        )


def synthesis_basis(*, contradictory: bool = False) -> dict[str, object]:
    service_cipher = cipher()
    source_version = 10
    basis_end = date(2026, 6, 1)
    signals: list[dict[str, object]] = []
    signal_types = ("desire", "action", "self_statement")
    themes = ("personal_growth", "career", "health", "family_friends")
    for index in range(10):
        entry_id = uuid4()
        signal_id = uuid4()
        analysis_id = uuid4()
        entry_text = f"Private person {index} chose focused work."
        quote = "chose focused work"
        start = entry_text.index(quote)
        entry_date = basis_end - timedelta(days=(9 - index) * 5)
        counter = contradictory and index < 3
        signals.append(
            {
                "id": str(signal_id),
                "user_id": str(USER_ID),
                "entry_id": str(entry_id),
                "entry_user_id": str(USER_ID),
                "analysis_id": str(analysis_id),
                "analysis_user_id": str(USER_ID),
                "analysis_entry_id": str(entry_id),
                "analysis_source_version": index + 1,
                "analysis_eligibility": "accepted",
                "entry_date": entry_date.isoformat(),
                "signal_type": signal_types[index % len(signal_types)],
                "normalized_label_fingerprint": f"{index + 1:064x}",
                "payload_envelope": service_cipher.encrypt_json(
                    {
                        "normalized_label": (
                            "no longer value competence" if counter else "focused work"
                        ),
                        "interpretation": (
                            "The entry no longer values competence."
                            if counter
                            else "The entry describes focused work."
                        ),
                        "source_quote": quote,
                    },
                    user_id=USER_ID,
                    record_id=signal_id,
                    purpose="entry_signal_payload",
                ),
                "entry_content_envelope": service_cipher.encrypt(
                    entry_text,
                    user_id=USER_ID,
                    record_id=entry_id,
                ),
                "themes": [themes[index % len(themes)]],
                "need_tags": ["competence"],
                "loop_role": None,
                "confidence": 0.95,
                "source_start": start,
                "source_end": start + len(quote),
                "occurred_on": entry_date.isoformat(),
                "duplicate_cluster_key": None,
            }
        )
    return {
        "source_version": source_version,
        "basis_start": (basis_end - timedelta(days=89)).isoformat(),
        "basis_end": basis_end.isoformat(),
        "valid_entry_count": 10,
        "excluded_entry_count": 2,
        "distinct_entry_dates": 10,
        "reflective_word_count": 1000,
        "signals": signals,
        "candidates": [],
        "next_snapshot_version": 1,
        "feedback_qualifications": {},
    }


@pytest.mark.parametrize(
    ("unsafe", "fabricated", "available"),
    [(False, False, True), (True, False, False), (False, True, False)],
)
def test_synthesis_uses_minimum_context_and_discards_invalid_output(
    caplog: pytest.LogCaptureFixture,
    unsafe: bool,
    fabricated: bool,
    available: bool,
) -> None:
    raw = synthesis_basis()
    repository = Repository(raw)
    provider = SynthesisProvider(unsafe=unsafe, fabricated=fabricated)
    service = ReflectionEngineService(
        repository=repository,
        provider=provider,
        cipher=cipher(),
    )
    claim = JobClaim(
        job_id=uuid4(),
        user_id=USER_ID,
        entry_id=None,
        job_type="reflection_synthesis",
        execution_mode="publish",
        source_version="10",
        claim_token=uuid4(),
        attempts=1,
    )
    service.run_synthesis_job(
        claim=claim,
        worker_id="reflection-worker",
        uow=UnitOfWork(),
    )
    assert repository.applied is not None
    assert len(provider.synthesis_payloads) == 1
    payload = provider.synthesis_payloads[0]
    assert "Private person" not in payload
    assert "chose focused work" not in payload
    assert "entry_text" not in payload
    assert "source_quote" not in payload
    assert len(provider.critic_payloads) == 0
    insights = repository.applied["insights"]
    hidden = [item for item in insights if item["pattern_type"] == "hidden_driver"]
    assert hidden[0]["status"] == ("available" if available else "insufficient_evidence")
    assert len([item for item in insights if item["pattern_type"] == "recurring_loop"]) == 1
    assert len([item for item in insights if item["pattern_type"] == "inner_tension"]) == 1
    assert len(repository.applied["snapshot_evidence"]) == (10 if available else 0)
    assert "Private person" not in caplog.text
    assert "chose focused work" not in caplog.text


def test_shadow_synthesis_runs_full_validation_without_applying_a_snapshot() -> None:
    repository = Repository(synthesis_basis())
    provider = SynthesisProvider()
    service = ReflectionEngineService(
        repository=repository,
        provider=provider,
        cipher=cipher(),
    )
    claim = JobClaim(
        job_id=uuid4(),
        user_id=USER_ID,
        entry_id=None,
        job_type="reflection_synthesis",
        execution_mode="shadow",
        source_version="10",
        claim_token=uuid4(),
        attempts=1,
    )

    assert service.run_synthesis_job(
        claim=claim,
        worker_id="reflection-worker",
        uow=UnitOfWork(),
    ) == claim.job_id
    assert len(provider.synthesis_payloads) == 1
    assert repository.applied is None
    assert repository.shadow is not None
    assert repository.shadow["candidate_count"] >= 1
    assert repository.shadow["selected_count"] == 1
    assert repository.shadow["provider_called"] is True


def test_snapshot_selection_supports_zero_one_and_multiple_inner_tensions() -> None:
    first = tension_candidate(key="b", score=0.80)
    second = tension_candidate(key="c", score=0.90)
    assert _select_snapshot_candidates([]) == []
    assert _select_snapshot_candidates([first]) == [first]
    assert _select_snapshot_candidates([first, second]) == [second, first]


def test_terra_input_is_bounded_to_reviewable_candidate_capacity() -> None:
    hidden = [hidden_candidate(score=0.95 - index / 100) for index in range(16)]
    tensions = [
        tension_candidate(key=str(index), score=0.95 - index / 100)
        for index in range(9)
    ]

    selected = _select_synthesis_candidates([*reversed(hidden), *reversed(tensions)])

    selected_hidden = [item for item in selected if item.pattern_type == "hidden_driver"]
    selected_tensions = [item for item in selected if item.pattern_type == "inner_tension"]
    assert len(selected_hidden) == 15
    assert len(selected_tensions) == 8
    assert [item.score for item in selected_hidden] == pytest.approx(
        [0.95 - index / 100 for index in range(15)]
    )
    assert [item.score for item in selected_tensions] == pytest.approx(
        [0.95 - index / 100 for index in range(8)]
    )


def test_contradiction_boundary_invokes_sol_once_after_local_validation() -> None:
    raw = synthesis_basis(contradictory=True)
    repository = Repository(raw)
    provider = SynthesisProvider()
    service = ReflectionEngineService(
        repository=repository,
        provider=provider,
        cipher=cipher(),
    )
    service.run_synthesis_job(
        claim=JobClaim(
            job_id=uuid4(),
            user_id=USER_ID,
            entry_id=None,
            job_type="reflection_synthesis",
            execution_mode="publish",
            source_version="10",
            claim_token=uuid4(),
            attempts=1,
        ),
        worker_id="reflection-worker",
        uow=UnitOfWork(),
    )
    assert len(provider.synthesis_payloads) == 1
    assert len(provider.critic_payloads) == 1
    critic_input = json.loads(provider.critic_payloads[0].split("\n", 1)[1])
    assert critic_input["candidate"]["score_components"]["contradiction"] >= 0.20


@pytest.mark.parametrize("tension_count", [0, 1, 2])
def test_snapshot_rows_persist_zero_one_and_multiple_inner_tensions(
    tension_count: int,
) -> None:
    candidates = [
        tension_candidate(key=key, score=score)
        for key, score in (("b", 0.80), ("c", 0.90))[:tension_count]
    ]
    signal_rows: dict[UUID, CandidateSignal] = {}
    for candidate_index, candidate in enumerate(candidates):
        for signal_index, signal_id in enumerate(candidate.support_signal_ids):
            entry_id = uuid4()
            need = "autonomy" if signal_index == 0 else "belonging"
            signal_rows[signal_id] = CandidateSignal(
                id=signal_id,
                user_id=USER_ID,
                entry_id=entry_id,
                entry_user_id=USER_ID,
                analysis_id=uuid4(),
                analysis_user_id=USER_ID,
                analysis_entry_id=entry_id,
                analysis_source_version=candidate_index * 2 + signal_index + 1,
                analysis_eligibility="accepted",
                entry_date=date(2026, 5, 1 + candidate_index * 2 + signal_index),
                signal_type="conflict",
                normalized_label_fingerprint=f"{candidate_index * 2 + signal_index + 1:064x}",
                normalized_label="competing needs",
                interpretation="The entry describes competing needs.",
                source_quote="needs",
                entry_text="needs",
                themes=["personal_growth"],
                need_tags=[need],
                loop_role=None,
                confidence=0.9,
                source_start=0,
                source_end=5,
                occurred_on=date(2026, 5, 1 + candidate_index * 2 + signal_index),
                duplicate_cluster_key=None,
            )
    service = ReflectionEngineService(repository=object(), cipher=cipher())  # type: ignore[arg-type]
    _, insights, evidence = service._snapshot_rows(
        user_id=USER_ID,
        raw={"next_snapshot_version": 1, "excluded_entry_count": 0},
        basis=AnalysisBasis(
            source_version=10,
            basis_start=date(2026, 3, 4),
            basis_end=date(2026, 6, 1),
            valid_entry_count=10,
            distinct_entry_dates=10,
            reflective_word_count=1000,
        ),
        candidates=_select_snapshot_candidates(candidates),
        signals=signal_rows,
    )
    inner = [item for item in insights if item["pattern_type"] == "inner_tension"]
    if tension_count == 0:
        assert inner == [
            {
                "id": inner[0]["id"],
                "pattern_type": "inner_tension",
                "ordinal": 0,
                "status": "insufficient_evidence",
                "reason_code": "BOTH_SIDES_NOT_SUPPORTED",
            }
        ]
        assert evidence == []
    else:
        assert [item["status"] for item in inner] == ["available"] * tension_count
        assert [item["ordinal"] for item in inner] == list(range(tension_count))
        assert len(evidence) == tension_count * 2
