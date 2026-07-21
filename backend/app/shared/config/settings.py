from __future__ import annotations

import base64
import binascii
import json
import math
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    ENVIRONMENT: str = "development"
    ENABLE_API_DOCS: bool = False

    SUPABASE_URL: str = ""
    SUPABASE_PUBLISHABLE_KEY: SecretStr = SecretStr("")
    SUPABASE_SECRET_KEY: SecretStr = SecretStr("")
    APP_DATABASE_URL: SecretStr = SecretStr("")
    WORKER_DATABASE_URL: SecretStr = SecretStr("")

    OPENAI_API_KEY: SecretStr = SecretStr("")
    OPENAI_PRIMARY_EXTRACTION_MODEL: str = "gpt-4o"
    OPENAI_FALLBACK_EXTRACTION_MODEL: str = "gpt-4o-mini"
    OPENAI_CONNECT_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=60)
    OPENAI_RESPONSE_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0, le=180)
    PROCESSING_TOTAL_TIMEOUT_SECONDS: float = Field(default=300.0, gt=0, le=600)
    ENTRY_ENCRYPTION_ACTIVE_KEY_ID: str = ""
    ENTRY_ENCRYPTION_KEYS: SecretStr = SecretStr("{}")
    ENTRY_FINGERPRINT_ACTIVE_KEY_ID: str = ""
    ENTRY_FINGERPRINT_KEYS: SecretStr = SecretStr("{}")
    REFLECTION_REVIEW_THRESHOLD: float = 0.80

    CORS_ALLOW_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://127.0.0.1:3100,http://localhost:8080,http://localhost:5173"
    )
    REQUEST_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=300)
    MAX_REQUEST_BODY_BYTES: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    DATABASE_POOL_SIZE: int = Field(default=5, ge=0, le=50)
    DATABASE_MAX_OVERFLOW: int = Field(default=5, ge=0, le=50)
    DATABASE_POOL_RECYCLE_SECONDS: int = Field(default=300, ge=30, le=3600)
    STARTUP_READINESS_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=60)
    PAST_IMPORT_STALE_SECONDS: int = Field(default=120, ge=30, le=3600)
    PAST_IMPORT_POLL_SECONDS: float = Field(default=1.0, ge=0.1, le=60)
    PAST_IMPORT_RECOVERY_INTERVAL_SECONDS: float = Field(default=60.0, ge=10, le=3600)
    WEB_CONCURRENCY: int = Field(default=1, ge=1, le=1)
    RATE_LIMITING_ENABLED: bool = True
    LOG_FORMAT: str = "json"
    OTEL_ENABLED: bool = False
    OTEL_SERVICE_NAME: str = "orion-backend"
    OTEL_EXPORTER_OTLP_ENDPOINT: SecretStr = SecretStr("")

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"development", "test", "production"}:
            raise ValueError("must be development, test, or production")
        return normalized

    @field_validator("REFLECTION_REVIEW_THRESHOLD")
    @classmethod
    def validate_threshold(cls, value: float) -> float:
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("must be finite and between 0 and 1")
        return value

    @field_validator("LOG_FORMAT")
    @classmethod
    def validate_log_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"json", "text"}:
            raise ValueError("must be json or text")
        return normalized

    @field_validator("OPENAI_PRIMARY_EXTRACTION_MODEL", "OPENAI_FALLBACK_EXTRACTION_MODEL")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 100:
            raise ValueError("model name must be between 1 and 100 characters")
        return normalized

    def cors_origins(self) -> tuple[str, ...]:
        values = tuple(dict.fromkeys(v.strip() for v in self.CORS_ALLOW_ORIGINS.split(",") if v.strip()))
        return values

    @staticmethod
    def _secret_present(value: SecretStr) -> bool:
        return bool(value.get_secret_value().strip())

    @staticmethod
    def _valid_key_map(value: SecretStr, active_key_id: str) -> bool:
        try:
            parsed = json.loads(value.get_secret_value())
        except (TypeError, json.JSONDecodeError):
            return False
        if not isinstance(parsed, dict) or not active_key_id or active_key_id not in parsed:
            return False
        for key_id, encoded in parsed.items():
            if not isinstance(key_id, str) or not key_id or not isinstance(encoded, str):
                return False
            try:
                decoded = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                return False
            if len(decoded) != 32 or base64.b64encode(decoded).decode("ascii") != encoded:
                return False
        return True

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if self.ENVIRONMENT != "production":
            return self
        if self.ENABLE_API_DOCS:
            raise ValueError("API docs must be disabled in production")
        required = {
            "SUPABASE_URL": bool(self.SUPABASE_URL.strip()),
            "SUPABASE_PUBLISHABLE_KEY": self._secret_present(self.SUPABASE_PUBLISHABLE_KEY),
            "SUPABASE_SECRET_KEY": self._secret_present(self.SUPABASE_SECRET_KEY),
            "APP_DATABASE_URL": self._secret_present(self.APP_DATABASE_URL),
            "WORKER_DATABASE_URL": self._secret_present(self.WORKER_DATABASE_URL),
            "OPENAI_API_KEY": self._secret_present(self.OPENAI_API_KEY),
            "ENTRY_ENCRYPTION_KEYS": self._valid_key_map(
                self.ENTRY_ENCRYPTION_KEYS, self.ENTRY_ENCRYPTION_ACTIVE_KEY_ID
            ),
            "ENTRY_FINGERPRINT_KEYS": self._valid_key_map(
                self.ENTRY_FINGERPRINT_KEYS, self.ENTRY_FINGERPRINT_ACTIVE_KEY_ID
            ),
        }
        missing = sorted(name for name, present in required.items() if not present)
        if missing:
            raise ValueError(f"missing or invalid production settings: {', '.join(missing)}")
        supabase_url = urlparse(self.SUPABASE_URL)
        if supabase_url.scheme != "https" or not supabase_url.netloc:
            raise ValueError("SUPABASE_URL must be HTTPS in production")
        app_database_url = self.APP_DATABASE_URL.get_secret_value()
        worker_database_url = self.WORKER_DATABASE_URL.get_secret_value()
        try:
            app_parsed = make_url(app_database_url)
            worker_parsed = make_url(worker_database_url)
        except ArgumentError as exc:
            raise ValueError("database URLs must be valid PostgreSQL psycopg URLs") from exc
        if any(
            url.drivername != "postgresql+psycopg" or not url.username or not url.host
            for url in (app_parsed, worker_parsed)
        ):
            raise ValueError("database URLs must use postgresql+psycopg with login roles")
        if app_database_url == worker_database_url:
            raise ValueError("application and worker database URLs must use distinct roles")
        if not self.cors_origins():
            raise ValueError("CORS_ALLOW_ORIGINS must not be empty in production")
        for origin in self.cors_origins():
            parsed = urlparse(origin)
            if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"}:
                raise ValueError("production CORS origins must be HTTPS origins")
        if self.LOG_FORMAT != "json":
            raise ValueError("production logs must use JSON")
        if self.REFLECTION_REVIEW_THRESHOLD != 0.80:
            raise ValueError("production reflection threshold must be 0.80")
        if self.WEB_CONCURRENCY != 1:
            raise ValueError("in-process rate limiting requires exactly one web worker")
        if not self.RATE_LIMITING_ENABLED:
            raise ValueError("rate limiting must be enabled in production")
        otel_endpoint = self.OTEL_EXPORTER_OTLP_ENDPOINT.get_secret_value().strip()
        if self.OTEL_ENABLED and (
            not otel_endpoint or urlparse(otel_endpoint).scheme != "https"
        ):
            raise ValueError("enabled OTLP export requires an HTTPS endpoint")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
