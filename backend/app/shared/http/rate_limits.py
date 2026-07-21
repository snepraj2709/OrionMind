from __future__ import annotations

import math
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Request


@dataclass(frozen=True, slots=True)
class Window:
    requests: int
    seconds: int


RULES: dict[str, tuple[Window, ...]] = {
    "health": (Window(60, 60),),
    "read": (Window(30, 1),),
    "profile_write": (Window(5, 1),),
    "account_delete": (Window(2, 60),),
    "draft_write": (Window(10, 1),),
    "text_create": (Window(5, 1),),
    "past_entry_create": (Window(2, 1), Window(200, 86_400)),
    "voice_create": (Window(1, 10), Window(6, 3_600)),
    "entry_retry": (Window(2, 60),),
}

_ENTRY_DETAIL = re.compile(r"^/api/v1/entries/[^/]+$")
_ENTRY_RETRY = re.compile(r"^/api/v1/entries/[^/]+/retry$")


def request_class(request: Request) -> tuple[str, str] | None:
    path = request.url.path
    method = request.method
    user = getattr(getattr(request.state, "auth_context", None), "user_id", None)
    scope = str(user) if user is not None else (
        request.client.host if request.client is not None else "unknown"
    )
    rate_class = _rate_class(method, path)
    return (rate_class, scope) if rate_class is not None else None


def _rate_class(method: str, path: str) -> str | None:
    if method == "GET" and path == "/health":
        return "health"
    if method == "PATCH" and path == "/api/v1/profile":
        return "profile_write"
    if method == "DELETE" and path == "/api/v1/account":
        return "account_delete"
    if method in {"PUT", "DELETE"} and path == "/api/v1/entry/draft":
        return "draft_write"
    if method == "POST" and path == "/api/v1/entry":
        return "text_create"
    if method == "POST" and path == "/api/v1/past-entries":
        return "past_entry_create"
    if method == "POST" and path == "/api/v1/entries/voice":
        return "voice_create"
    if method == "POST" and _ENTRY_RETRY.fullmatch(path):
        return "entry_retry"
    if method == "GET" and (
        path in {"/api/v1/profile", "/api/v1/entries", "/api/v1/entry/draft"}
        or _ENTRY_DETAIL.fullmatch(path)
    ):
        return "read"
    return None


class ProcessRateLimiter:
    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled
        self._events: dict[tuple[str, str, int], deque[float]] = defaultdict(deque)
        self._last_seen: dict[tuple[str, str], float] = {}
        self._checks = 0
        self._lock = threading.Lock()

    def check(self, rule: str, scope: str, *, now: float | None = None) -> int | None:
        if not self._enabled:
            return None
        current = time.monotonic() if now is None else now
        with self._lock:
            retry = 0.0
            for index, window in enumerate(RULES[rule]):
                events = self._events[(rule, scope, index)]
                while events and events[0] <= current - window.seconds:
                    events.popleft()
                if len(events) >= window.requests:
                    retry = max(retry, events[0] + window.seconds - current)
            self._last_seen[(rule, scope)] = current
            self._checks += 1
            if self._checks % 1_000 == 0:
                self._prune(current)
            if retry > 0:
                return max(1, math.ceil(retry))
            for index in range(len(RULES[rule])):
                self._events[(rule, scope, index)].append(current)
        return None

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._last_seen.clear()
            self._checks = 0

    def _prune(self, current: float) -> None:
        inactive = [
            key for key, last_seen in self._last_seen.items() if last_seen < current - 86_400
        ]
        for rule, scope in inactive:
            for index in range(len(RULES[rule])):
                self._events.pop((rule, scope, index), None)
            self._last_seen.pop((rule, scope), None)
