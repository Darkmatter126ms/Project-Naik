"""WSGI entrypoint for gunicorn / Render.

Render start command: ``gunicorn api.wsgi:app`` (run from the repo root, where
``api`` is an importable package).
"""

from .app import create_app

app = create_app()
