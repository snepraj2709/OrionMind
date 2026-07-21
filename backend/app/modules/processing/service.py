from __future__ import annotations

import logging
from datetime import date
from uuid import UUID, uuid4

from app.modules.jobs.types import JobClaim
from app.modules.processing.prompts import ENTRY_ANALYSIS_PROMPT_VERSION
from app.modules.processing.quality import (
    DeterministicQualityResult,
    compute_quality_features,
    finalize_quality,
)
from app.modules.processing.redaction import OffsetMap, PiiRedactor
from app.modules.processing.repository import ProcessingRepository
from app.modules.processing.schemas import (
    EntryExtraction,
    EntryQualityResult,
    ModelEntryAnalysis,
    ModelEntryExtraction,
)
from app.modules.processing.source_segments import SourceSegment, create_source_segments
from app.modules.processing.types import (
    EntryAnalysisProvider,
    PreparedEntryAnalysis,
    ThemeDefinition,
)
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.observability.logging import safe_log
from app.shared.observability.reflection import ReflectionTelemetry
from app.shared.security.encryption import ContentCipher


logger = logging.getLogger("orion.processing.service")


SCORES: dict[tuple[int, str], tuple[float, ...]] = {
    (1, "dominant"): (1.0,),
    (2, "dominant"): (0.6265, 0.3735),
    (2, "balanced"): (0.5333, 0.4667),
    (3, "dominant"): (0.52, 0.31, 0.17),
    (3, "balanced"): (0.40, 0.35, 0.25),
}
PROVIDER_MAX_SCALARS = 50_000
PROVIDER_MAX_UTF8_BYTES = 200_000


class AnalysisValidationError(ValueError):
    pass


class PrivacyValidationError(ValueError):
    pass


class ProcessingService:
    def __init__(
        self,
        *,
        repository: ProcessingRepository,
        provider: EntryAnalysisProvider,
        cipher: ContentCipher,
        redactor: PiiRedactor,
        model_id: str,
        reflection_threshold: float,
        telemetry: ReflectionTelemetry | None = None,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._cipher = cipher
        self._redactor = redactor
        self._model_id = model_id
        self._reflection_threshold = reflection_threshold
        self._telemetry = telemetry or ReflectionTelemetry()

    def analyze(
        self,
        *,
        user_id: UUID,
        entry_id: UUID,
        entry_date: date,
        theme_config_id: UUID,
        content: str,
        uow: UnitOfWorkFactory,
    ) -> PreparedEntryAnalysis:
        with uow.for_user(user_id) as work:
            raw_themes = self._repository.fixed_themes(work.session, theme_config_id)
        themes = tuple(ThemeDefinition(key=key, name=name) for key, name in raw_themes)
        if len(themes) != 8:
            raise RuntimeError("fixed theme catalog invariant failed")
        with uow.for_worker() as work:
            history = self._repository.recent_quality_history(
                work.session,
                user_id=user_id,
                entry_id=entry_id,
                entry_date=entry_date,
            )
        deterministic = compute_quality_features(
            content,
            user_id=user_id,
            cipher=self._cipher,
            history=history,
        )
        analysis_id = uuid4()
        try:
            with uow.for_worker() as work:
                vault_envelope, vault_version = self._repository.load_pii_vault_for_update(
                    work.session, user_id=user_id
                )
                protected = self._redactor.redact_and_encrypt(
                    content,
                    user_id=user_id,
                    analysis_id=analysis_id,
                    vault_envelope=vault_envelope,
                )
                self._repository.save_pii_vault(
                    work.session,
                    user_id=user_id,
                    mapping_envelope=protected.vault_envelope,
                    expected_version=vault_version,
                )
        except ValueError as exc:
            raise PrivacyValidationError("local PII redaction failed") from exc

        provider_text = _provider_content(protected.redacted_text)
        if deterministic.features.hard_exclusion_codes:
            model_result = _deterministic_exclusion(deterministic)
            model_id = "deterministic"
        else:
            _, safety_identifier = self._cipher.reflection_fingerprint(
                str(user_id), user_id=user_id, purpose="safety_identifier"
            )
            model_result = self._provider.analyze(
                redacted_text=provider_text,
                themes=themes,
                deterministic_features=deterministic.features,
                entry_date=entry_date,
                safety_identifier=safety_identifier,
            )
            model_id = self._model_id
        try:
            _validate_model_offsets(model_result, redacted_text=provider_text)
            final_quality = finalize_quality(
                model_result.quality,
                deterministic=deterministic.features,
            )
            extraction = materialize_extraction(
                model_result.legacy,
                content=provider_text,
                allowed_keys={theme.key for theme in themes},
                reflection_threshold=self._reflection_threshold,
                original_content=content,
                offset_map=protected.offset_map,
            )
            signals = (
                _materialize_signals(
                    model_result,
                    user_id=user_id,
                    original_content=content,
                    redacted_text=provider_text,
                    offset_map=protected.offset_map,
                    duplicate_cluster_key=deterministic.duplicate_cluster_key,
                    cipher=self._cipher,
                )
                if final_quality.eligibility == "accepted"
                else ()
            )
        except ValueError as exc:
            raise AnalysisValidationError("combined entry analysis is invalid") from exc
        analysis: dict[str, object] = {
            "id": str(analysis_id),
            "entry_kind": model_result.quality.entry_kind,
            "model_eligibility": model_result.quality.eligibility,
            "eligibility": final_quality.eligibility,
            "deterministic_features": deterministic.features.model_dump(mode="json"),
            "semantic_scores": final_quality.semantic_scores(model_result.quality),
            "exclusion_reason_codes": list(final_quality.exclusion_reason_codes),
            "ngram_sketch": list(deterministic.ngram_sketch),
            "redacted_text_envelope": protected.redacted_text_envelope,
            "offset_map_envelope": protected.offset_map_envelope,
            "reflective_word_count": deterministic.features.word_count,
            "duplicate_cluster_key": deterministic.duplicate_cluster_key,
            "model_id": model_id,
            "prompt_version": ENTRY_ANALYSIS_PROMPT_VERSION,
        }
        return PreparedEntryAnalysis(
            analysis=analysis,
            signals=signals,
            extraction=extraction,
        )

    def apply_job_analysis(
        self,
        *,
        claim: JobClaim,
        worker_id: str,
        theme_config_id: UUID,
        prepared: PreparedEntryAnalysis,
        apply_legacy: bool,
        uow: UnitOfWorkFactory,
    ) -> int:
        with uow.for_worker() as work:
            source_version = self._repository.apply_combined_job_analysis(
                work.session,
                claim=claim,
                worker_id=worker_id,
                theme_config_id=theme_config_id,
                extraction=prepared.extraction,
                analysis=prepared.analysis,
                signals=prepared.signals,
                apply_legacy=apply_legacy,
            )
        result = str(prepared.analysis["eligibility"])
        kind = str(prepared.analysis["entry_kind"])
        signal_types = tuple(str(item["signal_type"]) for item in prepared.signals)
        self._telemetry.record_entry_analysis(
            result=result,
            kind=kind,
            signal_types=signal_types,
        )
        reasons = prepared.analysis.get("exclusion_reason_codes")
        first_reason = (
            str(reasons[0])
            if isinstance(reasons, list) and reasons
            else "NONE"
        )
        safe_log(
            logger,
            "entry_analysis_materialized",
            entry_id=claim.entry_id,
            entry_kind=kind,
            status=result,
            exclusion_reason_code=first_reason,
            signal_count=len(signal_types),
        )
        return source_version


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


def _validate_model_offsets(result: ModelEntryAnalysis, *, redacted_text: str) -> None:
    for signal in result.signals:
        if (
            signal.source_end > len(redacted_text)
            or redacted_text[signal.source_start : signal.source_end]
            != signal.source_quote
        ):
            raise ValueError("redacted source quote mismatch")


def _materialize_signals(
    result: ModelEntryAnalysis,
    *,
    user_id: UUID,
    original_content: str,
    redacted_text: str,
    offset_map: OffsetMap,
    duplicate_cluster_key: str | None,
    cipher: ContentCipher,
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for signal in result.signals:
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
        rows.append(
            {
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
                "occurred_on": signal.occurred_on.isoformat(),
                "duplicate_cluster_key": duplicate_cluster_key,
            }
        )
    return tuple(rows)


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
