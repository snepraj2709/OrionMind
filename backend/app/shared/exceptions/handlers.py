from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.shared.exceptions.domain import DomainError


logger = logging.getLogger("orion.errors")


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: str
    message: str
    details: dict[str, Any]
    request_id: str


def request_id_for(request: Request) -> str:
    return getattr(request.state, "request_id", "req-unavailable")


def error_response(
    request: Request,
    *,
    status_code: int,
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error_code=error_code,
        message=message,
        details=details or {},
        request_id=request_id_for(request),
    )
    response_headers = dict(headers or {})
    response_headers.setdefault("X-Request-ID", envelope.request_id)
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers=response_headers,
    )


def _safe_validation_details(exc: RequestValidationError) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for item in exc.errors():
        fields.append(
            {
                "location": [str(part) for part in item.get("loc", ())],
                "type": str(item.get("type", "validation_error")),
                "message": str(item.get("msg", "Invalid value.")),
            }
        )
    return {"fields": fields}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return error_response(
            request,
            status_code=exc.status_code,
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=422,
            error_code="VALIDATION_ERROR",
            message="The request is invalid.",
            details=_safe_validation_details(exc),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        messages = {
            400: ("BAD_REQUEST", "The request is malformed."),
            401: ("UNAUTHORIZED", "Authentication is required."),
            404: ("NOT_FOUND", "The requested resource was not found."),
            405: ("METHOD_NOT_ALLOWED", "The request method is not allowed."),
            413: ("PAYLOAD_TOO_LARGE", "The request payload is too large."),
            415: ("UNSUPPORTED_MEDIA_TYPE", "The media type is not supported."),
            429: ("RATE_LIMITED", "Too many requests."),
            503: ("SERVICE_UNAVAILABLE", "The service is temporarily unavailable."),
        }
        error_code, message = messages.get(
            exc.status_code, ("HTTP_ERROR", "The request could not be completed.")
        )
        return error_response(
            request,
            status_code=exc.status_code,
            error_code=error_code,
            message=message,
            headers=dict(exc.headers or {}),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_request_error request_id=%s method=%s path=%s",
            request_id_for(request),
            request.method,
            request.url.path,
        )
        return error_response(
            request,
            status_code=500,
            error_code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
        )
