from __future__ import annotations

import re
from dataclasses import dataclass


PARAGRAPH_BREAK = re.compile(r"\r?\n[^\S\r\n]*(?:\r?\n)+")
TRIVIAL = (
    re.compile(r"^(?:hi|hello|hey|hiya|howdy)(?:[\s,!.-]+[\w'-]+){0,2}[.!?]*$", re.I),
    re.compile(r"^(?:what(?:'|’)s up|wassup|sup)[.!?]*$", re.I),
    re.compile(r"^(?:ok(?:ay)?|thanks?|thank you|yes|no|yep|nope)[.!?]*$", re.I),
    re.compile(r"^.*\b(?:mic|microphone)\s+(?:test|testing)\b.*$", re.I),
    re.compile(r"^(?:test|testing)(?:[\s,!.-]+\w+){0,2}[.!?]*$", re.I),
)
CONSONANT_NOISE = re.compile(r"[a-z]{8,}[.!?]*", re.I)
TERMINALS = frozenset(".!?。！？")
CLOSERS = frozenset("\"'’”)]}")


@dataclass(frozen=True, slots=True)
class SourceSegment:
    id: str
    start: int
    end: int
    selectable: bool

    def text(self, source: str) -> str:
        return source[self.start : self.end]


def _trim(source: str, start: int, end: int) -> tuple[int, int]:
    while start < end and source[start].isspace():
        start += 1
    while end > start and source[end - 1].isspace():
        end -= 1
    return start, end


def _selectable(value: str) -> bool:
    candidate = value.strip()
    if not candidate or not any(character.isalpha() for character in candidate):
        return False
    if any(pattern.fullmatch(candidate) for pattern in TRIVIAL):
        return False
    return not (
        CONSONANT_NOISE.fullmatch(candidate)
        and not any(character in "aeiouyAEIOUY" for character in candidate)
    )


def _paragraphs(source: str) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    cursor = 0
    for match in PARAGRAPH_BREAK.finditer(source):
        bounds = _trim(source, cursor, match.start())
        if bounds[0] < bounds[1]:
            result.append(bounds)
        cursor = match.end()
    bounds = _trim(source, cursor, len(source))
    if bounds[0] < bounds[1]:
        result.append(bounds)
    return result


def _sentences(source: str, start: int, end: int) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    sentence_start = start
    index = start
    while index < end:
        if source[index] not in TERMINALS:
            index += 1
            continue
        boundary = index + 1
        while boundary < end and source[boundary] in TERMINALS:
            boundary += 1
        while boundary < end and source[boundary] in CLOSERS:
            boundary += 1
        if boundary < end and not source[boundary].isspace():
            index = boundary
            continue
        bounds = _trim(source, sentence_start, boundary)
        if bounds[0] < bounds[1]:
            result.append(bounds)
        while boundary < end and source[boundary].isspace():
            boundary += 1
        sentence_start = boundary
        index = boundary
    bounds = _trim(source, sentence_start, end)
    if bounds[0] < bounds[1]:
        result.append(bounds)
    return result


def create_source_segments(source: str) -> tuple[SourceSegment, ...]:
    bounds = [item for paragraph in _paragraphs(source) for item in _sentences(source, *paragraph)]
    return tuple(
        SourceSegment(
            id=f"segment_{index:04d}",
            start=start,
            end=end,
            selectable=_selectable(source[start:end]),
        )
        for index, (start, end) in enumerate(bounds, start=1)
    )
