from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, Sequence
from uuid import UUID

from app.shared.security.encryption import ContentCipher


SUPPORTED_ENTITY_TYPES = frozenset(
    {
        "PERSON",
        "ORGANIZATION",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "STREET_ADDRESS",
        "LOCATION",
        "IP_ADDRESS",
        "URL",
        "IBAN_CODE",
        "CREDIT_CARD",
        "US_BANK_NUMBER",
        "ORION_ACCOUNT_IDENTIFIER",
        "ORION_IDENTIFIER",
    }
)
PLACEHOLDER_TYPE_BY_ENTITY = {
    "PERSON": "PERSON",
    "ORGANIZATION": "ORG",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "STREET_ADDRESS": "ADDRESS",
    "LOCATION": "LOCATION",
    "IP_ADDRESS": "IP",
    "URL": "URL",
    "IBAN_CODE": "FINANCIAL",
    "CREDIT_CARD": "FINANCIAL",
    "US_BANK_NUMBER": "FINANCIAL",
    "ORION_ACCOUNT_IDENTIFIER": "ACCOUNT",
    "ORION_IDENTIFIER": "IDENTIFIER",
}
PLACEHOLDER = re.compile(r"^<[A-Z][A-Z0-9_]*_[1-9][0-9]*>$")
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class DetectedEntity:
    entity_type: str
    start: int
    end: int
    score: float

    def __post_init__(self) -> None:
        if (
            self.entity_type not in SUPPORTED_ENTITY_TYPES
            or self.start < 0
            or self.end <= self.start
            or not math.isfinite(self.score)
            or not 0 <= self.score <= 1
        ):
            raise ValueError("invalid detected entity")


class EntityAnalyzer(Protocol):
    def detect(self, text: str) -> Sequence[DetectedEntity]: ...


class PresidioEntityAnalyzer:
    def __init__(self, analyzer) -> None:
        self._analyzer = analyzer

    @classmethod
    def from_local_model(cls) -> "PresidioEntityAnalyzer":
        from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            }
        )
        analyzer = AnalyzerEngine(
            nlp_engine=provider.create_engine(),
            supported_languages=["en"],
        )
        analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="STREET_ADDRESS",
                supported_language="en",
                patterns=[
                    Pattern(
                        "street address",
                        r"\b\d{1,6}\s+(?:[A-Za-z0-9.'-]+\s+){0,6}"
                        r"(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Boulevard|Blvd|"
                        r"Drive|Dr|Way|Court|Ct)\b\.?,?",
                        0.55,
                    )
                ],
            )
        )
        analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="ORION_ACCOUNT_IDENTIFIER",
                supported_language="en",
                patterns=[
                    Pattern(
                        "account identifier",
                        r"(?i)\b(?:account|acct|customer|member)\s*"
                        r"(?:number|no\.?|id)?\s*[:#-]?\s*[A-Z0-9][A-Z0-9-]{3,}\b",
                        0.65,
                    )
                ],
            )
        )
        analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="ORION_IDENTIFIER",
                supported_language="en",
                patterns=[
                    Pattern(
                        "UUID identifier",
                        r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
                        r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
                        0.7,
                    )
                ],
            )
        )
        return cls(analyzer)

    def detect(self, text: str) -> tuple[DetectedEntity, ...]:
        results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=sorted(SUPPORTED_ENTITY_TYPES),
            score_threshold=0.35,
        )
        return tuple(
            DetectedEntity(
                entity_type=str(item.entity_type),
                start=int(item.start),
                end=int(item.end),
                score=float(item.score),
            )
            for item in results
            if str(item.entity_type) in SUPPORTED_ENTITY_TYPES
        )


@dataclass(frozen=True, slots=True)
class VaultEntry:
    entity_type: str
    placeholder_type: str
    placeholder: str
    canonical_original: str
    fingerprint_key_id: str

    def to_payload(self) -> dict[str, str]:
        return {
            "entity_type": self.entity_type,
            "placeholder_type": self.placeholder_type,
            "placeholder": self.placeholder,
            "canonical_original": self.canonical_original,
            "fingerprint_key_id": self.fingerprint_key_id,
        }

    @classmethod
    def from_payload(cls, value: object) -> "VaultEntry":
        if not isinstance(value, dict) or set(value) != {
            "entity_type",
            "placeholder_type",
            "placeholder",
            "canonical_original",
            "fingerprint_key_id",
        }:
            raise ValueError("invalid PII vault entry")
        entry = cls(
            entity_type=_required_string(value["entity_type"], maximum=64),
            placeholder_type=_required_string(value["placeholder_type"], maximum=64),
            placeholder=_required_string(value["placeholder"], maximum=100),
            canonical_original=_required_string(value["canonical_original"], maximum=4000),
            fingerprint_key_id=_required_string(value["fingerprint_key_id"], maximum=64),
        )
        if (
            entry.entity_type not in SUPPORTED_ENTITY_TYPES
            or PLACEHOLDER_TYPE_BY_ENTITY[entry.entity_type] != entry.placeholder_type
            or PLACEHOLDER.fullmatch(entry.placeholder) is None
        ):
            raise ValueError("invalid PII vault entry")
        return entry


@dataclass(frozen=True, slots=True)
class PiiVault:
    entries: dict[str, VaultEntry]
    next_indices: dict[str, int]

    @classmethod
    def empty(cls) -> "PiiVault":
        return cls(entries={}, next_indices={})

    def to_payload(self) -> dict[str, object]:
        return {
            "version": 1,
            "entries": {
                fingerprint: entry.to_payload()
                for fingerprint, entry in sorted(self.entries.items())
            },
            "next_indices": dict(sorted(self.next_indices.items())),
        }

    @classmethod
    def from_payload(cls, value: object) -> "PiiVault":
        if not isinstance(value, dict) or set(value) != {
            "version",
            "entries",
            "next_indices",
        }:
            raise ValueError("invalid PII vault")
        if value["version"] != 1 or isinstance(value["version"], bool):
            raise ValueError("invalid PII vault")
        raw_entries = value["entries"]
        raw_indices = value["next_indices"]
        if not isinstance(raw_entries, dict) or not isinstance(raw_indices, dict):
            raise ValueError("invalid PII vault")
        if len(raw_entries) > 10_000 or len(raw_indices) > len(PLACEHOLDER_TYPE_BY_ENTITY):
            raise ValueError("invalid PII vault")
        entries: dict[str, VaultEntry] = {}
        for fingerprint, raw_entry in raw_entries.items():
            if not isinstance(fingerprint, str) or FINGERPRINT.fullmatch(fingerprint) is None:
                raise ValueError("invalid PII vault")
            entries[fingerprint] = VaultEntry.from_payload(raw_entry)
        indices: dict[str, int] = {}
        allowed_placeholder_types = set(PLACEHOLDER_TYPE_BY_ENTITY.values())
        for placeholder_type, raw_index in raw_indices.items():
            if (
                placeholder_type not in allowed_placeholder_types
                or isinstance(raw_index, bool)
                or not isinstance(raw_index, int)
                or raw_index < 1
                or raw_index > 1_000_000
            ):
                raise ValueError("invalid PII vault")
            indices[placeholder_type] = raw_index
        for entry in entries.values():
            placeholder_index = int(entry.placeholder.rsplit("_", 1)[1][:-1])
            if indices.get(entry.placeholder_type, 1) <= placeholder_index:
                raise ValueError("invalid PII vault")
        return cls(entries=entries, next_indices=indices)


@dataclass(frozen=True, slots=True)
class OffsetReplacement:
    original_start: int
    original_end: int
    redacted_start: int
    redacted_end: int
    placeholder: str

    def to_payload(self) -> dict[str, object]:
        return {
            "original_start": self.original_start,
            "original_end": self.original_end,
            "redacted_start": self.redacted_start,
            "redacted_end": self.redacted_end,
            "placeholder": self.placeholder,
        }

    @classmethod
    def from_payload(cls, value: object) -> "OffsetReplacement":
        if not isinstance(value, dict) or set(value) != {
            "original_start",
            "original_end",
            "redacted_start",
            "redacted_end",
            "placeholder",
        }:
            raise ValueError("invalid offset replacement")
        replacement = cls(
            original_start=_required_integer(value["original_start"]),
            original_end=_required_integer(value["original_end"]),
            redacted_start=_required_integer(value["redacted_start"]),
            redacted_end=_required_integer(value["redacted_end"]),
            placeholder=_required_string(value["placeholder"], maximum=100),
        )
        if (
            replacement.original_start < 0
            or replacement.original_end <= replacement.original_start
            or replacement.redacted_start < 0
            or replacement.redacted_end <= replacement.redacted_start
            or replacement.redacted_end - replacement.redacted_start
            != len(replacement.placeholder)
            or PLACEHOLDER.fullmatch(replacement.placeholder) is None
        ):
            raise ValueError("invalid offset replacement")
        return replacement


@dataclass(frozen=True, slots=True)
class TranslatedSpan:
    original_start: int
    original_end: int
    original_quote: str


@dataclass(frozen=True, slots=True)
class OffsetMap:
    replacements: tuple[OffsetReplacement, ...]

    def __post_init__(self) -> None:
        previous_original_end = 0
        previous_redacted_end = 0
        for replacement in self.replacements:
            if (
                replacement.original_start < previous_original_end
                or replacement.redacted_start < previous_redacted_end
            ):
                raise ValueError("offset replacements must be ordered and non-overlapping")
            unchanged_original = replacement.original_start - previous_original_end
            unchanged_redacted = replacement.redacted_start - previous_redacted_end
            if unchanged_original != unchanged_redacted:
                raise ValueError("offset replacement gap mismatch")
            previous_original_end = replacement.original_end
            previous_redacted_end = replacement.redacted_end

    def to_payload(self) -> dict[str, object]:
        return {
            "version": 1,
            "replacements": [item.to_payload() for item in self.replacements],
        }

    @classmethod
    def from_payload(cls, value: object) -> "OffsetMap":
        if not isinstance(value, dict) or set(value) != {"version", "replacements"}:
            raise ValueError("invalid offset map")
        if value["version"] != 1 or isinstance(value["version"], bool):
            raise ValueError("invalid offset map")
        replacements = value["replacements"]
        if not isinstance(replacements, list) or len(replacements) > 1000:
            raise ValueError("invalid offset map")
        return cls(tuple(OffsetReplacement.from_payload(item) for item in replacements))

    def redacted_boundary_to_original(self, position: int) -> int:
        if isinstance(position, bool) or not isinstance(position, int) or position < 0:
            raise ValueError("invalid redacted offset")
        original_cursor = 0
        redacted_cursor = 0
        for replacement in self.replacements:
            if position <= replacement.redacted_start:
                return original_cursor + (position - redacted_cursor)
            if position < replacement.redacted_end:
                raise ValueError("offset falls inside a PII placeholder")
            original_cursor = replacement.original_end
            redacted_cursor = replacement.redacted_end
        return original_cursor + (position - redacted_cursor)

    def original_boundary_to_redacted(self, position: int) -> int:
        if isinstance(position, bool) or not isinstance(position, int) or position < 0:
            raise ValueError("invalid original offset")
        original_cursor = 0
        redacted_cursor = 0
        for replacement in self.replacements:
            if position <= replacement.original_start:
                return redacted_cursor + (position - original_cursor)
            if position < replacement.original_end:
                raise ValueError("offset falls inside a PII span")
            original_cursor = replacement.original_end
            redacted_cursor = replacement.redacted_end
        return redacted_cursor + (position - original_cursor)

    def translate_redacted_span(
        self,
        *,
        redacted_text: str,
        original_text: str,
        source_quote: str,
        source_start: int,
        source_end: int,
    ) -> TranslatedSpan:
        if (
            source_start < 0
            or source_end <= source_start
            or source_end > len(redacted_text)
            or redacted_text[source_start:source_end] != source_quote
        ):
            raise ValueError("redacted source quote mismatch")
        included: list[OffsetReplacement] = []
        for replacement in self.replacements:
            overlaps = (
                replacement.redacted_start < source_end
                and replacement.redacted_end > source_start
            )
            if not overlaps:
                continue
            if (
                source_start > replacement.redacted_start
                or source_end < replacement.redacted_end
            ):
                raise ValueError("source quote cuts through a PII placeholder")
            included.append(replacement)
        original_start = self.redacted_boundary_to_original(source_start)
        original_end = self.redacted_boundary_to_original(source_end)
        if original_end > len(original_text):
            raise ValueError("translated source quote is out of bounds")
        rebuilt: list[str] = []
        cursor = source_start
        for replacement in included:
            rebuilt.append(redacted_text[cursor : replacement.redacted_start])
            rebuilt.append(original_text[replacement.original_start : replacement.original_end])
            cursor = replacement.redacted_end
        rebuilt.append(redacted_text[cursor:source_end])
        original_quote = "".join(rebuilt)
        if original_text[original_start:original_end] != original_quote:
            raise ValueError("original source quote mismatch")
        return TranslatedSpan(original_start, original_end, original_quote)


@dataclass(frozen=True, slots=True)
class RedactionResult:
    redacted_text: str
    offset_map: OffsetMap
    vault: PiiVault


@dataclass(frozen=True, slots=True)
class EncryptedRedactionResult:
    redacted_text: str
    redacted_text_envelope: dict
    offset_map: OffsetMap
    offset_map_envelope: dict
    vault: PiiVault
    vault_envelope: dict


class PiiRedactor:
    def __init__(self, *, analyzer: EntityAnalyzer, cipher: ContentCipher) -> None:
        self._analyzer = analyzer
        self._cipher = cipher

    @classmethod
    def from_local_model(cls, *, cipher: ContentCipher) -> "PiiRedactor":
        return cls(analyzer=_local_entity_analyzer(), cipher=cipher)

    def redact(self, text: str, *, user_id: UUID, vault: PiiVault) -> RedactionResult:
        if not isinstance(text, str) or len(text) > 200_000:
            raise ValueError("invalid redaction input")
        selected = _resolve_overlaps(self._analyzer.detect(text), text_length=len(text))
        entries = dict(vault.entries)
        next_indices = dict(vault.next_indices)
        output: list[str] = []
        replacements: list[OffsetReplacement] = []
        original_cursor = 0
        redacted_cursor = 0
        for entity in selected:
            output.append(text[original_cursor : entity.start])
            redacted_cursor += entity.start - original_cursor
            original_value = text[entity.start : entity.end]
            normalized = _normalize_entity(original_value)
            key_id, fingerprint = self._cipher.entity_fingerprint(
                normalized,
                user_id=user_id,
                entity_type=entity.entity_type,
            )
            entry = entries.get(fingerprint)
            if entry is None:
                entry = _entry_for_rotated_fingerprint(
                    entries,
                    entity_type=entity.entity_type,
                    normalized=normalized,
                )
            if entry is None:
                placeholder_type = PLACEHOLDER_TYPE_BY_ENTITY[entity.entity_type]
                index = next_indices.get(placeholder_type, 1)
                placeholder = f"<{placeholder_type}_{index}>"
                next_indices[placeholder_type] = index + 1
                entry = VaultEntry(
                    entity_type=entity.entity_type,
                    placeholder_type=placeholder_type,
                    placeholder=placeholder,
                    canonical_original=unicodedata.normalize("NFC", original_value),
                    fingerprint_key_id=key_id,
                )
            entries[fingerprint] = entry
            output.append(entry.placeholder)
            replacements.append(
                OffsetReplacement(
                    original_start=entity.start,
                    original_end=entity.end,
                    redacted_start=redacted_cursor,
                    redacted_end=redacted_cursor + len(entry.placeholder),
                    placeholder=entry.placeholder,
                )
            )
            redacted_cursor += len(entry.placeholder)
            original_cursor = entity.end
        output.append(text[original_cursor:])
        return RedactionResult(
            redacted_text="".join(output),
            offset_map=OffsetMap(tuple(replacements)),
            vault=PiiVault(entries=entries, next_indices=next_indices),
        )

    def redact_and_encrypt(
        self,
        text: str,
        *,
        user_id: UUID,
        analysis_id: UUID,
        vault_envelope: dict | None,
    ) -> EncryptedRedactionResult:
        if vault_envelope is None:
            vault = PiiVault.empty()
        else:
            vault = PiiVault.from_payload(
                self._cipher.decrypt_json(
                    vault_envelope,
                    user_id=user_id,
                    record_id=user_id,
                    purpose="pii_vault",
                )
            )
        result = self.redact(text, user_id=user_id, vault=vault)
        return EncryptedRedactionResult(
            redacted_text=result.redacted_text,
            redacted_text_envelope=self._cipher.encrypt_json(
                result.redacted_text,
                user_id=user_id,
                record_id=analysis_id,
                purpose="entry_redacted_text",
            ),
            offset_map=result.offset_map,
            offset_map_envelope=self._cipher.encrypt_json(
                result.offset_map.to_payload(),
                user_id=user_id,
                record_id=analysis_id,
                purpose="entry_offset_map",
            ),
            vault=result.vault,
            vault_envelope=self._cipher.encrypt_json(
                result.vault.to_payload(),
                user_id=user_id,
                record_id=user_id,
                purpose="pii_vault",
            ),
        )


def _resolve_overlaps(
    entities: Sequence[DetectedEntity], *, text_length: int
) -> tuple[DetectedEntity, ...]:
    candidates = []
    for entity in entities:
        if entity.end > text_length:
            raise ValueError("detected entity is out of bounds")
        candidates.append(entity)
    ranked = sorted(
        candidates,
        key=lambda item: (-item.score, -(item.end - item.start), item.start, item.end, item.entity_type),
    )
    selected: list[DetectedEntity] = []
    for candidate in ranked:
        if any(
            candidate.start < existing.end and candidate.end > existing.start
            for existing in selected
        ):
            continue
        selected.append(candidate)
    return tuple(sorted(selected, key=lambda item: (item.start, item.end, item.entity_type)))


@lru_cache(maxsize=1)
def _local_entity_analyzer() -> PresidioEntityAnalyzer:
    return PresidioEntityAnalyzer.from_local_model()


def _normalize_entity(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    return " ".join(normalized.split()).casefold()


def _entry_for_rotated_fingerprint(
    entries: dict[str, VaultEntry], *, entity_type: str, normalized: str
) -> VaultEntry | None:
    for entry in entries.values():
        if (
            entry.entity_type == entity_type
            and _normalize_entity(entry.canonical_original) == normalized
        ):
            return entry
    return None


def _required_string(value: object, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError("invalid string value")
    return value


def _required_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("invalid integer value")
    return value
