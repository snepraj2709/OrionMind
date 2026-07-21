from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def install_user_rls_context(session: Session, user_id: UUID) -> None:
    claims = json.dumps({"sub": str(user_id), "role": "authenticated"}, separators=(",", ":"))
    session.execute(text("SET LOCAL ROLE authenticated"))
    session.execute(
        text("SELECT pg_catalog.set_config('request.jwt.claims', :claims, true)"),
        {"claims": claims},
    )


def install_worker_role(session: Session) -> None:
    session.execute(text("SET LOCAL ROLE orion_worker"))
