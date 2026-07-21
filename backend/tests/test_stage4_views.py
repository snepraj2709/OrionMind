from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

import pytest

from app.modules.entries.types import (
    ClassificationData,
    EntryData,
    EntryOperation,
    EntryPageData,
    EntrySummaryData,
    ThemeData,
)
from app.modules.entries.views import entry_detail_response, entry_page_response


ENTRY_ID = UUID("77777777-7777-4777-8777-777777777777")
CONFIG_ID = UUID("00000000-0000-0000-0000-000000000801")
NOW = datetime(2026, 7, 21, tzinfo=timezone.utc)


def themes(count: int) -> tuple[ThemeData, ...]:
    values = (
        ThemeData("career", "Career", "#2563EB", "primary", 0.52 if count == 3 else 1.0),
        ThemeData("health", "Health", "#16A34A", "secondary", 0.31),
        ThemeData("money", "Money", "#D97706", "tertiary", 0.17),
    )
    return values[:count]


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_completed_empty_and_one_two_three_theme_list_detail_shapes(count: int) -> None:
    selected = themes(count)
    entry = EntryData(
        id=ENTRY_ID,
        envelope={},
        input_type="text",
        entry_date=date(2026, 7, 21),
        original_theme_config_id=CONFIG_ID,
        processing_status="completed",
        processing_error_code=None,
        created_at=NOW,
        classification=ClassificationData(
            theme_config_id=CONFIG_ID,
            source="initial",
            mode=None if count == 0 else "dominant",
            themes=selected,
        ),
    )
    page = entry_page_response(
        EntryPageData(
            items=(EntrySummaryData(entry=entry, plaintext="😀" * 205, themes=selected),),
            total=1,
            page=1,
            page_size=20,
        )
    )
    assert len(page.items[0].content_preview) == 200
    assert [item.tier for item in page.items[0].themes] == [
        "primary",
        "secondary",
        "tertiary",
    ][:count]
    detail = entry_detail_response(
        EntryOperation(entry=entry, plaintext="full content", status_code=200)
    )
    assert detail.classification is not None
    assert len(detail.classification.themes) == count
    assert detail.classification.mode == (None if count == 0 else "dominant")
