from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date, datetime, timezone
from types import TracebackType
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.review.repository import (
    ReviewItemNotFoundError,
    ReviewItemStaleError,
    ReviewRepositoryDataError,
)
from app.modules.review.schemas import (
    EntryInsightFeedback,
    EntryInsightReviewItem,
    PatternFeedback,
    PatternReviewItem,
    ReviewItem,
)
from app.modules.review.service import ReviewService
from app.modules.reflections.types import RecalculationRequest
from app.modules.review.types import SavedReviewFeedback, feedback_decision
from app.shared.config import Settings
from app.shared.database.session import DatabaseSessions


USER_ID = UUID("91111111-1111-4111-8111-111111111111")
OTHER_ID = UUID("92222222-2222-4222-8222-222222222222")
ENTRY_ID = UUID("93333333-3333-4333-8333-333333333333")
ENTRY_ITEM_ID = UUID("94444444-4444-4444-8444-444444444444")
PATTERN_ITEM_ID = UUID("95555555-5555-4555-8555-555555555555")
HEADERS = {"Authorization": "Bearer valid"}
UPDATED_AT = datetime(2026, 7, 23, 10, 30, tzinfo=timezone.utc)


class Verifier:
    def verify_access_token(self, token: str) -> str:
        if token != "valid":
            raise RuntimeError("private auth failure")
        return str(USER_ID)


class Transaction(AbstractContextManager):
    def __enter__(self):
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> bool:
        return False


class Session:
    def begin(self) -> Transaction:
        return Transaction()

    def execute(self, *_args, **_kwargs):
        return None

    def close(self) -> None:
        return None


def entry_item() -> EntryInsightReviewItem:
    return EntryInsightReviewItem(
        id=ENTRY_ITEM_ID,
        scope="entry_insight",
        type="energy_loss",
        category="energy",
        statement="Preparing at the last minute drained your energy.",
        source_quote="The rushed preparation was exhausting.",
        source_entry_ids=[ENTRY_ID],
        source_dates=[date(2026, 7, 20)],
        inference_level="direct",
        confidence=0.94,
        status="pending",
        feedback=None,
    )


def pattern_item() -> PatternReviewItem:
    return PatternReviewItem(
        id=PATTERN_ITEM_ID,
        scope="pattern",
        type="hidden_driver",
        category="hidden_driver",
        statement="You may protect competence by preparing intensely.",
        source_quote=None,
        source_entry_ids=[ENTRY_ID],
        source_dates=[date(2026, 7, 20)],
        inference_level="synthesized",
        confidence=0.8,
        status="pending",
        feedback=None,
    )


class Repository:
    def __init__(self, items: tuple[ReviewItem, ...]) -> None:
        self.items = {item.id: item for item in items}
        self.owners = {item.id: USER_ID for item in items}
        self.list_calls: list[dict[str, object]] = []
        self.feedback_calls: list[dict[str, object]] = []
        self.feedback_values: dict[UUID, tuple[object, ...]] = {}
        self.source_version = 10
        self.data_error = False
        self.stale = False
        self.legacy_item_id: UUID | None = PATTERN_ITEM_ID
        self.legacy_lookup_calls: list[dict[str, object]] = []

    def count_items(self, _session, **kwargs) -> int:
        if self.data_error:
            raise ReviewRepositoryDataError
        return len(self._matching(**kwargs))

    def list_items(self, _session, **kwargs) -> tuple[ReviewItem, ...]:
        if self.data_error:
            raise ReviewRepositoryDataError
        self.list_calls.append(kwargs)
        values = self._matching(**kwargs)
        offset = (int(kwargs["page"]) - 1) * int(kwargs["page_size"])
        return tuple(values[offset : offset + int(kwargs["page_size"])])

    def _matching(self, **kwargs) -> list[ReviewItem]:
        return [
            item
            for item_id, item in self.items.items()
            if self.owners[item_id] == kwargs["user_id"]
            and item.scope == kwargs["scope"]
            and item.status == kwargs["status"]
            and (kwargs["category"] == "all" or item.category == kwargs["category"])
        ]

    def get_by_owner(
        self, _session, *, user_id: UUID, item_id: UUID
    ) -> ReviewItem | None:
        if self.data_error:
            raise ReviewRepositoryDataError
        if self.owners.get(item_id) != user_id:
            return None
        return self.items.get(item_id)

    def pattern_item_id_for_snapshot_insight(self, _session, **kwargs):
        if self.data_error:
            raise ReviewRepositoryDataError
        self.legacy_lookup_calls.append(kwargs)
        return self.legacy_item_id

    def put_feedback(self, _session, **kwargs) -> SavedReviewFeedback:
        if self.stale:
            raise ReviewItemStaleError
        item_id = kwargs["item_id"]
        if self.owners.get(item_id) != kwargs["user_id"]:
            raise ReviewItemNotFoundError
        self.feedback_calls.append(kwargs)
        normalized = (
            kwargs["verdict"],
            kwargs["corrected_statement"],
            kwargs["note"],
        )
        changed = self.feedback_values.get(item_id) != normalized
        if changed:
            self.feedback_values[item_id] = normalized
            self.source_version += 1
            item = self.items[item_id]
            decision = feedback_decision(
                scope=item.scope,
                verdict=kwargs["verdict"],
            )
            feedback_kwargs = {
                "verdict": kwargs["verdict"],
                "corrected_statement": kwargs["corrected_statement"],
                "note": kwargs["note"],
                "evidence_weight": decision.evidence_weight,
                "updated_at": UPDATED_AT,
            }
            feedback = (
                EntryInsightFeedback(**feedback_kwargs)
                if item.scope == "entry_insight"
                else PatternFeedback(**feedback_kwargs)
            )
            self.items[item_id] = item.model_copy(
                update={"status": decision.status, "feedback": feedback}
            )
        return SavedReviewFeedback(
            item_id=item_id,
            changed=changed,
            source_version=self.source_version,
            updated_at=UPDATED_AT,
        )


class RecalculationRepository:
    def __init__(self) -> None:
        self.calls: list[UUID] = []
        self.fail = False
        self.outcome = "accepted"

    def request_recalculation(self, _session, *, user_id: UUID):
        self.calls.append(user_id)
        if self.fail:
            raise RuntimeError("private scheduling detail")
        return RecalculationRequest(
            outcome=self.outcome,  # type: ignore[arg-type]
            job_id=(
                UUID("98888888-8888-4888-8888-888888888888")
                if self.outcome == "accepted"
                else None
            ),
            source_version=11,
            valid_entry_count=3,
            distinct_entry_dates=2,
            reflective_word_count=300,
        )


def settings(
    *,
    rate_limiting: bool = False,
    reflection_api_enabled: bool = True,
) -> Settings:
    return Settings.model_validate(
        {
            "ENVIRONMENT": "test",
            "ENABLE_API_DOCS": False,
            "CORS_ALLOW_ORIGINS": "https://app.example.test",
            "LOG_FORMAT": "text",
            "RATE_LIMITING_ENABLED": rate_limiting,
            "REFLECTION_ENGINE_ENABLED": True,
            "REFLECTION_SCHEDULER_ENABLED": False,
            "REFLECTION_API_ENABLED": reflection_api_enabled,
            "REFLECTION_ROLLOUT_MODE": (
                "publish" if reflection_api_enabled else "shadow"
            ),
            "REFLECTION_ROLLOUT_USER_IDS": str(USER_ID),
        }
    )


def build_app(
    items: tuple[ReviewItem, ...] = (entry_item(), pattern_item()),
    *,
    rate_limiting: bool = False,
    enabled: bool = True,
    allowed_user_ids: set[UUID] | None = None,
):
    repository = Repository(items)
    recalculation = RecalculationRepository()
    sessions = DatabaseSessions(
        None,
        None,
        lambda: Session(),
        lambda: Session(),
    )  # type: ignore[arg-type]
    app = create_app(
        settings=settings(rate_limiting=rate_limiting),
        database_sessions=sessions,
        token_verifier=Verifier(),
    )
    app.state.review_service = ReviewService(
        repository=repository,  # type: ignore[arg-type]
        recalculation_repository=recalculation,  # type: ignore[arg-type]
        enabled=enabled,
        allowed_user_ids=(
            {USER_ID} if allowed_user_ids is None else allowed_user_ids
        ),
    )
    return app, repository, recalculation


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    assert response.json()["error_code"] == code
    assert response.headers["cache-control"] == "private, no-store"


def test_list_defaults_filters_paginates_and_returns_camel_case() -> None:
    app, repository, _recalculation = build_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/review/items?scope=entry_insight",
            headers=HEADERS,
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {
        "items": [
            {
                "id": str(ENTRY_ITEM_ID),
                "scope": "entry_insight",
                "type": "energy_loss",
                "category": "energy",
                "statement": "Preparing at the last minute drained your energy.",
                "sourceQuote": "The rushed preparation was exhausting.",
                "sourceEntryIds": [str(ENTRY_ID)],
                "sourceDates": ["2026-07-20"],
                "inferenceLevel": "direct",
                "confidence": 0.94,
                "status": "pending",
                "feedback": None,
            }
        ],
        "pagination": {"page": 1, "pageSize": 20, "total": 1},
    }
    assert repository.list_calls == [
        {
            "user_id": USER_ID,
            "scope": "entry_insight",
            "category": "all",
            "status": "pending",
            "page": 1,
            "page_size": 20,
        }
    ]


@pytest.mark.parametrize(
    "query",
    [
        "scope=entry_insight&category=hidden_driver",
        "scope=pattern&category=energy",
        "scope=entry_insight&search=private",
        "scope=entry_insight&scope=pattern",
        "scope=entry_insight&page=0",
        "scope=entry_insight&page_size=101",
    ],
)
def test_list_rejects_cross_scope_unknown_repeated_and_unbounded_queries(
    query: str,
) -> None:
    app, _repository, _recalculation = build_app()
    with TestClient(app) as client:
        response = client.get(f"/api/v1/review/items?{query}", headers=HEADERS)
    assert_error(response, 422, "VALIDATION_ERROR")


def test_authentication_precedes_feedback_body_parsing() -> None:
    app, repository, _recalculation = build_app()
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/review/items/{ENTRY_ITEM_ID}/feedback",
            content=b"not-json-private-body",
        )
    assert_error(response, 401, "UNAUTHORIZED")
    assert repository.feedback_calls == []


def test_feedback_body_accepts_only_frozen_camel_case_fields() -> None:
    app, repository, _recalculation = build_app()
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/review/items/{ENTRY_ITEM_ID}/feedback",
            headers=HEADERS,
            json={
                "verdict": "accurate",
                "corrected_statement": "This alias is not public.",
            },
        )
    assert_error(response, 422, "VALIDATION_ERROR")
    assert repository.feedback_calls == []


@pytest.mark.parametrize(
    ("enabled", "allowed_user_ids"),
    [(False, {USER_ID}), (True, {OTHER_ID})],
)
def test_disabled_and_out_of_cohort_review_operations_are_opaque_and_read_nothing(
    enabled: bool,
    allowed_user_ids: set[UUID],
) -> None:
    app, repository, recalculation = build_app(
        enabled=enabled,
        allowed_user_ids=allowed_user_ids,
    )
    with TestClient(app) as client:
        listed = client.get(
            "/api/v1/review/items?scope=entry_insight",
            headers=HEADERS,
        )
        feedback = client.post(
            f"/api/v1/review/items/{ENTRY_ITEM_ID}/feedback",
            headers=HEADERS,
            json={"verdict": "accurate"},
        )
    for response in (listed, feedback):
        assert_error(response, 503, "SERVICE_UNAVAILABLE")
        assert response.headers["retry-after"] == "60"
    assert repository.list_calls == []
    assert repository.feedback_calls == []
    assert recalculation.calls == []


def test_bootstrap_uses_the_public_reflection_api_gate_for_review() -> None:
    sessions = DatabaseSessions(
        None,
        None,
        lambda: Session(),
        lambda: Session(),
    )  # type: ignore[arg-type]
    app = create_app(
        settings=settings(reflection_api_enabled=False),
        database_sessions=sessions,
        token_verifier=Verifier(),
    )
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/review/items?scope=entry_insight",
            headers=HEADERS,
        )
    assert_error(response, 503, "SERVICE_UNAVAILABLE")
    assert app.state.review_service._enabled is False
    assert app.state.reflections_service._enabled is False


@pytest.mark.parametrize(
    ("item_id", "verdict", "expected_status", "expected_weight"),
    [
        (ENTRY_ITEM_ID, "accurate", "confirmed", 1.0),
        (ENTRY_ITEM_ID, "partly_accurate", "partially_confirmed", 0.5),
        (ENTRY_ITEM_ID, "not_accurate", "rejected", 0.0),
        (PATTERN_ITEM_ID, "resonates", "confirmed", 1.0),
        (PATTERN_ITEM_ID, "partly_true", "partially_confirmed", 0.5),
        (PATTERN_ITEM_ID, "not_true", "rejected", 0.0),
    ],
)
def test_feedback_maps_every_scope_verdict(
    item_id: UUID,
    verdict: str,
    expected_status: str,
    expected_weight: float,
) -> None:
    app, _repository, recalculation = build_app()
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/review/items/{item_id}/feedback",
            headers=HEADERS,
            json={
                "verdict": verdict,
                "correctedStatement": "  A corrected statement.  ",
                "note": "  A private note.  ",
            },
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert body["status"] == expected_status
    assert body["feedback"] == {
        "verdict": verdict,
        "correctedStatement": "A corrected statement.",
        "note": "A private note.",
        "evidenceWeight": expected_weight,
        "updatedAt": "2026-07-23T10:30:00Z",
    }
    assert recalculation.calls == [USER_ID]


def test_feedback_remains_successful_when_recalculation_is_not_eligible() -> None:
    app, _repository, recalculation = build_app()
    recalculation.outcome = "not_eligible"

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/review/items/{ENTRY_ITEM_ID}/feedback",
            headers=HEADERS,
            json={"verdict": "not_accurate"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert recalculation.calls == [USER_ID]


@pytest.mark.parametrize(
    ("legacy_response", "review_verdict"),
    [
        ("resonates", "resonates"),
        ("partly", "partly_true"),
        ("rejected", "not_true"),
    ],
)
def test_legacy_pattern_feedback_delegates_to_review_command(
    legacy_response: str,
    review_verdict: str,
) -> None:
    app, repository, recalculation = build_app()
    snapshot_id = UUID("96666666-6666-4666-8666-666666666666")
    insight_id = UUID("97777777-7777-4777-8777-777777777777")

    item = app.state.review_service.save_legacy_pattern_feedback(
        user_id=USER_ID,
        snapshot_id=snapshot_id,
        insight_id=insight_id,
        response=legacy_response,
        uow=app.state.database_sessions.unit_of_work_factory,
    )

    assert item.id == PATTERN_ITEM_ID
    assert item.feedback is not None
    assert item.feedback.verdict == review_verdict
    assert repository.legacy_lookup_calls == [
        {
            "user_id": USER_ID,
            "snapshot_id": snapshot_id,
            "insight_id": insight_id,
        }
    ]
    assert repository.feedback_calls[0]["verdict"] == review_verdict
    assert recalculation.calls == [USER_ID]


@pytest.mark.parametrize(
    ("item_id", "verdict"),
    [(ENTRY_ITEM_ID, "resonates"), (PATTERN_ITEM_ID, "accurate")],
)
def test_wrong_scope_verdict_is_rejected_without_a_write(
    item_id: UUID, verdict: str
) -> None:
    app, repository, recalculation = build_app()
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/review/items/{item_id}/feedback",
            headers=HEADERS,
            json={"verdict": verdict},
        )
    assert_error(response, 422, "VALIDATION_ERROR")
    assert repository.feedback_calls == []
    assert recalculation.calls == []


def test_identical_normalized_replay_does_not_bump_or_request_another_job() -> None:
    app, repository, recalculation = build_app()
    path = f"/api/v1/review/items/{ENTRY_ITEM_ID}/feedback"
    with TestClient(app) as client:
        first = client.post(
            path,
            headers=HEADERS,
            json={"verdict": "partly_accurate", "note": "  note  "},
        )
        replay = client.post(
            path,
            headers=HEADERS,
            json={
                "verdict": "partly_accurate",
                "correctedStatement": " ",
                "note": "note",
            },
        )
        changed = client.post(
            path,
            headers=HEADERS,
            json={"verdict": "not_accurate", "note": "note"},
        )
    assert first.status_code == replay.status_code == changed.status_code == 200
    assert repository.source_version == 12
    assert recalculation.calls == [USER_ID, USER_ID]
    assert replay.json() == first.json()
    assert changed.json()["feedback"]["evidenceWeight"] == 0.0


def test_missing_other_owner_and_stale_items_are_non_enumerating() -> None:
    app, repository, _recalculation = build_app()
    repository.owners[ENTRY_ITEM_ID] = OTHER_ID
    with TestClient(app) as client:
        other = client.post(
            f"/api/v1/review/items/{ENTRY_ITEM_ID}/feedback",
            headers=HEADERS,
            json={"verdict": "accurate"},
        )
        random = client.post(
            "/api/v1/review/items/96666666-6666-4666-8666-666666666666/feedback",
            headers=HEADERS,
            json={"verdict": "accurate"},
        )
    assert_error(other, 404, "REVIEW_ITEM_NOT_FOUND")
    assert_error(random, 404, "REVIEW_ITEM_NOT_FOUND")
    assert other.json()["message"] == random.json()["message"]

    repository.owners[ENTRY_ITEM_ID] = USER_ID
    repository.stale = True
    with TestClient(app) as client:
        stale = client.post(
            f"/api/v1/review/items/{ENTRY_ITEM_ID}/feedback",
            headers=HEADERS,
            json={"verdict": "accurate"},
        )
    assert_error(stale, 409, "REVIEW_ITEM_STALE")


def test_corrupt_review_data_is_sanitized_and_never_cached() -> None:
    app, repository, _recalculation = build_app()
    repository.data_error = True
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/review/items?scope=entry_insight",
            headers=HEADERS,
        )
    assert_error(response, 500, "REVIEW_DATA_UNAVAILABLE")
    assert "cipher" not in response.text.lower()


def test_scheduler_failure_keeps_durable_feedback_but_returns_sanitized_503(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, repository, recalculation = build_app()
    recalculation.fail = True
    private_note = "unique-private-review-note"
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/review/items/{ENTRY_ITEM_ID}/feedback",
            headers=HEADERS,
            json={"verdict": "accurate", "note": private_note},
        )
    assert_error(response, 503, "REFLECTION_RECALCULATION_UNAVAILABLE")
    assert repository.items[ENTRY_ITEM_ID].status == "confirmed"
    assert private_note not in caplog.text
    assert private_note not in response.text


def test_feedback_rate_limit_is_owner_scoped_and_no_store() -> None:
    app, _repository, _recalculation = build_app(rate_limiting=True)
    path = f"/api/v1/review/items/{ENTRY_ITEM_ID}/feedback"
    with TestClient(app) as client:
        responses = [
            client.post(
                path,
                headers=HEADERS,
                json={"verdict": "accurate"},
            )
            for _index in range(6)
        ]
    assert all(response.status_code == 200 for response in responses[:5])
    assert_error(responses[-1], 429, "RATE_LIMITED")
    assert responses[-1].headers["retry-after"].isdigit()
