"""Runtime configuration for the Naik API, sourced from environment variables.

Render injects ``DATABASE_URL`` (via the Blueprint's ``fromDatabase`` binding)
and any vars declared in ``render.yaml``. Locally, an ``.env`` (see
``.env.example``) or plain shell exports work. Nothing here is secret-bearing —
secrets live only in the platform's env store, never in the repo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Union

# flask-cors accepts either the literal "*" or an explicit list of origins.
CorsOrigins = Union[str, list[str]]


def _parse_origins(raw: str | None) -> CorsOrigins:
    """Parse the CORS_ORIGINS env var.

    "*" (or empty) -> allow any origin (fine for a public /health proof).
    Otherwise a comma-separated allowlist -> a list of exact origins.
    """
    value = (raw or "*").strip()
    if value in ("", "*"):
        return "*"
    return [origin.strip() for origin in value.split(",") if origin.strip()]


@dataclass(frozen=True)
class Config:
    """Immutable view of the process configuration."""

    app_version: str = "0.1.0"
    cors_origins: CorsOrigins = "*"

    @classmethod
    def from_env(cls) -> "Config":
        """Build configuration from the current environment."""
        return cls(
            app_version=os.environ.get("APP_VERSION", "0.1.0"),
            cors_origins=_parse_origins(os.environ.get("CORS_ORIGINS")),
        )
