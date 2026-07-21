from __future__ import annotations

from fastapi import FastAPI


PUBLIC_OPERATIONS = frozenset(
    {
        ("GET", "/health"),
        ("GET", "/api/v1/profile"),
        ("PATCH", "/api/v1/profile"),
        ("DELETE", "/api/v1/account"),
        ("GET", "/api/v1/entries"),
        ("GET", "/api/v1/entry/draft"),
        ("PUT", "/api/v1/entry/draft"),
        ("DELETE", "/api/v1/entry/draft"),
        ("POST", "/api/v1/entry"),
        ("POST", "/api/v1/past-entries"),
        ("POST", "/api/v1/entries/voice"),
        ("GET", "/api/v1/entries/{entry_id}"),
        ("POST", "/api/v1/entries/{entry_id}/retry"),
    }
)
LOCAL_DOC_OPERATIONS = frozenset(
    {
        ("GET", "/docs"),
        ("GET", "/docs/oauth2-redirect"),
        ("GET", "/openapi.json"),
    }
)


def registered_public_operations(app: FastAPI) -> frozenset[tuple[str, str]]:
    return frozenset(
        (method, route.path)
        for route in app.routes
        for method in route.methods or ()
        if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    )


def assert_public_contract(app: FastAPI) -> None:
    actual = registered_public_operations(app) - LOCAL_DOC_OPERATIONS
    if actual != PUBLIC_OPERATIONS:
        missing = sorted(PUBLIC_OPERATIONS - actual)
        unexpected = sorted(actual - PUBLIC_OPERATIONS)
        raise RuntimeError(
            f"public route contract drift: missing={missing!r} unexpected={unexpected!r}"
        )
