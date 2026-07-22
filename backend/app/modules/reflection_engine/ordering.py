from __future__ import annotations

from datetime import date

from app.modules.reflection_engine.schemas import CandidateSignal


def signal_order(signal: CandidateSignal) -> tuple[date, str, int, str]:
    return (
        signal.entry_date,
        str(signal.entry_id),
        signal.source_start,
        str(signal.id),
    )
