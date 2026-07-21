"""ASGI entrypoint kept intentionally thin."""

from app.main import create_app

app = create_app()
