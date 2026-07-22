from __future__ import annotations

from dataclasses import dataclass
from datetime import date


class LiveRunError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SampleEntry:
    entry_date: date
    content: str
