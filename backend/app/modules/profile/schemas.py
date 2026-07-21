from __future__ import annotations

from typing import Self
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


IANA_TIMEZONES = frozenset(available_timezones())


class ProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    timezone: str


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("display_name cannot be null")
        return value.strip()

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("timezone cannot be null")
        if value != value.strip() or value not in IANA_TIMEZONES:
            raise ValueError("Unsupported IANA timezone")
        return value

    @model_validator(mode="after")
    def require_update(self) -> Self:
        if not ({"display_name", "timezone"} & self.model_fields_set):
            raise ValueError("At least one profile field is required")
        return self


class AccountDeletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: str
    reauthentication_token: str = Field(min_length=1)

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, value: str) -> str:
        if value != "DELETE MY ACCOUNT":
            raise ValueError("Invalid account deletion confirmation")
        return value
