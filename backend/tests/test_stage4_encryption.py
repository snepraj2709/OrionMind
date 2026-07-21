from __future__ import annotations

import unicodedata
from uuid import UUID

import pytest

from app.modules.entries.schemas import EntryDraftUpdate, TextEntryCreate
from app.shared.security.encryption import AesGcmContentCipher, ContentUnavailableError


USER = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
RECORD = UUID("33333333-3333-4333-8333-333333333333")


def cipher() -> AesGcmContentCipher:
    return AesGcmContentCipher(
        encryption_keys={"entry-key": b"e" * 32},
        active_encryption_key_id="entry-key",
        fingerprint_keys={"fingerprint-key": b"f" * 32},
        active_fingerprint_key_id="fingerprint-key",
    )


def test_canonicalization_is_exact_lf_nfc_and_frozen_edge_trim() -> None:
    service = cipher()
    decomposed = "Cafe\u0301"
    assert service.canonicalize(f" \t{decomposed}\r\nline\r ") == "Café\nline"
    assert service.canonicalize("\u00a0content\u00a0") == "\u00a0content\u00a0"
    assert unicodedata.unidata_version == "14.0.0"
    with pytest.raises(ValueError):
        service.canonicalize(" \t\r\n")
    assert len(service.canonicalize("x" * 200_000)) == 200_000
    with pytest.raises(ValueError):
        service.canonicalize("x" * 200_001)


def test_envelope_round_trip_and_uniform_authentication_failure() -> None:
    service = cipher()
    plaintext = "Private journal text"
    envelope = service.encrypt(plaintext, user_id=USER, record_id=RECORD)
    assert set(envelope) == service.ENVELOPE_KEYS
    assert envelope["version"] == 2
    assert plaintext not in str(envelope)
    assert service.decrypt(envelope, user_id=USER, record_id=RECORD) == plaintext
    variants = [
        (envelope, OTHER, RECORD),
        (envelope, USER, OTHER),
        ({**envelope, "tag": "AAAAAAAAAAAAAAAAAAAAAA=="}, USER, RECORD),
        ({**envelope, "key_id": "missing"}, USER, RECORD),
        ({**envelope, "extra": "value"}, USER, RECORD),
    ]
    for value, user_id, record_id in variants:
        with pytest.raises(ContentUnavailableError, match="entry content is unavailable"):
            service.decrypt(value, user_id=user_id, record_id=record_id)


def test_fingerprints_are_deterministic_owner_and_date_scoped() -> None:
    service = cipher()
    first = service.draft_fingerprint("same", user_id=USER)
    assert first == service.draft_fingerprint(" same ", user_id=USER)
    assert first != service.draft_fingerprint("same", user_id=OTHER)
    assert service.past_fingerprint("same", user_id=USER, entry_date="2026-01-01") != service.past_fingerprint(
        "same", user_id=USER, entry_date="2026-01-02"
    )


def test_entry_request_dtos_forbid_ownership_and_operational_fields() -> None:
    assert EntryDraftUpdate.model_validate({"content": ""}).content == ""
    assert TextEntryCreate.model_validate({"content": "entry"}).content == "entry"
    for payload in (
        {"content": "entry", "user_id": str(USER)},
        {"content": "entry", "entry_id": str(RECORD)},
        {"content": "entry", "entry_date": "2026-01-01"},
        {"content": "entry", "processing_token": str(RECORD)},
    ):
        with pytest.raises(Exception):
            TextEntryCreate.model_validate(payload)
