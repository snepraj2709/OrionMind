from __future__ import annotations

from app.modules.processing.repository import ProcessingRepository
from app.modules.processing.schemas import EntryExtraction, ModelEntryExtraction
from app.modules.processing.source_segments import SourceSegment, create_source_segments
from app.modules.processing.types import ExtractionProvider, ProcessingRequest, ThemeDefinition
from app.shared.database.unit_of_work import UnitOfWorkFactory


SCORES: dict[tuple[int, str], tuple[float, ...]] = {
    (1, "dominant"): (1.0,),
    (2, "dominant"): (0.6265, 0.3735),
    (2, "balanced"): (0.5333, 0.4667),
    (3, "dominant"): (0.52, 0.31, 0.17),
    (3, "balanced"): (0.40, 0.35, 0.25),
}
PROVIDER_MAX_SCALARS = 50_000
PROVIDER_MAX_UTF8_BYTES = 200_000


class ProcessingService:
    def __init__(
        self,
        *,
        repository: ProcessingRepository,
        provider: ExtractionProvider,
        reflection_threshold: float,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._reflection_threshold = reflection_threshold

    def process(self, request: ProcessingRequest, unit_of_work_factory: UnitOfWorkFactory) -> None:
        try:
            with unit_of_work_factory.for_user(request.user_id) as work:
                raw_themes = self._repository.fixed_themes(work.session, request.theme_config_id)
            themes = tuple(ThemeDefinition(key=key, name=name) for key, name in raw_themes)
            if len(themes) != 8:
                raise RuntimeError("fixed theme catalog invariant failed")
            provider_content = _provider_content(request.content)
            model_result = self._provider.extract(content=provider_content, themes=themes)
            extraction = materialize_extraction(
                model_result,
                content=provider_content,
                allowed_keys={theme.key for theme in themes},
                reflection_threshold=self._reflection_threshold,
            )
            with unit_of_work_factory.for_user(request.user_id) as work:
                self._repository.apply_extraction(
                    work.session,
                    user_id=request.user_id,
                    entry_id=request.entry_id,
                    processing_token=request.processing_token,
                    theme_config_id=request.theme_config_id,
                    extraction=extraction,
                    past_import=request.past_import,
                )
        except Exception:
            try:
                with unit_of_work_factory.for_user(request.user_id) as work:
                    self._repository.mark_failed(
                        work.session,
                        user_id=request.user_id,
                        entry_id=request.entry_id,
                        processing_token=request.processing_token,
                        error_code="PROCESSING_FAILED",
                    )
            except Exception:
                pass
            raise


def _provider_content(content: str) -> str:
    limited = content[:PROVIDER_MAX_SCALARS]
    encoded = limited.encode("utf-8")
    if len(encoded) <= PROVIDER_MAX_UTF8_BYTES:
        return limited
    end = len(limited)
    while len(limited[:end].encode("utf-8")) > PROVIDER_MAX_UTF8_BYTES:
        end -= 1
    return limited[:end]


def _resolve_segment(
    segment_id: str,
    *,
    content: str,
    segments: dict[str, SourceSegment],
) -> str:
    segment = segments.get(segment_id)
    if segment is None or not segment.selectable:
        raise ValueError("invalid source segment reference")
    return segment.text(content)


def materialize_extraction(
    result: ModelEntryExtraction,
    *,
    content: str,
    allowed_keys: set[str],
    reflection_threshold: float,
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
    return EntryExtraction.model_validate(
        {
            "ideas": [
                {"content": _resolve_segment(item.source_segment_id, content=content, segments=segments)}
                for item in result.ideas
            ],
            "memories": [
                {"content": _resolve_segment(item.source_segment_id, content=content, segments=segments)}
                for item in result.memories
            ],
            "theme": {
                "mode": result.theme.mode,
                "themes": [
                    {
                        "key": item.key,
                        "tier": item.tier,
                        "evidence": _resolve_segment(
                            item.evidence_segment_id, content=content, segments=segments
                        ),
                        "score": scores[index],
                    }
                    for index, item in enumerate(result.theme.themes)
                ],
            },
            "reflection": reflections,
        }
    )
