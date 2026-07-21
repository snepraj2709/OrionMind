from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
from types import TracebackType
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.modules.reflections.repository import ReflectionResourceNotFoundError
from app.modules.reflections.schemas import (
    AvailableHiddenDriver,
    FeedbackRequest,
    InsufficientInsight,
)
from app.modules.reflections.service import ReflectionsService
from app.modules.reflections.types import SavedFeedback
from app.shared.config import Settings
from app.shared.database.session import DatabaseSessions
from app.shared.security.encryption import AesGcmContentCipher


USER_ID = UUID("81111111-1111-4111-8111-111111111111")
OTHER_ID = UUID("82222222-2222-4222-8222-222222222222")
SNAPSHOT_ID = UUID("83333333-3333-4333-8333-333333333333")
HEADERS = {"Authorization": "Bearer valid"}


class Verifier:
    def verify_access_token(self, token: str) -> str:
        if token != "valid":
            raise RuntimeError("private auth failure")
        return str(USER_ID)


class Provider:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("GET and feedback must not invoke synthesis")

    def critique(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("GET and feedback must not invoke the critic")


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
    def __init__(self, raw: dict[str, object]) -> None:
        self.raw = raw
        self.read_users: list[UUID] = []
        self.feedback_calls: list[dict[str, object]] = []
        self.not_found = False

    def load_aggregate(self, _session, *, user_id: UUID) -> dict[str, object]:
        self.read_users.append(user_id)
        return self.raw

    def put_feedback(self, _session, **kwargs) -> SavedFeedback:
        if self.not_found:
            raise ReflectionResourceNotFoundError
        self.feedback_calls.append(kwargs)
        result = SavedFeedback(
            snapshot_id=kwargs["snapshot_id"],
            insight_id=kwargs["insight_id"],
            response=kwargs["response"],
            updated_at=datetime(2026, 7, 21, 12, 42, tzinfo=timezone.utc),
        )
        feedback = self.raw.setdefault("feedback", [])
        assert isinstance(feedback, list)
        feedback[:] = [
            item
            for item in feedback
            if item.get("insight_id") != str(kwargs["insight_id"])
        ]
        feedback.append(
            {"insight_id": str(kwargs["insight_id"]), "response": kwargs["response"]}
        )
        return result


def cipher() -> AesGcmContentCipher:
    return AesGcmContentCipher(
        encryption_keys={"test": b"e" * 32},
        active_encryption_key_id="test",
        fingerprint_keys={"test": b"f" * 32},
        active_fingerprint_key_id="test",
    )


def settings(*, reflections_enabled: bool = True) -> Settings:
    return Settings.model_validate(
        {
            "ENVIRONMENT": "test",
            "ENABLE_API_DOCS": False,
            "CORS_ALLOW_ORIGINS": "https://app.example.test",
            "LOG_FORMAT": "text",
            "RATE_LIMITING_ENABLED": False,
            "REFLECTION_ENGINE_ENABLED": reflections_enabled,
            "REFLECTION_SCHEDULER_ENABLED": False,
            "REFLECTION_API_ENABLED": reflections_enabled,
            "REFLECTION_ROLLOUT_MODE": (
                "publish" if reflections_enabled else "off"
            ),
            "REFLECTION_ROLLOUT_USER_IDS": (
                str(USER_ID) if reflections_enabled else ""
            ),
        }
    )


def current_basis(*, valid: int = 0, excluded: int = 0) -> dict[str, object]:
    return {
        "basis_start": "2026-04-23",
        "basis_end": "2026-07-21",
        "valid_entry_count": valid,
        "excluded_entry_count": excluded,
        "distinct_entry_dates": 2 if excluded else valid,
        "reflective_word_count": valid * 100,
        "excluded_reasons": {"test_or_noise": excluded} if excluded else {},
    }


def insufficient_rows() -> list[dict[str, object]]:
    return [
        {
            "id": str(uuid4()),
            "pattern_type": pattern_type,
            "ordinal": 0,
            "status": "insufficient_evidence",
            "reason_code": reason,
        }
        for pattern_type, reason in (
            ("hidden_driver", "DRIVER_NOT_REPEATED"),
            ("recurring_loop", "LOOP_NOT_REPEATED"),
            ("inner_tension", "BOTH_SIDES_NOT_SUPPORTED"),
        )
    ]


def snapshot_raw() -> dict[str, object]:
    return {
        "id": str(SNAPSHOT_ID),
        "version": 4,
        "source_version": 10,
        "basis_start": "2026-04-23",
        "basis_end": "2026-07-21",
        "valid_entry_count": 18,
        "excluded_entry_count": 4,
        "distinct_entry_dates": 11,
        "reflective_word_count": 2140,
        "status": "available",
        "created_at": "2026-07-21T12:35:00Z",
        "excluded_reasons": {"test_or_noise": 4},
    }


def raw_without_snapshot(*, valid: int = 0, excluded: int = 0) -> dict[str, object]:
    return {
        "state": {
            "latest_accepted_source_version": valid,
            "last_processing_error_code": None,
        },
        "job": None,
        "snapshot": None,
        "current_basis": current_basis(valid=valid, excluded=excluded),
        "insights": [],
        "evidence": [],
        "feedback": [],
    }


def raw_with_snapshot() -> dict[str, object]:
    return {
        "state": {
            "latest_accepted_source_version": 10,
            "last_processing_error_code": None,
        },
        "job": {"status": "completed"},
        "snapshot": snapshot_raw(),
        "current_basis": current_basis(valid=18, excluded=4),
        "insights": insufficient_rows(),
        "evidence": [],
        "feedback": [],
    }


def add_available_hidden(raw: dict[str, object], content_cipher: AesGcmContentCipher) -> UUID:
    insight_id = UUID("84444444-4444-4444-8444-444444444444")
    payload = {
        "version": 1,
        "pattern_type": "hidden_driver",
        "structure": {
            "canonical_need": "competence",
            "statement": "A possible pattern across your entries may involve making ideas tangible.",
            "underlying_need": "competence",
            "supporting_entries": 5,
            "distinct_dates": 4,
            "distinct_signal_types": 3,
        },
    }
    rows = raw["insights"]
    assert isinstance(rows, list)
    rows[0] = {
        "id": str(insight_id),
        "pattern_type": "hidden_driver",
        "ordinal": 0,
        "status": "available",
        "payload_envelope": content_cipher.encrypt_json(
            payload,
            user_id=USER_ID,
            record_id=insight_id,
            purpose="reflection_insight_payload",
        ),
        "confidence_label": "emerging",
        "score": 0.74,
    }
    return insight_id


def add_evidence(
    raw: dict[str, object],
    content_cipher: AesGcmContentCipher,
    *,
    insight_id: UUID,
) -> None:
    entry_id = UUID("85555555-5555-4555-8555-555555555555")
    signal_id = UUID("86666666-6666-4666-8666-666666666666")
    entry_text = "I felt capable after finishing the draft."
    quote = "felt capable"
    start = entry_text.index(quote)
    evidence = raw["evidence"]
    assert isinstance(evidence, list)
    evidence.append(
        {
            "insight_id": str(insight_id),
            "signal_id": str(signal_id),
            "entry_id": str(entry_id),
            "evidence_role": "supporting",
            "ordinal": 0,
            "source_start": start,
            "source_end": start + len(quote),
            "entry_date": "2026-07-20",
            "input_type": "text",
            "entry_content_envelope": content_cipher.encrypt(
                entry_text, user_id=USER_ID, record_id=entry_id
            ),
            "signal_payload_envelope": content_cipher.encrypt_json(
                {
                    "normalized_label": "capability after completion",
                    "interpretation": "Completing something may reinforce a sense of competence.",
                    "source_quote": quote,
                },
                user_id=USER_ID,
                record_id=signal_id,
                purpose="entry_signal_payload",
            ),
            "themes": ["career"],
        }
    )


def add_tension(
    raw: dict[str, object],
    content_cipher: AesGcmContentCipher,
    *,
    ordinal: int,
) -> UUID:
    insight_id = uuid4()
    payload = {
        "version": 1,
        "pattern_type": "inner_tension",
        "structure": {
            "left_need": "autonomy",
            "right_need": "security",
            "left_statement": "You may value room to choose.",
            "right_statement": "You may also value a stable base.",
            "integration": "A small reversible choice may honor both needs.",
            "left_support_signal_ids": [str(uuid4())],
            "right_support_signal_ids": [str(uuid4())],
            "left_supporting_entries": 2,
            "right_supporting_entries": 2,
            "distinct_dates": 3,
        },
    }
    rows = raw["insights"]
    assert isinstance(rows, list)
    if ordinal == 0:
        rows[2] = {
            "id": str(insight_id),
            "pattern_type": "inner_tension",
            "ordinal": ordinal,
            "status": "available",
            "payload_envelope": content_cipher.encrypt_json(
                payload,
                user_id=USER_ID,
                record_id=insight_id,
                purpose="reflection_insight_payload",
            ),
            "confidence_label": "preliminary",
            "score": 0.71,
        }
    else:
        rows.append(
            {
                "id": str(insight_id),
                "pattern_type": "inner_tension",
                "ordinal": ordinal,
                "status": "available",
                "payload_envelope": content_cipher.encrypt_json(
                    payload,
                    user_id=USER_ID,
                    record_id=insight_id,
                    purpose="reflection_insight_payload",
                ),
                "confidence_label": "emerging",
                "score": 0.76,
            }
        )
    return insight_id


def build_app(
    raw: dict[str, object],
    *,
    reflections_enabled: bool = True,
    allowed_user_ids: set[UUID] | None = None,
):
    content_cipher = cipher()
    repository = Repository(raw)
    provider = Provider()
    sessions = DatabaseSessions(None, None, lambda: Session(), None)  # type: ignore[arg-type]
    app = create_app(
        settings=settings(reflections_enabled=reflections_enabled),
        database_sessions=sessions,
        token_verifier=Verifier(),
        reflection_provider=provider,
        content_cipher=content_cipher,
    )
    app.state.reflections_service = ReflectionsService(
        repository=repository,  # type: ignore[arg-type]
        cipher=content_cipher,
        enabled=reflections_enabled,
        allowed_user_ids={USER_ID} if allowed_user_ids is None else allowed_user_ids,
    )
    return app, repository, provider, content_cipher


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/api/v1/reflections?range=all", None),
        (
            "PUT",
            f"/api/v1/reflections/{SNAPSHOT_ID}/insights/{uuid4()}/feedback",
            {"response": "resonates"},
        ),
    ],
)
def test_disabled_reflection_operations_are_opaque_no_store_and_side_effect_free(
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    app, repository, provider, _content_cipher = build_app(
        raw_with_snapshot(), reflections_enabled=False
    )

    with TestClient(app) as client:
        response = client.request(method, path, headers=HEADERS, json=payload)

    assert response.status_code == 503
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {
        "error_code": "SERVICE_UNAVAILABLE",
        "message": "The service is temporarily unavailable.",
        "details": {},
        "request_id": response.json()["request_id"],
    }
    assert repository.read_users == []
    assert repository.feedback_calls == []
    assert provider.calls == []


def test_out_of_cohort_reflection_operations_match_disabled_behavior() -> None:
    app, repository, provider, _content_cipher = build_app(
        raw_with_snapshot(), allowed_user_ids={OTHER_ID}
    )
    with TestClient(app) as client:
        read = client.get("/api/v1/reflections?range=7d", headers=HEADERS)
        feedback = client.put(
            f"/api/v1/reflections/{SNAPSHOT_ID}/insights/{uuid4()}/feedback",
            headers=HEADERS,
            json={"response": "resonates"},
        )
    for response in (read, feedback):
        assert response.status_code == 503
        assert response.headers["cache-control"] == "private, no-store"
        assert response.json()["error_code"] == "SERVICE_UNAVAILABLE"
    assert repository.read_users == []
    assert repository.feedback_calls == []
    assert provider.calls == []


@pytest.mark.parametrize("selected_range", ["7d", "30d", "all"])
def test_aggregate_read_is_authenticated_owner_scoped_bounded_and_llm_free(
    selected_range: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = raw_with_snapshot()
    app, repository, provider, content_cipher = build_app(raw)
    insight_id = add_available_hidden(raw, content_cipher)
    add_evidence(raw, content_cipher, insight_id=insight_id)
    with TestClient(app) as client:
        unauthenticated = client.get(f"/api/v1/reflections?range={selected_range}")
        response = client.get(
            f"/api/v1/reflections?range={selected_range}", headers=HEADERS
        )
    assert unauthenticated.status_code == 401
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert body["range"] == selected_range
    assert body["reflectionState"] == "available"
    assert body["processingState"] == "idle"
    assert body["snapshot"] == {
        "id": str(SNAPSHOT_ID),
        "version": 4,
        "generatedAt": "2026-07-21T12:35:00Z",
        "sourceVersion": 10,
        "isStale": False,
    }
    assert body["data"]["hiddenDriver"]["id"] == str(insight_id)
    assert body["data"]["hiddenDriver"]["status"] == "available"
    assert body["data"]["hiddenDriver"]["evidence"][0] == {
        "id": body["data"]["hiddenDriver"]["evidence"][0]["id"],
        "entryDate": "2026-07-20",
        "sourceLabel": "Journal entry",
        "quote": "felt capable",
        "interpretation": "Completing something may reinforce a sense of competence.",
        "theme": "career",
        "supports": "Supporting evidence",
    }
    assert set(body["data"]) == {"hiddenDriver", "recurringLoop", "innerTensions"}
    assert body["analysisBasis"]["window"] == "90d"
    if selected_range == "all":
        assert body["analysisBasis"]["currentRangeFrom"] == "2026-04-23"
    assert "userId" not in response.text
    assert "source_start" not in response.text
    assert "payload_envelope" not in response.text
    assert repository.read_users == [USER_ID]
    assert provider.calls == []
    assert "felt capable" not in caplog.text
    assert "Completing something may reinforce" not in caplog.text


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/reflections",
        "/api/v1/reflections?range=90d",
        f"/api/v1/reflections?range=7d&userId={OTHER_ID}",
        "/api/v1/reflections?range=7d&reflectionTab=hiddenDriver",
    ],
)
def test_read_rejects_missing_invalid_and_client_owned_query_fields(url: str) -> None:
    app, _repository, provider, _cipher = build_app(raw_with_snapshot())
    with TestClient(app) as client:
        response = client.get(url, headers=HEADERS)
    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"
    assert response.headers["cache-control"] == "private, no-store"
    assert provider.calls == []


def test_first_pending_garbage_only_and_terminal_failure_states() -> None:
    pending_raw = raw_without_snapshot(valid=2)
    pending_raw["job"] = {"status": "running"}
    pending_app, _, _, _ = build_app(pending_raw)
    garbage_app, _, _, _ = build_app(raw_without_snapshot(excluded=10))
    failed_raw = raw_without_snapshot(valid=3)
    failed_raw["state"]["last_processing_error_code"] = "PROVIDER_UNAVAILABLE"  # type: ignore[index]
    failed_raw["job"] = {"status": "failed"}
    failed_app, _, _, _ = build_app(failed_raw)
    with TestClient(pending_app) as client:
        pending = client.get("/api/v1/reflections?range=7d", headers=HEADERS)
    with TestClient(garbage_app) as client:
        garbage = client.get("/api/v1/reflections?range=30d", headers=HEADERS)
    with TestClient(failed_app) as client:
        failed = client.get("/api/v1/reflections?range=all", headers=HEADERS)
    assert (pending.status_code, pending.json()["reflectionState"], pending.json()["processingState"]) == (
        200,
        "first_reflection_pending",
        "pending",
    )
    assert pending.json()["snapshot"] is None
    assert all(
        value["status"] == "insufficient_evidence"
        for value in pending.json()["data"].values()
    )
    assert garbage.status_code == 200
    assert garbage.json()["reflectionState"] == "insufficient_reflective_content"
    assert garbage.json()["analysisBasis"]["excludedReasons"] == {
        "test_or_noise": 10
    }
    assert failed.status_code == 503
    assert failed.json()["details"] == {
        "reflectionState": "technical_failure",
        "processingState": "failed",
    }
    assert "PROVIDER_UNAVAILABLE" not in failed.text


@pytest.mark.parametrize(
    ("job", "latest", "expected_processing"),
    [({"status": "pending"}, 11, "pending"), ({"status": "failed"}, 10, "failed")],
)
def test_stale_snapshot_is_preserved_for_pending_or_failed_refresh(
    job: dict[str, object], latest: int, expected_processing: str
) -> None:
    raw = raw_with_snapshot()
    raw["job"] = job
    raw["state"]["latest_accepted_source_version"] = latest  # type: ignore[index]
    if expected_processing == "failed":
        raw["state"]["last_processing_error_code"] = "SYNTHESIS_FAILED"  # type: ignore[index]
    app, _, _, _ = build_app(raw)
    with TestClient(app) as client:
        response = client.get("/api/v1/reflections?range=7d", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["reflectionState"] == "stale"
    assert response.json()["processingState"] == expected_processing
    assert response.json()["snapshot"]["id"] == str(SNAPSHOT_ID)
    assert response.json()["snapshot"]["isStale"] is True
    assert "SYNTHESIS_FAILED" not in response.text


def test_zero_one_and_multiple_inner_tensions_use_strict_section_union() -> None:
    zero_app, _, _, _ = build_app(raw_with_snapshot())
    one_raw = raw_with_snapshot()
    one_app, _, _, one_cipher = build_app(one_raw)
    add_tension(one_raw, one_cipher, ordinal=0)
    many_raw = raw_with_snapshot()
    many_app, _, _, many_cipher = build_app(many_raw)
    add_tension(many_raw, many_cipher, ordinal=0)
    add_tension(many_raw, many_cipher, ordinal=1)
    responses = []
    for app in (zero_app, one_app, many_app):
        with TestClient(app) as client:
            responses.append(
                client.get("/api/v1/reflections?range=all", headers=HEADERS).json()
            )
    assert responses[0]["data"]["innerTensions"]["status"] == "insufficient_evidence"
    assert len(responses[1]["data"]["innerTensions"]["tensions"]) == 1
    assert len(responses[2]["data"]["innerTensions"]["tensions"]) == 2


def test_feedback_create_repeat_replace_restore_and_opaque_not_found_are_llm_free() -> None:
    raw = raw_with_snapshot()
    app, repository, provider, content_cipher = build_app(raw)
    insight_id = add_available_hidden(raw, content_cipher)
    url = f"/api/v1/reflections/{SNAPSHOT_ID}/insights/{insight_id}/feedback"
    with TestClient(app) as client:
        created = client.put(url, headers=HEADERS, json={"response": "resonates"})
        repeated = client.put(url, headers=HEADERS, json={"response": "resonates"})
        replaced = client.put(url, headers=HEADERS, json={"response": "rejected"})
        restored = client.get("/api/v1/reflections?range=all", headers=HEADERS)
        invalid = client.put(url, headers=HEADERS, json={"response": "yes"})
        repository.not_found = True
        missing = client.put(
            f"/api/v1/reflections/{OTHER_ID}/insights/{insight_id}/feedback",
            headers=HEADERS,
            json={"response": "partly"},
        )
    assert created.status_code == repeated.status_code == replaced.status_code == 200
    assert created.headers["cache-control"] == "private, no-store"
    assert replaced.json() == {
        "snapshotId": str(SNAPSHOT_ID),
        "insightId": str(insight_id),
        "response": "rejected",
        "updatedAt": "2026-07-21T12:42:00Z",
    }
    assert restored.json()["data"]["hiddenDriver"]["feedback"] == "rejected"
    assert invalid.status_code == 422
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "NOT_FOUND"
    assert len(repository.feedback_calls) == 3
    assert all(item["user_id"] == USER_ID for item in repository.feedback_calls)
    assert provider.calls == []


def test_public_unions_and_feedback_body_reject_unknown_values_and_fields() -> None:
    with pytest.raises(ValidationError):
        InsufficientInsight.model_validate(
            {
                "status": "unknown",
                "reasonCode": "LOOP_NOT_REPEATED",
                "message": "safe",
            }
        )
    with pytest.raises(ValidationError):
        AvailableHiddenDriver.model_validate(
            {
                "status": "available",
                "id": str(uuid4()),
                "confidence": "certain",
                "score": 0.7,
                "statement": "A possible pattern.",
                "underlyingNeed": "clarity",
                "drivers": [],
                "evidence": [],
                "feedback": None,
            }
        )
    with pytest.raises(ValidationError):
        FeedbackRequest.model_validate({"response": "resonates", "userId": str(USER_ID)})
