from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from app.modules.processing.schemas import (
    DeterministicExclusionCode,
    DeterministicQualityFeatures,
    Eligibility,
    EntryQualityResult,
    QualityReasonCode,
)
from app.modules.processing.source_segments import is_trivial_source


TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
WHITESPACE = re.compile(r"\s+")
CAUSAL_OR_EMOTIONAL = re.compile(
    r"\b(?:after|because|felt|feel|feeling|frustrated|glad|happy|hurt|"
    r"nervous|sad|so|therefore|upset|worried)\b",
    re.IGNORECASE,
)
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "hers",
        "him",
        "his",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "ours",
        "she",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "they",
        "this",
        "to",
        "was",
        "we",
        "were",
        "with",
        "you",
        "your",
        "yours",
    }
)
SEMANTIC_KIND_REASON: dict[str, QualityReasonCode] = {
    "test_or_noise": "TEST_OR_NOISE",
    "informational_text": "INFORMATIONAL_TEXT",
    "copied_or_quoted_text": "COPIED_OR_QUOTED_TEXT",
    "task_or_note": "TASK_OR_NOTE",
    "creative_writing": "CREATIVE_WRITING",
    "unclear": "UNCLEAR",
}


class QualityFingerprintCipher(Protocol):
    def canonicalize(self, plaintext: str) -> str: ...

    def reflection_fingerprint(
        self,
        value: str,
        *,
        user_id: UUID,
        purpose: Literal["entry_duplicate", "token_trigram"],
    ) -> tuple[str, str]: ...


@dataclass(frozen=True, slots=True)
class QualityHistory:
    duplicate_cluster_key: str | None
    ngram_sketch: tuple[str, ...]
    eligibility: Eligibility


@dataclass(frozen=True, slots=True)
class DeterministicQualityResult:
    features: DeterministicQualityFeatures
    ngram_sketch: tuple[str, ...]
    duplicate_cluster_key: str | None


@dataclass(frozen=True, slots=True)
class FinalQualityDecision:
    eligibility: Eligibility
    reflective_score: float
    exclusion_reason_codes: tuple[QualityReasonCode, ...]

    def semantic_scores(self, quality: EntryQualityResult) -> dict[str, float]:
        return {
            "lived_experience_score": quality.lived_experience_score,
            "self_reference_score": quality.self_reference_score,
            "emotional_information_score": quality.emotional_information_score,
            "causal_reasoning_score": quality.causal_reasoning_score,
            "personal_relevance_score": quality.personal_relevance_score,
            "confidence": quality.confidence,
            "reflective_score": self.reflective_score,
        }


def compute_quality_features(
    content: str,
    *,
    user_id: UUID,
    cipher: QualityFingerprintCipher,
    history: tuple[QualityHistory, ...] = (),
) -> DeterministicQualityResult:
    canonical = _canonical_or_blank(content, cipher=cipher)
    lowered = WHITESPACE.sub(" ", canonical).casefold()
    tokens = tuple(match.group(0).casefold() for match in TOKEN.finditer(canonical))
    meaningful = tuple(
        token for token in tokens if len(token) > 1 and token not in STOPWORDS
    )
    trigrams = tuple("\x1f".join(tokens[index : index + 3]) for index in range(len(tokens) - 2))
    sketch = _bottom_k_sketch(trigrams, user_id=user_id, cipher=cipher)
    _, exact_fingerprint = cipher.reflection_fingerprint(
        lowered or "<EMPTY>", user_id=user_id, purpose="entry_duplicate"
    )
    accepted = tuple(item for item in history if item.eligibility == "accepted")
    exact_match = next(
        (
            item
            for item in accepted
            if item.duplicate_cluster_key == exact_fingerprint
        ),
        None,
    )
    similarities = tuple(
        (item, sketch_jaccard(sketch, item.ngram_sketch))
        for item in accepted
        if sketch and item.ngram_sketch
    )
    near_match, near_similarity = max(
        similarities,
        key=lambda item: item[1],
        default=(None, None),
    )
    is_near_duplicate = (
        exact_match is None
        and near_match is not None
        and near_similarity is not None
        and near_similarity >= 0.90
    )
    total_trigrams = len(trigrams)
    repeated_ngram_ratio = (
        0.0
        if total_trigrams == 0
        else 1 - len(set(trigrams)) / total_trigrams
    )
    hard_codes: list[DeterministicExclusionCode] = []
    if not canonical:
        hard_codes.append("EMPTY_CONTENT")
    if canonical and is_trivial_source(canonical):
        hard_codes.append("TEST_OR_NOISE")
    if exact_match is not None:
        hard_codes.append("EXACT_DUPLICATE")
    elif is_near_duplicate:
        hard_codes.append("NEAR_DUPLICATE")
    if (
        repeated_ngram_ratio >= 0.70
        and len(meaningful) < 8
        and CAUSAL_OR_EMOTIONAL.search(canonical) is None
    ):
        hard_codes.append("REPEATED_NGRAMS")
    if not meaningful and "EMPTY_CONTENT" not in hard_codes:
        hard_codes.append("NO_MEANINGFUL_CONTENT")

    matching_history = 0
    for item in history:
        if item.duplicate_cluster_key == exact_fingerprint:
            matching_history += 1
        elif sketch and item.ngram_sketch and sketch_jaccard(sketch, item.ngram_sketch) >= 0.90:
            matching_history += 1
    duplicate_cluster_key: str | None = exact_fingerprint
    if exact_match is not None and exact_match.duplicate_cluster_key is not None:
        duplicate_cluster_key = exact_match.duplicate_cluster_key
    elif is_near_duplicate and near_match is not None:
        duplicate_cluster_key = near_match.duplicate_cluster_key

    character_count = len(canonical)
    features = DeterministicQualityFeatures(
        word_count=len(tokens),
        meaningful_token_count=len(meaningful),
        unique_token_ratio=(len(set(meaningful)) / max(len(meaningful), 1)),
        repeated_ngram_ratio=repeated_ngram_ratio,
        alphabetic_character_ratio=(
            sum(character.isalpha() for character in canonical)
            / max(character_count, 1)
        ),
        exact_duplicate=exact_match is not None,
        near_duplicate_similarity=near_similarity,
        repeated_recent_entry_count=matching_history,
        copied_text_ratio=_copied_text_ratio(canonical),
        hard_exclusion_codes=hard_codes,
    )
    return DeterministicQualityResult(
        features=features,
        ngram_sketch=sketch,
        duplicate_cluster_key=duplicate_cluster_key,
    )


def finalize_quality(
    quality: EntryQualityResult,
    *,
    deterministic: DeterministicQualityFeatures,
) -> FinalQualityDecision:
    reflective_score = (
        0.30 * quality.lived_experience_score
        + 0.20 * quality.self_reference_score
        + 0.20 * quality.emotional_information_score
        + 0.15 * quality.causal_reasoning_score
        + 0.15 * quality.personal_relevance_score
    )
    reasons: list[QualityReasonCode] = list(quality.exclusion_reason_codes)
    if deterministic.hard_exclusion_codes:
        reasons.extend(deterministic.hard_exclusion_codes)
        eligibility: Eligibility = "excluded"
    elif (
        quality.entry_kind
        in {
            "test_or_noise",
            "informational_text",
            "copied_or_quoted_text",
            "task_or_note",
            "creative_writing",
        }
        and quality.confidence >= 0.80
    ):
        reasons.append(SEMANTIC_KIND_REASON[quality.entry_kind])
        eligibility = "excluded"
    elif quality.entry_kind == "unclear":
        reasons.append("UNCLEAR")
        eligibility = "uncertain"
    elif (
        reflective_score >= 0.60
        and quality.confidence >= 0.70
        and quality.eligibility == "accepted"
    ):
        eligibility = "accepted"
    elif reflective_score >= 0.40 or quality.confidence < 0.70:
        eligibility = "uncertain"
        if quality.confidence < 0.70:
            reasons.append("LOW_CONFIDENCE")
    else:
        eligibility = "excluded"
        reasons.append("LOW_REFLECTIVE_SCORE")
    return FinalQualityDecision(
        eligibility=eligibility,
        reflective_score=reflective_score,
        exclusion_reason_codes=tuple(dict.fromkeys(reasons))[:10],
    )


def sketch_jaccard(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    return len(left_set & right_set) / max(len(left_set | right_set), 1)


def _bottom_k_sketch(
    trigrams: tuple[str, ...],
    *,
    user_id: UUID,
    cipher: QualityFingerprintCipher,
) -> tuple[str, ...]:
    values = {
        cipher.reflection_fingerprint(
            trigram, user_id=user_id, purpose="token_trigram"
        )[1][:16]
        for trigram in trigrams
    }
    return tuple(sorted(values, key=lambda value: int(value, 16))[:128])


def _canonical_or_blank(content: str, *, cipher: QualityFingerprintCipher) -> str:
    try:
        return cipher.canonicalize(content)
    except ValueError:
        if isinstance(content, str) and not content.strip():
            return ""
        raise


def _copied_text_ratio(content: str) -> float:
    if not content:
        return 0.0
    copied = [False] * len(content)
    quote_start: int | None = None
    opening: str | None = None
    for index, character in enumerate(content):
        if quote_start is None and character in {'"', "“"}:
            quote_start = index
            opening = character
        elif quote_start is not None and (
            (opening == '"' and character == '"')
            or (opening == "“" and character == "”")
        ):
            for copied_index in range(quote_start, index + 1):
                copied[copied_index] = True
            quote_start = None
            opening = None
    cursor = 0
    for line in content.splitlines(keepends=True):
        if line.lstrip().startswith(">"):
            for copied_index in range(cursor, cursor + len(line)):
                copied[copied_index] = True
        cursor += len(line)
    return sum(copied) / len(content)
