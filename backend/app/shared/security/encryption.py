from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import re
import unicodedata
from typing import Literal, NoReturn, Protocol, TypeAlias, cast
from uuid import UUID

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

from app.shared.config.settings import Settings


class ContentUnavailableError(ValueError):
    pass


EnvelopePurpose: TypeAlias = Literal[
    "pii_vault",
    "entry_redacted_text",
    "entry_offset_map",
    "entry_signal_payload",
    "reflection_candidate_payload",
    "reflection_insight_payload",
    "review_item_statement",
    "review_item_source_quote",
    "review_item_corrected_statement",
    "review_item_feedback_note",
]
ReflectionFingerprintPurpose: TypeAlias = Literal[
    "entry_duplicate",
    "token_trigram",
    "signal_label",
    "safety_identifier",
    "candidate_canonical",
    "review_feedback_correction",
    "review_feedback_note",
]

ENVELOPE_PURPOSES = frozenset(
    {
        "pii_vault",
        "entry_redacted_text",
        "entry_offset_map",
        "entry_signal_payload",
        "reflection_candidate_payload",
        "reflection_insight_payload",
        "review_item_statement",
        "review_item_source_quote",
        "review_item_corrected_statement",
        "review_item_feedback_note",
    }
)


class ContentCipher(Protocol):
    def canonicalize(self, plaintext: str) -> str: ...

    def encrypt(self, plaintext: str, *, user_id: UUID, record_id: UUID) -> dict: ...

    def decrypt(self, envelope: dict, *, user_id: UUID, record_id: UUID) -> str: ...

    def draft_fingerprint(self, plaintext: str, *, user_id: UUID) -> tuple[str, str]: ...

    def past_fingerprint(
        self, plaintext: str, *, user_id: UUID, entry_date: str
    ) -> tuple[str, str]: ...

    def encrypt_json(
        self,
        value: object,
        *,
        user_id: UUID,
        record_id: UUID,
        purpose: EnvelopePurpose,
    ) -> dict: ...

    def decrypt_json(
        self,
        envelope: dict,
        *,
        user_id: UUID,
        record_id: UUID,
        purpose: EnvelopePurpose,
    ) -> object: ...

    def entity_fingerprint(
        self, value: str, *, user_id: UUID, entity_type: str
    ) -> tuple[str, str]: ...

    def reflection_fingerprint(
        self,
        value: str,
        *,
        user_id: UUID,
        purpose: ReflectionFingerprintPurpose,
    ) -> tuple[str, str]: ...

    def reflection_fingerprints(
        self,
        value: str,
        *,
        user_id: UUID,
        purpose: ReflectionFingerprintPurpose,
    ) -> tuple[tuple[str, str], ...]: ...


class AesGcmContentCipher:
    ENVELOPE_KEYS = {
        "version",
        "algorithm",
        "key_id",
        "kdf",
        "salt",
        "nonce",
        "ciphertext",
        "tag",
    }
    EDGE_WHITESPACE = "\t\n\v\f\r "
    MAX_GENERIC_JSON_BYTES = 700_000

    def __init__(
        self,
        *,
        encryption_keys: dict[str, bytes],
        active_encryption_key_id: str,
        fingerprint_keys: dict[str, bytes],
        active_fingerprint_key_id: str,
    ) -> None:
        if encryption_keys.get(active_encryption_key_id) is None:
            raise ValueError("active encryption key is unavailable")
        if fingerprint_keys.get(active_fingerprint_key_id) is None:
            raise ValueError("active fingerprint key is unavailable")
        if any(len(value) != 32 for value in (*encryption_keys.values(), *fingerprint_keys.values())):
            raise ValueError("all content keys must be 32 bytes")
        self._encryption_keys = dict(encryption_keys)
        self._active_encryption_key_id = active_encryption_key_id
        self._fingerprint_keys = dict(fingerprint_keys)
        self._active_fingerprint_key_id = active_fingerprint_key_id

    @classmethod
    def from_settings(cls, settings: Settings) -> "AesGcmContentCipher":
        return cls(
            encryption_keys=_decode_key_map(settings.ENTRY_ENCRYPTION_KEYS.get_secret_value()),
            active_encryption_key_id=settings.ENTRY_ENCRYPTION_ACTIVE_KEY_ID,
            fingerprint_keys=_decode_key_map(settings.ENTRY_FINGERPRINT_KEYS.get_secret_value()),
            active_fingerprint_key_id=settings.ENTRY_FINGERPRINT_ACTIVE_KEY_ID,
        )

    def canonicalize(self, plaintext: str) -> str:
        if unicodedata.unidata_version != "14.0.0" or not isinstance(plaintext, str):
            raise ValueError("invalid entry content")
        value = unicodedata.normalize(
            "NFC", plaintext.replace("\r\n", "\n").replace("\r", "\n")
        ).strip(self.EDGE_WHITESPACE)
        if not value or len(value) > 200_000:
            raise ValueError("invalid entry content")
        value.encode("utf-8", errors="strict")
        return value

    @staticmethod
    def _derive(master_key: bytes, salt: bytes) -> bytes:
        pseudorandom_key = hmac.new(salt, master_key, hashlib.sha256).digest()
        return hmac.new(
            pseudorandom_key,
            b"orion/entry-content/v2\x01",
            hashlib.sha256,
        ).digest()

    @staticmethod
    def _aad(*, key_id: str, user_id: UUID, record_id: UUID) -> bytes:
        return "\n".join(
            (
                "orion-entry-envelope",
                "version=2",
                "algorithm=AES-256-GCM",
                "kdf=HKDF-SHA256",
                f"key_id={key_id}",
                f"user_id={user_id}",
                f"entry_id={record_id}",
                "field=content",
            )
        ).encode("utf-8")

    def encrypt(self, plaintext: str, *, user_id: UUID, record_id: UUID) -> dict:
        canonical = self.canonicalize(plaintext).encode("utf-8")
        key_id = self._active_encryption_key_id
        salt = get_random_bytes(32)
        nonce = get_random_bytes(12)
        cipher = AES.new(self._derive(self._encryption_keys[key_id], salt), AES.MODE_GCM, nonce=nonce)
        cipher.update(self._aad(key_id=key_id, user_id=user_id, record_id=record_id))
        ciphertext, tag = cipher.encrypt_and_digest(canonical)
        return {
            "version": 2,
            "algorithm": "AES-256-GCM",
            "key_id": key_id,
            "kdf": "HKDF-SHA256",
            "salt": _encode(salt),
            "nonce": _encode(nonce),
            "ciphertext": _encode(ciphertext),
            "tag": _encode(tag),
        }

    def decrypt(self, envelope: dict, *, user_id: UUID, record_id: UUID) -> str:
        try:
            if not isinstance(envelope, dict) or set(envelope) != self.ENVELOPE_KEYS:
                raise ValueError
            if (
                envelope["version"] != 2
                or isinstance(envelope["version"], bool)
                or envelope["algorithm"] != "AES-256-GCM"
                or envelope["kdf"] != "HKDF-SHA256"
            ):
                raise ValueError
            key_id = envelope["key_id"]
            master = self._encryption_keys[key_id]
            salt = _decode(envelope["salt"], length=32)
            nonce = _decode(envelope["nonce"], length=12)
            ciphertext = _decode(envelope["ciphertext"])
            tag = _decode(envelope["tag"], length=16)
            if not ciphertext:
                raise ValueError
            cipher = AES.new(self._derive(master, salt), AES.MODE_GCM, nonce=nonce)
            cipher.update(self._aad(key_id=key_id, user_id=user_id, record_id=record_id))
            return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8", errors="strict")
        except Exception as exc:
            raise ContentUnavailableError("entry content is unavailable") from exc

    def draft_fingerprint(self, plaintext: str, *, user_id: UUID) -> tuple[str, str]:
        return self._fingerprint(
            b"orion/entry-draft-fingerprint/v1",
            self.canonicalize(plaintext).encode("utf-8"),
            user_id,
        )

    def past_fingerprint(
        self, plaintext: str, *, user_id: UUID, entry_date: str
    ) -> tuple[str, str]:
        canonical = self.canonicalize(plaintext).encode("utf-8")
        return self._fingerprint(
            b"orion/past-entry-import/v1",
            entry_date.encode("ascii") + b"\n" + canonical,
            user_id,
        )

    def _fingerprint(self, domain: bytes, value: bytes, user_id: UUID) -> tuple[str, str]:
        key_id = self._active_fingerprint_key_id
        payload = b"\n".join((domain, str(user_id).encode("ascii"), value))
        digest = hmac.new(self._fingerprint_keys[key_id], payload, hashlib.sha256).hexdigest()
        return key_id, digest

    @staticmethod
    def _derive_generic(master_key: bytes, salt: bytes) -> bytes:
        pseudorandom_key = hmac.new(salt, master_key, hashlib.sha256).digest()
        return hmac.new(
            pseudorandom_key,
            b"orion/generic-json/v1\x01",
            hashlib.sha256,
        ).digest()

    @staticmethod
    def _generic_aad(
        *,
        key_id: str,
        user_id: UUID,
        record_id: UUID,
        purpose: EnvelopePurpose,
    ) -> bytes:
        return "\n".join(
            (
                "orion-json-envelope",
                "version=1",
                "algorithm=AES-256-GCM",
                "kdf=HKDF-SHA256",
                f"key_id={key_id}",
                f"user_id={user_id}",
                f"record_id={record_id}",
                f"purpose={purpose}",
            )
        ).encode("utf-8")

    def encrypt_json(
        self,
        value: object,
        *,
        user_id: UUID,
        record_id: UUID,
        purpose: EnvelopePurpose,
    ) -> dict:
        validated_purpose = _validate_purpose(purpose)
        plaintext = _canonical_json_bytes(value, maximum=self.MAX_GENERIC_JSON_BYTES)
        key_id = self._active_encryption_key_id
        salt = get_random_bytes(32)
        nonce = get_random_bytes(12)
        cipher = AES.new(
            self._derive_generic(self._encryption_keys[key_id], salt),
            AES.MODE_GCM,
            nonce=nonce,
        )
        cipher.update(
            self._generic_aad(
                key_id=key_id,
                user_id=user_id,
                record_id=record_id,
                purpose=validated_purpose,
            )
        )
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        return {
            "version": 1,
            "algorithm": "AES-256-GCM",
            "key_id": key_id,
            "kdf": "HKDF-SHA256",
            "salt": _encode(salt),
            "nonce": _encode(nonce),
            "ciphertext": _encode(ciphertext),
            "tag": _encode(tag),
        }

    def decrypt_json(
        self,
        envelope: dict,
        *,
        user_id: UUID,
        record_id: UUID,
        purpose: EnvelopePurpose,
    ) -> object:
        try:
            validated_purpose = _validate_purpose(purpose)
            if not isinstance(envelope, dict) or set(envelope) != self.ENVELOPE_KEYS:
                raise ValueError
            if (
                envelope["version"] != 1
                or isinstance(envelope["version"], bool)
                or envelope["algorithm"] != "AES-256-GCM"
                or envelope["kdf"] != "HKDF-SHA256"
            ):
                raise ValueError
            key_id = envelope["key_id"]
            master = self._encryption_keys[key_id]
            salt = _decode(envelope["salt"], length=32)
            nonce = _decode(envelope["nonce"], length=12)
            ciphertext = _decode(envelope["ciphertext"])
            tag = _decode(envelope["tag"], length=16)
            if not ciphertext or len(ciphertext) > self.MAX_GENERIC_JSON_BYTES:
                raise ValueError
            cipher = AES.new(self._derive_generic(master, salt), AES.MODE_GCM, nonce=nonce)
            cipher.update(
                self._generic_aad(
                    key_id=key_id,
                    user_id=user_id,
                    record_id=record_id,
                    purpose=validated_purpose,
                )
            )
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
            decoded = plaintext.decode("utf-8", errors="strict")
            value = json.loads(decoded)
            if _canonical_json_bytes(value, maximum=self.MAX_GENERIC_JSON_BYTES) != plaintext:
                raise ValueError
            return value
        except Exception as exc:
            raise ContentUnavailableError("encrypted data is unavailable") from exc

    def entity_fingerprint(
        self, value: str, *, user_id: UUID, entity_type: str
    ) -> tuple[str, str]:
        if (
            not isinstance(value, str)
            or not value
            or not isinstance(entity_type, str)
            or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", entity_type)
        ):
            raise ValueError("invalid entity fingerprint input")
        return self._fingerprint(
            b"orion/pii-entity-fingerprint/v1\n" + entity_type.encode("ascii"),
            value.encode("utf-8", errors="strict"),
            user_id,
        )

    def reflection_fingerprint(
        self,
        value: str,
        *,
        user_id: UUID,
        purpose: ReflectionFingerprintPurpose,
    ) -> tuple[str, str]:
        return self.reflection_fingerprints(
            value,
            user_id=user_id,
            purpose=purpose,
        )[0]

    def reflection_fingerprints(
        self,
        value: str,
        *,
        user_id: UUID,
        purpose: ReflectionFingerprintPurpose,
    ) -> tuple[tuple[str, str], ...]:
        if (
            not isinstance(value, str)
            or not value
            or purpose
            not in {
                "entry_duplicate",
                "token_trigram",
                "signal_label",
                "safety_identifier",
                "candidate_canonical",
                "review_feedback_correction",
                "review_feedback_note",
            }
        ):
            raise ValueError("invalid reflection fingerprint input")
        domain = b"orion/reflection-fingerprint/v1\n" + purpose.encode("ascii")
        encoded = value.encode("utf-8", errors="strict")
        key_ids = (
            self._active_fingerprint_key_id,
            *sorted(
                key_id
                for key_id in self._fingerprint_keys
                if key_id != self._active_fingerprint_key_id
            ),
        )
        payload = b"\n".join((domain, str(user_id).encode("ascii"), encoded))
        return tuple(
            (
                key_id,
                hmac.new(
                    self._fingerprint_keys[key_id],
                    payload,
                    hashlib.sha256,
                ).hexdigest(),
            )
            for key_id in key_ids
        )


class UnavailableContentCipher:
    def __getattr__(self, _name: str) -> NoReturn:
        raise RuntimeError("content encryption is unavailable")


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: object, *, length: int | None = None) -> bytes:
    if not isinstance(value, str):
        raise ValueError
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError from exc
    if _encode(decoded) != value or (length is not None and len(decoded) != length):
        raise ValueError
    return decoded


def _decode_key_map(serialized: str) -> dict[str, bytes]:
    parsed = json.loads(serialized)
    if not isinstance(parsed, dict):
        raise ValueError("key map must be an object")
    return {str(key): _decode(value, length=32) for key, value in parsed.items()}


def _validate_purpose(value: object) -> EnvelopePurpose:
    if not isinstance(value, str) or value not in ENVELOPE_PURPOSES:
        raise ValueError("invalid encryption purpose")
    return cast(EnvelopePurpose, value)


def _reject_nonfinite(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        for item in value.values():
            _reject_nonfinite(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_nonfinite(item)


def _canonical_json_bytes(value: object, *, maximum: int) -> bytes:
    _reject_nonfinite(value)
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("value is not canonical JSON") from exc
    if not encoded or len(encoded) > maximum:
        raise ValueError("JSON payload is too large")
    return encoded
