"""Database access for the Naik API.

A single lazily-created SQLAlchemy engine, plus a cheap connectivity probe used
by ``/health``. The engine is intentionally lazy so the web process boots even
when ``DATABASE_URL`` is unset (the health check then reports
``db: "not_configured"`` rather than crashing on import).

Render's managed Postgres hands out a URL with the ``postgres://`` scheme, which
SQLAlchemy 2.x no longer recognises; ``normalize_database_url`` rewrites it to
``postgresql://`` so the default psycopg2 driver is selected.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_LEGACY_PREFIX = "postgres://"
_CANONICAL_PREFIX = "postgresql://"


def normalize_database_url(url: Optional[str]) -> Optional[str]:
    """Return a SQLAlchemy-compatible URL, or ``None`` if unset/blank.

    Rewrites the legacy ``postgres://`` scheme (as emitted by Render/Heroku) to
    the canonical ``postgresql://`` that SQLAlchemy 2.x requires.
    """
    if not url or not url.strip():
        return None
    cleaned = url.strip()
    if cleaned.startswith(_LEGACY_PREFIX):
        cleaned = _CANONICAL_PREFIX + cleaned[len(_LEGACY_PREFIX):]
    return cleaned


@lru_cache(maxsize=1)
def get_engine() -> Optional[Engine]:
    """Return the process-wide engine, or ``None`` when no DB is configured.

    ``pool_pre_ping`` guards against Render dropping idle connections;
    ``pool_recycle`` keeps connections under the managed-Postgres idle timeout.
    Cached so repeated ``/health`` hits reuse one pool.
    """
    url = normalize_database_url(os.environ.get("DATABASE_URL"))
    if url is None:
        return None
    return create_engine(url, pool_pre_ping=True, pool_recycle=300, future=True)


def check_db() -> str:
    """Probe connectivity for ``/health``.

    Returns one of ``"ok"``, ``"not_configured"``, or ``"error"``. Never raises:
    a DB blip must not take the liveness endpoint (and thus the deploy) down.
    """
    engine = get_engine()
    if engine is None:
        return "not_configured"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:  # noqa: BLE001 — health must be total; report, don't raise
        return "error"
