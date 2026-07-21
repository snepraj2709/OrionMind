from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def install_local_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict:
        if app.openapi_schema is None:
            schema = get_openapi(
                title=app.title,
                version=app.version,
                routes=app.routes,
            )
            components = schema.setdefault("components", {})
            schemes = components.setdefault("securitySchemes", {})
            schemes["bearerAuth"] = {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "Supabase JWT",
                "description": "Supabase access token; never a service-role key.",
            }
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi
