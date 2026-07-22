from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI


CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "contracts"
    / "profile-entry-v1.openapi.json"
)


def install_local_openapi(app: FastAPI) -> None:
    frozen = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def custom_openapi() -> dict:
        if app.openapi_schema is None:
            app.openapi_schema = frozen
        return app.openapi_schema

    setattr(app, "openapi", custom_openapi)
