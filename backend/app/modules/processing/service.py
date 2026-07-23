from __future__ import annotations

import logging
from datetime import date
from uuid import UUID, uuid4

from app.modules.jobs.types import JobClaim
from app.modules.processing.materialization import (
    _bind_model_offsets,
    _deterministic_exclusion,
    _materialize_signals,
    _provider_content,
    materialize_extraction,
    signal_embedding_text,
)
from app.modules.processing.prompts import ENTRY_ANALYSIS_PROMPT_VERSION
from app.modules.processing.quality import (
    compute_quality_features,
    finalize_quality,
)
from app.modules.processing.redaction import PiiRedactor
from app.modules.processing.repository import ProcessingRepository
from app.modules.processing.types import (
    EntryAnalysisProvider,
    PreparedEntryAnalysis,
    SignalEmbeddingProvider,
    ThemeDefinition,
)
from app.shared.database.unit_of_work import UnitOfWorkFactory
from app.shared.observability.logging import safe_log
from app.shared.observability.reflection import ReflectionTelemetry
from app.shared.security.encryption import ContentCipher


logger = logging.getLogger("orion.processing.service")


class AnalysisValidationError(ValueError):
    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__("combined entry analysis is invalid")


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
        embedding_provider: SignalEmbeddingProvider | None = None,
        embedding_model_id: str = "disabled",
        telemetry: ReflectionTelemetry | None = None,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._cipher = cipher
        self._redactor = redactor
        self._model_id = model_id
        self._reflection_threshold = reflection_threshold
        self._embedding_provider = embedding_provider
        self._embedding_model_id = embedding_model_id
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
            safety_identifier = ""
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
            model_result = _bind_model_offsets(
                model_result,
                redacted_text=provider_text,
            )
        except ValueError as exc:
            raise AnalysisValidationError("source_offsets") from exc
        try:
            final_quality = finalize_quality(
                model_result.quality,
                deterministic=deterministic.features,
            )
        except ValueError as exc:
            raise AnalysisValidationError("quality") from exc
        try:
            extraction = materialize_extraction(
                model_result.legacy,
                content=provider_text,
                allowed_keys={theme.key for theme in themes},
                reflection_threshold=self._reflection_threshold,
                original_content=content,
                offset_map=protected.offset_map,
            )
        except ValueError as exc:
            raise AnalysisValidationError("legacy_extraction") from exc
        try:
            embeddings: tuple[tuple[float, ...], ...] = ()
            if final_quality.eligibility == "accepted" and model_result.signals:
                if self._embedding_provider is None:
                    raise RuntimeError("signal embedding provider is not configured")
                embeddings = self._embedding_provider.embed(
                    texts=tuple(
                        signal_embedding_text(
                            signal_type=item.signal_type,
                            normalized_label=item.normalized_label,
                            interpretation=item.interpretation,
                            themes=item.themes,
                            need_tags=item.need_tags,
                            loop_role=item.loop_role,
                        )
                        for item in model_result.signals
                    ),
                    safety_identifier=safety_identifier,
                )
            signals = _materialize_signals(
                model_result,
                user_id=user_id,
                original_content=content,
                redacted_text=provider_text,
                offset_map=protected.offset_map,
                duplicate_cluster_key=deterministic.duplicate_cluster_key,
                cipher=self._cipher,
                entry_date=entry_date,
                model_id=model_id,
                prompt_version=ENTRY_ANALYSIS_PROMPT_VERSION,
                embeddings=embeddings,
                embedding_model_id=self._embedding_model_id,
            ) if final_quality.eligibility == "accepted" else ()
        except ValueError as exc:
            raise AnalysisValidationError("embeddings") from exc
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
