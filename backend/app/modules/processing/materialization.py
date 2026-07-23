from __future__ import annotations

import unicodedata
from collections.abc import Collection
from datetime import date
from typing import cast
from uuid import UUID, uuid4

from app.modules.processing.quality import DeterministicQualityResult
from app.modules.processing.redaction import OffsetMap
from app.modules.processing.schemas import (
    EntryExtraction,
    EntryQualityResult,
    ModelEntryAnalysis,
    ModelEntryExtraction,
)
from app.modules.processing.source_segments import SourceSegment, create_source_segments
from app.modules.review.types import (
    ENTRY_INSIGHT_CATEGORY_BY_TYPE,
    ENTRY_INSIGHT_TYPES,
    EntryInsightType,
)
from app.shared.security.encryption import ContentCipher


SCORES: dict[tuple[int, str], tuple[float, ...]] = {
    (1, "dominant"): (1.0,),
    (2, "dominant"): (0.6265, 0.3735),
    (2, "balanced"): (0.5333, 0.4667),
    (3, "dominant"): (0.52, 0.31, 0.17),
    (3, "balanced"): (0.40, 0.35, 0.25),
}
PROVIDER_MAX_SCALARS = 50_000
PROVIDER_MAX_UTF8_BYTES = 200_000


def _provider_content(content: str) -> str:
    limited = content[:PROVIDER_MAX_SCALARS]
    encoded = limited.encode("utf-8")
    if len(encoded) > PROVIDER_MAX_UTF8_BYTES:
        end = len(limited)
        while len(limited[:end].encode("utf-8")) > PROVIDER_MAX_UTF8_BYTES:
            end -= 1
        limited = limited[:end]
    if limited.count("<") > limited.count(">"):
        limited = limited[: limited.rfind("<")]
    return limited


def _resolve_segment(
    segment_id: str,
    *,
    content: str,
    segments: dict[str, SourceSegment],
    original_content: str | None,
    offset_map: OffsetMap | None,
) -> str:
    segment = segments.get(segment_id)
    if segment is None or not segment.selectable:
        raise ValueError("invalid source segment reference")
    value = segment.text(content)
    if original_content is None or offset_map is None:
        return value
    return offset_map.translate_redacted_span(
        redacted_text=content,
        original_text=original_content,
        source_quote=value,
        source_start=segment.start,
        source_end=segment.end,
    ).original_quote


def materialize_extraction(
    result: ModelEntryExtraction,
    *,
    content: str,
    allowed_keys: set[str],
    reflection_threshold: float,
    original_content: str | None = None,
    offset_map: OffsetMap | None = None,
) -> EntryExtraction:
    segments = {segment.id: segment for segment in create_source_segments(content)}
    selected_keys = {item.key for item in result.theme.themes}
    if not selected_keys <= allowed_keys:
        raise ValueError("theme outside fixed config")
    count = len(result.theme.themes)
    scores = () if count == 0 else SCORES[(count, str(result.theme.mode))]
    reflections = result.reflection.model_dump()
    for key, value in tuple(reflections.items()):
        if value is not None and value["confidence"] < reflection_threshold:
            reflections[key] = None
    resolve = lambda segment_id: _resolve_segment(  # noqa: E731
        segment_id,
        content=content,
        segments=segments,
        original_content=original_content,
        offset_map=offset_map,
    )
    return EntryExtraction.model_validate(
        {
            "ideas": [{"content": resolve(item.source_segment_id)} for item in result.ideas],
            "memories": [
                {"content": resolve(item.source_segment_id)} for item in result.memories
            ],
            "theme": {
                "mode": result.theme.mode,
                "themes": [
                    {
                        "key": item.key,
                        "tier": item.tier,
                        "evidence": resolve(item.evidence_segment_id),
                        "score": scores[index],
                    }
                    for index, item in enumerate(result.theme.themes)
                ],
            },
            "reflection": reflections,
        }
    )

def _bind_model_offsets(
    result: ModelEntryAnalysis,
    *,
    redacted_text: str,
) -> ModelEntryAnalysis:
    occupied: list[tuple[int, int]] = []
    bound = []
    for signal in result.signals:
        spans = _source_quote_spans(redacted_text, signal.source_quote)
        available = [
            (start, end)
            for start, end in spans
            if all(
                end <= used_start
                or start >= used_end
                for used_start, used_end in occupied
            )
        ]
        # Overlap is a model-quality issue, not an evidence-integrity issue. If
        # two otherwise valid atomic signals cite intersecting source text,
        # retain both exact source spans rather than discarding the whole entry.
        if not available:
            available = spans
        if not available:
            continue
        start, end = min(
            available,
            key=lambda candidate: (
                abs(candidate[0] - signal.source_start),
                candidate[0],
                candidate[1],
            ),
        )
        occupied.append((start, end))
        bound.append(
            signal.model_copy(
                update={
                    "source_quote": redacted_text[start:end],
                    "source_start": start,
                    "source_end": end,
                }
            )
        )
    bound.sort(key=lambda signal: (signal.source_start, signal.source_end))
    return result.model_copy(update={"signals": bound})


_QUOTE_EQUIVALENTS = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)


def _locator_text(value: str) -> tuple[str, list[tuple[int, int]]]:
    characters: list[str] = []
    source_spans: list[tuple[int, int]] = []
    for index, source_character in enumerate(value):
        if source_character.isspace():
            if characters and characters[-1] != " ":
                characters.append(" ")
                source_spans.append((index, index + 1))
            elif characters:
                start, _ = source_spans[-1]
                source_spans[-1] = (start, index + 1)
            continue
        normalized = unicodedata.normalize("NFKC", source_character)
        normalized = normalized.translate(_QUOTE_EQUIVALENTS).casefold()
        for character in normalized:
            characters.append(character)
            source_spans.append((index, index + 1))
    if characters and characters[-1] == " ":
        characters.pop()
        source_spans.pop()
    return "".join(characters), source_spans


def _source_quote_spans(source: str, quote: str) -> list[tuple[int, int]]:
    exact: list[tuple[int, int]] = []
    cursor = 0
    while True:
        start = source.find(quote, cursor)
        if start < 0:
            break
        exact.append((start, start + len(quote)))
        cursor = start + 1
    if exact:
        return exact

    normalized_source, source_map = _locator_text(source)
    normalized_quote, _ = _locator_text(quote)
    if not normalized_quote:
        return []
    normalized: list[tuple[int, int]] = []
    cursor = 0
    while True:
        start = normalized_source.find(normalized_quote, cursor)
        if start < 0:
            break
        final = start + len(normalized_quote) - 1
        normalized.append((source_map[start][0], source_map[final][1]))
        cursor = start + 1
    return normalized


def _materialize_signals(
    result: ModelEntryAnalysis,
    *,
    user_id: UUID,
    original_content: str,
    redacted_text: str,
    offset_map: OffsetMap,
    duplicate_cluster_key: str | None,
    cipher: ContentCipher,
    entry_date: date,
    model_id: str,
    prompt_version: str,
    embeddings: tuple[tuple[float, ...], ...] = (),
    embedding_model_id: str = "disabled",
) -> tuple[dict[str, object], ...]:
    if len(embeddings) != len(result.signals):
        raise ValueError("every accepted signal requires one embedding")
    rows: list[dict[str, object]] = []
    for signal, embedding in zip(result.signals, embeddings, strict=True):
        translated = offset_map.translate_redacted_span(
            redacted_text=redacted_text,
            original_text=original_content,
            source_quote=signal.source_quote,
            source_start=signal.source_start,
            source_end=signal.source_end,
        )
        signal_id = uuid4()
        normalized_label = " ".join(signal.normalized_label.split()).casefold()
        _, label_fingerprint = cipher.reflection_fingerprint(
            normalized_label, user_id=user_id, purpose="signal_label"
        )
        payload = {
            "normalized_label": normalized_label,
            "interpretation": signal.interpretation,
            "source_quote": translated.original_quote,
        }
        row: dict[str, object] = {
            "id": str(signal_id),
            "signal_type": signal.signal_type,
            "normalized_label_fingerprint": label_fingerprint,
            "payload_envelope": cipher.encrypt_json(
                payload,
                user_id=user_id,
                record_id=signal_id,
                purpose="entry_signal_payload",
            ),
            "themes": signal.themes,
            "need_tags": signal.need_tags,
            "loop_role": signal.loop_role,
            "confidence": signal.confidence,
            "source_start": translated.original_start,
            "source_end": translated.original_end,
            "occurred_on": entry_date.isoformat(),
            "duplicate_cluster_key": duplicate_cluster_key,
            "embedding": list(embedding),
            "embedding_model": embedding_model_id,
        }
        if signal.signal_type in ENTRY_INSIGHT_TYPES:
            item_type = cast(EntryInsightType, signal.signal_type)
            review_item_id = uuid4()
            row["review_item"] = {
                "id": str(review_item_id),
                "category": ENTRY_INSIGHT_CATEGORY_BY_TYPE[item_type],
                "statement_envelope": cipher.encrypt_json(
                    signal.interpretation,
                    user_id=user_id,
                    record_id=review_item_id,
                    purpose="review_item_statement",
                ),
                "source_quote_envelope": cipher.encrypt_json(
                    translated.original_quote,
                    user_id=user_id,
                    record_id=review_item_id,
                    purpose="review_item_source_quote",
                ),
                "inference_level": signal.inference_level,
                "metadata": {
                    "model_id": model_id,
                    "prompt_version": prompt_version,
                    "source": "entry_analysis",
                },
            }
        rows.append(row)
    return tuple(rows)


def signal_embedding_text(
    *,
    signal_type: str,
    normalized_label: str,
    interpretation: str,
    themes: Collection[str],
    need_tags: Collection[str],
    loop_role: str | None,
) -> str:
    fields = (
        f"signal_type: {signal_type}",
        f"normalized_label: {' '.join(normalized_label.split()).casefold()}",
        f"interpretation: {' '.join(interpretation.split())}",
        f"themes: {', '.join(themes)}",
        f"needs: {', '.join(need_tags)}",
        f"loop_role: {loop_role or 'none'}",
    )
    return "\n".join(fields)


def _deterministic_exclusion(
    deterministic: DeterministicQualityResult,
) -> ModelEntryAnalysis:
    kind = (
        "test_or_noise"
        if any(
            code
            in {
                "EMPTY_CONTENT",
                "TEST_OR_NOISE",
                "REPEATED_NGRAMS",
                "NO_MEANINGFUL_CONTENT",
            }
            for code in deterministic.features.hard_exclusion_codes
        )
        else "unclear"
    )
    quality = EntryQualityResult.model_validate(
        {
            "entry_kind": kind,
            "lived_experience_score": 0,
            "self_reference_score": 0,
            "emotional_information_score": 0,
            "causal_reasoning_score": 0,
            "personal_relevance_score": 0,
            "confidence": 1,
            "eligibility": "excluded",
            "exclusion_reason_codes": deterministic.features.hard_exclusion_codes,
        }
    )
    return ModelEntryAnalysis.model_validate(
        {
            "quality": quality,
            "signals": [],
            "legacy": {
                "ideas": [],
                "memories": [],
                "theme": {"mode": None, "themes": []},
                "reflection": {
                    "filled_energy": None,
                    "drained_energy": None,
                    "learned_about_self": None,
                },
            },
        }
    )
