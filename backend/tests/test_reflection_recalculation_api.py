from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from types import TracebackType
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.reflections.service import ReflectionsService
from app.modules.reflections.types import RecalculationRequest
from app.shared.config import Settings
from app.shared.database.session import DatabaseSessions


USER_ID = UUID("a1111111-1111-4111-8111-111111111111")
JOB_ID = UUID("a2222222-2222-4222-8222-222222222222")
HEADERS = {"Authorization": "Bearer valid"}


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


class Repository:
    def __init__(self) -> None:
        self.calls: list[UUID] = []
        self.fail = False
        self.result = RecalculationRequest(
            outcome="accepted",
            job_id=JOB_ID,
            source_version=12,
            valid_entry_count=4,
            distinct_entry_dates=3,
            reflective_word_count=420,
        )

    def request_recalculation(self, _session, *, user_id: UUID):
        self.calls.append(user_id)
        if self.fail:
            raise RuntimeError("private database detail")
        return self.result


def settings(*, rate_limiting: bool = False) -> Settings:
    return Settings.model_validate(
        {
            "ENVIRONMENT": "test",
            "ENABLE_API_DOCS": False,
            "CORS_ALLOW_ORIGINS": "https://app.example.test",
            "LOG_FORMAT": "text",
            "RATE_LIMITING_ENABLED": rate_limiting,
            "REFLECTION_ENGINE_ENABLED": True,
            "REFLECTION_SCHEDULER_ENABLED": False,
            "REFLECTION_API_ENABLED": True,
            "REFLECTION_ROLLOUT_MODE": "publish",
            "REFLECTION_ROLLOUT_USER_IDS": str(USER_ID),
        }
    )


def build_app(
    *,
    recalculation_enabled: bool = True,
    rate_limiting: bool = False,
):
    repository = Repository()
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
    app.state.reflections_service = ReflectionsService(
        repository=repository,  # type: ignore[arg-type]
        review_service=object(),  # type: ignore[arg-type]
        cipher=object(),  # type: ignore[arg-type]
        enabled=True,
        recalculation_enabled=recalculation_enabled,
        allowed_user_ids={USER_ID},
    )
    return app, repository


def test_recalculation_is_authenticated_no_body_exact_202_and_no_store() -> None:
    app, repository = build_app()
    with TestClient(app) as client:
        unauthenticated = client.post("/api/v1/reflections/recalculate")
        with_body = client.post(
            "/api/v1/reflections/recalculate",
            headers=HEADERS,
            json={},
        )
        first = client.post("/api/v1/reflections/recalculate", headers=HEADERS)
        second = client.post("/api/v1/reflections/recalculate", headers=HEADERS)

    assert unauthenticated.status_code == 401
    assert with_body.status_code == 422
    assert with_body.headers["cache-control"] == "private, no-store"
    assert first.status_code == second.status_code == 202
    assert first.headers["cache-control"] == "private, no-store"
    assert first.json() == second.json() == {
        "status": "accepted",
        "jobId": str(JOB_ID),
    }
    assert repository.calls == [USER_ID, USER_ID]


def test_concurrent_recalculation_requests_return_the_same_durable_job() -> None:
    app, repository = build_app()

    def request_once() -> tuple[int, dict[str, str]]:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/reflections/recalculate",
                headers=HEADERS,
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(lambda _index: request_once(), range(4)))

    assert responses == [
        (202, {"status": "accepted", "jobId": str(JOB_ID)})
    ] * 4
    assert repository.calls == [USER_ID] * 4


def test_recalculation_maps_current_and_ineligible_conflicts() -> None:
    app, repository = build_app()
    with TestClient(app) as client:
        repository.result = RecalculationRequest(
            outcome="already_current",
            job_id=JOB_ID,
            source_version=12,
            valid_entry_count=4,
            distinct_entry_dates=3,
            reflective_word_count=420,
        )
        current = client.post("/api/v1/reflections/recalculate", headers=HEADERS)
        repository.result = RecalculationRequest(
            outcome="not_eligible",
            job_id=None,
            source_version=2,
            valid_entry_count=2,
            distinct_entry_dates=1,
            reflective_word_count=120,
        )
        ineligible = client.post(
            "/api/v1/reflections/recalculate",
            headers=HEADERS,
        )

    assert current.status_code == 409
    assert current.json()["error_code"] == "REFLECTION_ALREADY_CURRENT"
    assert current.headers["cache-control"] == "private, no-store"
    assert ineligible.status_code == 409
    assert ineligible.json()["error_code"] == "REFLECTION_NOT_ELIGIBLE"
    assert ineligible.json()["details"] == {
        "valid_entry_count": 2,
        "distinct_entry_dates": 1,
        "reflective_word_count": 120,
        "reason_codes": ["MINIMUM_BASIS_NOT_MET"],
    }
    assert ineligible.headers["cache-control"] == "private, no-store"


def test_recalculation_maps_configuration_database_and_job_failures_to_503() -> None:
    disabled_app, disabled_repository = build_app(recalculation_enabled=False)
    failed_app, failed_repository = build_app()
    failed_repository.fail = True
    unavailable_app, unavailable_repository = build_app()
    unavailable_repository.result = RecalculationRequest(
        outcome="unavailable",
        job_id=JOB_ID,
        source_version=12,
        valid_entry_count=4,
        distinct_entry_dates=3,
        reflective_word_count=420,
    )

    responses = []
    for app in (disabled_app, failed_app, unavailable_app):
        with TestClient(app) as client:
            responses.append(
                client.post("/api/v1/reflections/recalculate", headers=HEADERS)
            )

    for response in responses:
        assert response.status_code == 503
        assert response.json()["error_code"] == (
            "REFLECTION_RECALCULATION_UNAVAILABLE"
        )
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["retry-after"] == "60"
        assert "private" not in response.text
    assert disabled_repository.calls == []


def test_recalculation_rate_limit_is_owner_scoped_and_no_store() -> None:
    app, repository = build_app(rate_limiting=True)
    with TestClient(app) as client:
        responses = [
            client.post("/api/v1/reflections/recalculate", headers=HEADERS)
            for _ in range(6)
        ]

    assert [response.status_code for response in responses] == [202] * 5 + [429]
    assert responses[-1].json()["error_code"] == "RATE_LIMITED"
    assert responses[-1].headers["cache-control"] == "private, no-store"
    assert responses[-1].headers["retry-after"].isdigit()
    assert repository.calls == [USER_ID] * 5
