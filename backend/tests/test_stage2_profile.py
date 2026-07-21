from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from types import TracebackType
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.modules.profile.schemas import AccountDeletionRequest, ProfileUpdateRequest
from app.modules.profile.service import ProfileService
from app.modules.profile.types import AccountDeletionOutcome, ProfileData
from app.shared.config import Settings
from app.shared.database.session import DatabaseSessions
from app.shared.integrations.supabase_auth import SupabaseAccountAuthGateway


USER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ID = UUID("22222222-2222-4222-8222-222222222222")
HEADERS = {"Authorization": "Bearer access"}


class ValidVerifier:
    def verify_access_token(self, _access_token: str) -> str:
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


class FakeSession:
    def begin(self) -> Transaction:
        return Transaction()

    def execute(self, *_args, **_kwargs) -> None:
        return None

    def close(self) -> None:
        return None


class FakeRepository:
    def __init__(self) -> None:
        self.profile = ProfileData(display_name="Original", timezone="UTC")
        self.changes: list[dict[str, str]] = []

    def get(self, _session, _user_id: UUID) -> ProfileData:
        return self.profile

    def update(self, _session, _user_id: UUID, changes: dict[str, str]) -> ProfileData:
        self.changes.append(dict(changes))
        self.profile = ProfileData(
            display_name=changes.get("display_name", self.profile.display_name),
            timezone=changes.get("timezone", self.profile.timezone),
        )
        return self.profile


@dataclass
class FakeAccountAuth:
    proof_user_id: UUID = USER_ID
    proof_error: Exception | None = None
    delete_error: Exception | None = None

    def __post_init__(self) -> None:
        self.proofs: list[str] = []
        self.deleted: list[UUID] = []

    def verify_user(self, proof_token: str) -> UUID:
        self.proofs.append(proof_token)
        if self.proof_error is not None:
            raise self.proof_error
        return self.proof_user_id

    def delete_user(self, user_id: UUID) -> AccountDeletionOutcome:
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted.append(user_id)
        return AccountDeletionOutcome.DELETED


def app_settings() -> Settings:
    return Settings.model_validate(
        {
            "ENVIRONMENT": "test",
            "ENABLE_API_DOCS": False,
            "CORS_ALLOW_ORIGINS": "https://app.example.test",
            "LOG_FORMAT": "text",
            "RATE_LIMITING_ENABLED": False,
        }
    )


def build_app(repository: FakeRepository | None = None, account_auth=None):
    repository = repository or FakeRepository()
    account_auth = account_auth or FakeAccountAuth()
    sessions = DatabaseSessions(None, None, lambda: FakeSession(), None)  # type: ignore[arg-type]
    app = create_app(
        settings=app_settings(),
        database_sessions=sessions,
        token_verifier=ValidVerifier(),
        account_auth=account_auth,
    )
    app.state.profile_service = ProfileService(
        repository=repository,  # type: ignore[arg-type]
        account_auth=account_auth,
    )
    return app, repository, account_auth


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error_code", "message", "details", "request_id"}
    assert body["error_code"] == code
    assert response.headers["x-request-id"] == body["request_id"]
    return body


def test_profile_read_and_partial_update_expose_only_public_fields() -> None:
    app, repository, _account_auth = build_app()
    with TestClient(app) as client:
        read = client.get("/api/v1/profile", headers=HEADERS)
        updated = client.patch(
            "/api/v1/profile",
            headers=HEADERS,
            json={"display_name": "  Updated  "},
        )
    assert read.status_code == 200
    assert read.json() == {"display_name": "Original", "timezone": "UTC"}
    assert updated.status_code == 200
    assert updated.json() == {"display_name": "Updated", "timezone": "UTC"}
    assert repository.changes == [{"display_name": "Updated"}]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"display_name": None},
        {"timezone": None},
        {"timezone": " UTC"},
        {"timezone": "Not/A_Real_Zone"},
        {"display_name": "valid", "user_id": str(OTHER_ID)},
    ],
)
def test_profile_update_rejects_empty_null_noncanonical_and_ownership_fields(payload) -> None:
    app, _repository, _account_auth = build_app()
    with TestClient(app) as client:
        response = client.patch("/api/v1/profile", headers=HEADERS, json=payload)
    assert_error(response, 422, "VALIDATION_ERROR")


def test_profile_dtos_are_strict_without_fastapi() -> None:
    assert ProfileUpdateRequest.model_validate({"timezone": "Asia/Kolkata"}).timezone == "Asia/Kolkata"
    with pytest.raises(ValidationError):
        ProfileUpdateRequest.model_validate({"display_name": "x" * 101})
    with pytest.raises(ValidationError):
        AccountDeletionRequest.model_validate(
            {
                "confirmation": "DELETE MY ACCOUNT",
                "reauthentication_token": "proof",
                "user_id": str(USER_ID),
            }
        )


def test_account_deletion_requires_exact_body_and_uses_verified_owner() -> None:
    account_auth = FakeAccountAuth()
    app, _repository, _account_auth = build_app(account_auth=account_auth)
    with TestClient(app) as client:
        response = client.request(
            "DELETE",
            "/api/v1/account",
            headers=HEADERS,
            json={
                "confirmation": "DELETE MY ACCOUNT",
                "reauthentication_token": "fresh-proof",
            },
        )
    assert response.status_code == 204
    assert response.content == b""
    assert account_auth.proofs == ["fresh-proof"]
    assert account_auth.deleted == [USER_ID]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"confirmation": "delete", "reauthentication_token": "proof"},
        {"confirmation": "DELETE MY ACCOUNT", "reauthentication_token": ""},
        {
            "confirmation": "DELETE MY ACCOUNT",
            "reauthentication_token": "proof",
            "user_id": str(USER_ID),
        },
    ],
)
def test_account_deletion_rejects_invalid_contract_body(payload) -> None:
    app, _repository, _account_auth = build_app()
    with TestClient(app) as client:
        response = client.request("DELETE", "/api/v1/account", headers=HEADERS, json=payload)
    assert_error(response, 422, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    "account_auth",
    [
        FakeAccountAuth(proof_user_id=OTHER_ID),
        FakeAccountAuth(proof_error=RuntimeError("provider proof payload")),
    ],
)
def test_account_deletion_rejects_invalid_or_other_user_proof(account_auth) -> None:
    app, _repository, _account_auth = build_app(account_auth=account_auth)
    with TestClient(app) as client:
        response = client.request(
            "DELETE",
            "/api/v1/account",
            headers=HEADERS,
            json={
                "confirmation": "DELETE MY ACCOUNT",
                "reauthentication_token": "fresh-proof",
            },
        )
    body = assert_error(response, 401, "REAUTHENTICATION_REQUIRED")
    assert "provider" not in response.text
    assert body["message"] == "Fresh reauthentication is required to delete your account."


def test_account_deletion_provider_failure_is_safe_and_retryable() -> None:
    account_auth = FakeAccountAuth(delete_error=RuntimeError("secret provider payload"))
    app, _repository, _account_auth = build_app(account_auth=account_auth)
    with TestClient(app) as client:
        response = client.request(
            "DELETE",
            "/api/v1/account",
            headers=HEADERS,
            json={
                "confirmation": "DELETE MY ACCOUNT",
                "reauthentication_token": "fresh-proof",
            },
        )
    assert_error(response, 503, "ACCOUNT_DELETION_UNAVAILABLE")
    assert response.headers["retry-after"] == "30"
    assert "secret provider payload" not in response.text


def test_account_deletion_already_missing_outcome_is_successful() -> None:
    class AlreadyMissing(FakeAccountAuth):
        def delete_user(self, _user_id: UUID) -> AccountDeletionOutcome:
            return AccountDeletionOutcome.ALREADY_MISSING

    app, _repository, _account_auth = build_app(account_auth=AlreadyMissing())
    with TestClient(app) as client:
        response = client.request(
            "DELETE",
            "/api/v1/account",
            headers=HEADERS,
            json={
                "confirmation": "DELETE MY ACCOUNT",
                "reauthentication_token": "fresh-proof",
            },
        )
    assert response.status_code == 204


def test_account_auth_adapter_classifies_missing_identity_as_idempotent_success() -> None:
    class MissingIdentity(Exception):
        status_code = 404

    class VerificationAuth:
        def get_user(self, _token: str):
            return type("Response", (), {"user": type("User", (), {"id": str(USER_ID)})()})()

    class Admin:
        def delete_user(self, _user_id: str) -> None:
            raise MissingIdentity()

    verification_client = type("Client", (), {"auth": VerificationAuth()})()
    administration_client = type(
        "Client", (), {"auth": type("Auth", (), {"admin": Admin()})()}
    )()
    gateway = SupabaseAccountAuthGateway(verification_client, administration_client)
    assert gateway.verify_user("proof") == USER_ID
    assert gateway.delete_user(USER_ID) is AccountDeletionOutcome.ALREADY_MISSING


def test_product_routes_authenticate_before_parsing_their_bodies() -> None:
    app, _repository, _account_auth = build_app()
    with TestClient(app) as client:
        response = client.request(
            "DELETE",
            "/api/v1/account",
            headers={"Content-Type": "application/json"},
            content=b'{"confirmation":',
        )
    assert_error(response, 401, "UNAUTHORIZED")
