from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Sequence
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.shared.exceptions.handlers import error_response


logger = logging.getLogger("orion.http")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class RequestBodyTooLarge(Exception):
    pass


class HttpBoundaryMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        allow_origins: Sequence[str],
        body_limit: int,
        request_timeout: float,
        body_limit_exempt_paths: Sequence[str],
        timeout_exempt_paths: Sequence[str],
    ) -> None:
        self.app = app
        self.allow_origins = frozenset(allow_origins)
        self.body_limit = body_limit
        self.request_timeout = request_timeout
        self.body_limit_exempt_paths = frozenset(body_limit_exempt_paths)
        self.timeout_exempt_paths = frozenset(timeout_exempt_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        supplied_request_id = headers.get("x-request-id", "")
        request_id = (
            supplied_request_id
            if _REQUEST_ID.fullmatch(supplied_request_id)
            else f"req-{uuid4().hex}"
        )
        scope.setdefault("state", {})["request_id"] = request_id
        request = Request(scope, receive=receive)
        origin = headers.get("origin")

        if origin and origin not in self.allow_origins:
            response = error_response(
                request,
                status_code=403,
                error_code="CORS_ORIGIN_DENIED",
                message="The request origin is not allowed.",
            )
            await response(scope, receive, send)
            return

        enforce_body_limit = scope["path"] not in self.body_limit_exempt_paths
        content_length = headers.get("content-length") if enforce_body_limit else None
        if content_length:
            try:
                parsed_content_length = int(content_length)
                if parsed_content_length < 0:
                    raise ValueError
                if parsed_content_length > self.body_limit:
                    raise RequestBodyTooLarge
            except ValueError:
                response = error_response(
                    request,
                    status_code=400,
                    error_code="BAD_REQUEST",
                    message="The request is malformed.",
                )
                await response(scope, receive, send)
                return
            except RequestBodyTooLarge:
                response = self._payload_too_large(request)
                await response(scope, receive, send)
                return

        consumed = 0

        async def limited_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if enforce_body_limit and message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self.body_limit:
                    raise RequestBodyTooLarge
            return message

        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                mutable = MutableHeaders(scope=message)
                mutable["X-Request-ID"] = request_id
            await send(message)

        started_at = time.monotonic()
        try:
            operation = self.app(scope, limited_receive, send_with_request_id)
            if scope["path"] in self.timeout_exempt_paths:
                await operation
            else:
                await asyncio.wait_for(operation, timeout=self.request_timeout)
        except RequestBodyTooLarge:
            if not response_started:
                await self._payload_too_large(request)(scope, receive, send_with_request_id)
        except asyncio.TimeoutError:
            if not response_started:
                response = error_response(
                    request,
                    status_code=503,
                    error_code="REQUEST_TIMEOUT",
                    message="The request timed out.",
                    headers={"Retry-After": "1"},
                )
                await response(scope, receive, send_with_request_id)
        finally:
            logger.info(
                "request_complete request_id=%s method=%s path=%s duration_ms=%d",
                request_id,
                scope["method"],
                scope["path"],
                int((time.monotonic() - started_at) * 1000),
            )

    @staticmethod
    def _payload_too_large(request: Request):
        return error_response(
            request,
            status_code=413,
            error_code="PAYLOAD_TOO_LARGE",
            message="The request payload is too large.",
        )


def install_http_middleware(
    app: FastAPI,
    *,
    allow_origins: Sequence[str],
    body_limit: int,
    request_timeout: float,
    body_limit_exempt_paths: Sequence[str] = ("/api/v1/entries/voice",),
    timeout_exempt_paths: Sequence[str] = ("/api/v1/entries/voice",),
) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allow_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Request-ID",
        ],
        expose_headers=["Retry-After", "X-Request-ID", "Location", "Cache-Control"],
    )
    app.add_middleware(
        HttpBoundaryMiddleware,
        allow_origins=allow_origins,
        body_limit=body_limit,
        request_timeout=request_timeout,
        body_limit_exempt_paths=body_limit_exempt_paths,
        timeout_exempt_paths=timeout_exempt_paths,
    )
