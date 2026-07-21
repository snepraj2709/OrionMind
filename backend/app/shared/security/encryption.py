from __future__ import annotations

from typing import Protocol
from uuid import UUID


class ContentCipher(Protocol):
    """Feature-facing seam for versioned authenticated content encryption."""

    def encrypt(self, plaintext: str, *, user_id: UUID, record_id: UUID) -> dict: ...

    def decrypt(self, envelope: dict, *, user_id: UUID, record_id: UUID) -> str: ...
