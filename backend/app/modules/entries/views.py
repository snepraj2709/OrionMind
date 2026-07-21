from __future__ import annotations

from dataclasses import asdict

from app.modules.entries.schemas import (
    Candidate,
    Classification,
    EntryDetail,
    EntryDraftResponse,
    EntryPage,
    EntrySummary,
    EntrySummaryTheme,
    Reflection,
    ThemeScore,
)
from app.modules.entries.types import EntryOperation, EntryPageData


def draft_response(content: str | None, updated_at) -> EntryDraftResponse:
    return EntryDraftResponse(content=content, updated_at=updated_at)


def entry_page_response(page: EntryPageData) -> EntryPage:
    return EntryPage(
        items=[
            EntrySummary(
                id=item.entry.id,
                input_type=item.entry.input_type,
                entry_date=item.entry.entry_date,
                processing_status=item.entry.processing_status,
                created_at=item.entry.created_at,
                content_preview=item.plaintext[:200],
                themes=[
                    EntrySummaryTheme(
                        key=theme.key,
                        name=theme.name,
                        color_hex=theme.color_hex,
                        tier=theme.tier,
                    )
                    for theme in item.themes
                ],
            )
            for item in page.items
        ],
        total=page.total,
        page=page.page,
        page_size=page.page_size,
    )


def entry_detail_response(operation: EntryOperation) -> EntryDetail:
    entry = operation.entry
    classification = None
    if entry.classification is not None:
        classification = Classification(
            theme_config_id=entry.classification.theme_config_id,
            source=entry.classification.source,
            mode=entry.classification.mode,
            themes=[
                ThemeScore(
                    key=theme.key,
                    name=theme.name,
                    score=theme.score,
                    tier=theme.tier,
                )
                for theme in entry.classification.themes
            ],
        )
    return EntryDetail(
        id=entry.id,
        content=operation.plaintext,
        input_type=entry.input_type,
        entry_date=entry.entry_date,
        original_theme_config_id=entry.original_theme_config_id,
        processing_status=entry.processing_status,
        processing_error_code=entry.processing_error_code,
        created_at=entry.created_at,
        classification=classification,
        ideas=[Candidate(**asdict(candidate)) for candidate in entry.ideas],
        extracted_memories=[Candidate(**asdict(candidate)) for candidate in entry.memories],
        reflections=[Reflection(**asdict(reflection)) for reflection in entry.reflections],
    )
