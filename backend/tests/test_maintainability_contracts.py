from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.main import create_app
from app.modules.entries.repository import MissingMatchingDraftError
from app.modules.entries.service import EntryService
from app.modules.jobs.service import _classify_failure
from app.modules.processing.provider import (
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.modules.processing.service import (
    AnalysisValidationError,
    PrivacyValidationError,
)
from app.modules.reflection_engine.provider import (
    ReflectionProviderResponseError,
    ReflectionProviderUnavailableError,
)
from app.modules.reflection_engine.service import SnapshotValidationError
from app.shared.config.settings import Settings
from app.shared.database.session import DatabaseSessions
from app.shared.exceptions.domain import DomainError
from app.shared.security.encryption import ContentUnavailableError
from scripts.run_sample_reflection_e2e import parse_args


USER_ID = UUID("11111111-1111-4111-8111-111111111111")


class Verifier:
    def verify_access_token(self, _access_token: str) -> str:
        return str(USER_ID)


def test_application_state_registration_and_service_graph_are_stable() -> None:
    settings = Settings.model_validate(
        {
            "ENVIRONMENT": "test",
            "ENABLE_API_DOCS": False,
            "LOG_FORMAT": "text",
            "RATE_LIMITING_ENABLED": False,
        }
    )
    sessions = DatabaseSessions(None, None, None, None)

    app = create_app(
        settings=settings,
        database_sessions=sessions,
        token_verifier=Verifier(),
    )

    assert set(app.state._state) == {
        "authentication_service",
        "content_cipher",
        "database_sessions",
        "entry_service",
        "job_service",
        "meter_provider",
        "processing_service",
        "processing_worker",
        "profile_service",
        "rate_limiter",
        "reflection_engine_service",
        "reflection_telemetry",
        "reflections_service",
        "settings",
        "tracer_provider",
        "transcriber",
    }
    assert app.state.database_sessions is sessions
    assert app.state.job_service._processing is app.state.processing_service
    assert app.state.job_service._reflection is app.state.reflection_engine_service
    assert app.state.processing_worker._service is app.state.job_service
    assert app.state.entry_service._cipher is app.state.content_cipher


class SubmitFailureRepository:
    def profile_timezone(self, _session: object, _user_id: UUID) -> str:
        return "UTC"

    def fixed_config_id(self, _session: object) -> UUID:
        return uuid4()

    def submit_text(self, _session: object, **_kwargs: object) -> object:
        raise MissingMatchingDraftError("stored procedure detail")


class Cipher:
    def canonicalize(self, plaintext: str) -> str:
        return plaintext

    def draft_fingerprint(self, _plaintext: str, *, user_id: UUID) -> tuple[str, str]:
        return "key", str(user_id)

    def encrypt(self, _plaintext: str, *, user_id: UUID, record_id: UUID) -> dict:
        return {"owner": str(user_id), "record": str(record_id)}


class UserWork:
    session = object()

    def __enter__(self) -> "UserWork":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class UserUnitOfWork:
    def for_user(self, _user_id: UUID) -> UserWork:
        return UserWork()


def test_missing_matching_draft_preserves_exact_conflict_error() -> None:
    service = EntryService(
        repository=SubmitFailureRepository(),  # type: ignore[arg-type]
        past_imports=SimpleNamespace(),
        cipher=Cipher(),  # type: ignore[arg-type]
    )

    with pytest.raises(DomainError) as exc_info:
        service.submit_text(
            user_id=USER_ID,
            content="A valid entry",
            uow=UserUnitOfWork(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "INVALID_STATE"
    assert exc_info.value.message == "A matching saved draft is required."


@pytest.mark.parametrize(
    ("error", "synthesis", "expected"),
    [
        (ContentUnavailableError(), False, ("ENTRY_CONTENT_UNAVAILABLE", False)),
        (ProviderResponseError("invalid"), False, ("INVALID_ANALYSIS", False)),
        (AnalysisValidationError("quality"), False, ("INVALID_ANALYSIS", False)),
        (PrivacyValidationError(), False, ("PRIVACY_VALIDATION_FAILED", False)),
        (
            ReflectionProviderResponseError("invalid"),
            True,
            ("INVALID_SYNTHESIS", False),
        ),
        (SnapshotValidationError("invalid"), True, ("INVALID_SYNTHESIS", False)),
        (ValueError("invalid"), True, ("INVALID_SYNTHESIS", False)),
        (ValueError("invalid"), False, ("INVALID_ANALYSIS", False)),
        (RuntimeError("unexpected"), False, ("PROCESSING_FAILED", False)),
    ],
)
def test_worker_failure_classification_is_stable(
    error: Exception,
    synthesis: bool,
    expected: tuple[str, bool],
) -> None:
    assert _classify_failure(error, synthesis=synthesis) == expected


@pytest.mark.parametrize(
    "error_type",
    [ProviderUnavailableError, ReflectionProviderUnavailableError],
)
def test_provider_unavailability_without_a_cause_remains_retryable(error_type) -> None:
    expected_code = (
        "PROVIDER_UNAVAILABLE"
        if error_type is ProviderUnavailableError
        else "REFLECTION_PROVIDER_UNAVAILABLE"
    )
    assert _classify_failure(error_type("unavailable")) == (expected_code, True)


def test_sample_e2e_cli_defaults_and_continuation_shape_are_stable() -> None:
    args = parse_args(
        [
            "--input",
            "input.json",
            "--output",
            "output.json",
            "--frontend-env",
            "frontend.env",
            "--backend-env",
            "backend.env",
        ]
    )

    assert vars(args) == {
        "input": args.input,
        "output": args.output,
        "frontend_env": args.frontend_env,
        "backend_env": args.backend_env,
        "timeout_seconds": 14_400,
        "import_interval_seconds": 0.55,
        "prior_diagnostic_attempts": 0,
        "prior_diagnostic_unpriced_attempts": 0,
        "prior_diagnostic_known_cost_usd": args.prior_diagnostic_known_cost_usd,
        "finalize_existing": False,
        "continuation_events": None,
    }
    assert args.prior_diagnostic_known_cost_usd == 0
