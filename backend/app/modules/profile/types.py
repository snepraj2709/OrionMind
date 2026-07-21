from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProfileData:
    display_name: str
    timezone: str


class AccountDeletionOutcome(str, Enum):
    DELETED = "deleted"
    ALREADY_MISSING = "already_missing"


class AccountAuthGateway(Protocol):
    def verify_user(self, proof_token: str) -> UUID: ...

    def delete_user(self, user_id: UUID) -> AccountDeletionOutcome: ...
