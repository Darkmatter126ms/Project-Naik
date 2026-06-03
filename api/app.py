"""Naik API — Flask application factory.

Block 2 scope: a deployable web service with a real ``/health`` endpoint, CORS
configured so the Vercel frontend can reach it cross-origin, and a live Postgres
connectivity probe. The four agent endpoints (``/diagnostic``, ``/wealth``,
``/insurance``, ``/compliance``) land in later blocks; this file is structured
as a factory so they can be added as blueprints without churn.

Run locally:
    cd <repo root>
    flask --app api.wsgi run --port 5050        # or: gunicorn api.wsgi:app
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from flask import Flask, jsonify
from flask_cors import CORS

from .config import Config
from .db import check_db
from .schemas import SCHEMA_VERSION


def create_app(config: Optional[Config] = None) -> Flask:
    """Construct and configure the Flask app.

    Accepts an optional ``Config`` for tests; defaults to reading the
    environment so production and local runs need no arguments.
    """
    app = Flask(__name__)
    cfg = config or Config.from_env()

    # CORS: the deployed Vercel origin must be able to fetch /health. Scope to
    # cfg.cors_origins (default "*" for the public health proof; tighten to the
    # Vercel URL for production via the CORS_ORIGINS env var).
    CORS(app, resources={r"/*": {"origins": cfg.cors_origins}})

    @app.get("/")
    def root():  # noqa: ANN202
        """Service banner — points callers at the health endpoint."""
        return jsonify(
            {
                "service": "naik-api",
                "status": "ok",
                "message": "Naik API. See /health for liveness and DB status.",
            }
        )

    @app.get("/health")
    def health():  # noqa: ANN202
        """Liveness + dependency status.

        Always returns 200 when the process is up. ``db`` is informational
        ("ok" / "not_configured" / "error") so a transient DB issue never marks
        the service unhealthy and blocks a deploy.
        """
        return jsonify(
            {
                "service": "naik-api",
                "status": "ok",
                "version": cfg.app_version,
                "schema_version": SCHEMA_VERSION,
                "time": datetime.now(timezone.utc).isoformat(),
                "db": check_db(),
            }
        )

    @app.errorhandler(404)
    def not_found(_err):  # noqa: ANN001, ANN202
        """Return JSON (not HTML) for unknown routes — friendlier to fetch()."""
        return jsonify({"status": "error", "error": "not_found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_err):  # noqa: ANN001, ANN202
        """JSON for wrong-method requests (e.g. GET on a POST-only route)."""
        return jsonify({"status": "error", "error": "method_not_allowed"}), 405

    # Agent gateway routes (Block 1 stubs; real agents wire in Phase 2).
    from .routes import agents_bp

    app.register_blueprint(agents_bp)

    # Realtime API ephemeral-token endpoint (voice path).
    from .realtime import realtime_bp

    app.register_blueprint(realtime_bp)

    return app
