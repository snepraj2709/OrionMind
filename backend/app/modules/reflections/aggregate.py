from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import cast
from uuid import UUID

from app.modules.reflections.schemas import FeedbackResponse, ReflectionRange


def _range_bounds(
    *,
    basis_start: date | None,
    basis_end: date | None,
    selected_range: ReflectionRange,
) -> tuple[date | None, date | None]:
    if basis_start is None or basis_end is None:
        return None, None
    if selected_range == "all":
        return basis_start, basis_end
    days = 7 if selected_range == "7d" else 30
    return max(basis_start, basis_end - timedelta(days=days - 1)), basis_end


def _feedback_map(value: object) -> dict[UUID, FeedbackResponse]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise ValueError("reflection feedback payload is invalid")
    result: dict[UUID, FeedbackResponse] = {}
    for item in value:
        row = _required_mapping(item, "reflection feedback")
        response = row.get("response")
        if response not in {"resonates", "partly", "rejected"}:
            raise ValueError("reflection feedback response is invalid")
        result[UUID(str(row.get("insight_id")))] = cast(FeedbackResponse, response)
    return result


def _first(value: list[Mapping[str, object]] | None) -> Mapping[str, object] | None:
    return value[0] if value else None


def _required_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} is invalid")
    return cast(Mapping[str, object], value)


def _optional_mapping(value: object, name: str) -> Mapping[str, object] | None:
    if value is None:
        return None
    return _required_mapping(value, name)


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} is invalid")
    return value


def _positive_int(value: object, name: str) -> int:
    result = _nonnegative_int(value, name)
    if result < 1:
        raise ValueError(f"{name} is invalid")
    return result


def _date(value: object, name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{name} is invalid") from exc
    raise ValueError(f"{name} is invalid")


def _optional_date(value: object, name: str) -> date | None:
    return None if value is None else _date(value, name)


def _datetime(value: object, name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{name} is invalid") from exc
    raise ValueError(f"{name} is invalid")
