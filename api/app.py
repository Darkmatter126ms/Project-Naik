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

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from flask import Flask, g, jsonify, request
from flask_cors import CORS

from .config import Config
from .db import check_db, get_engine
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

    # --- Logging + request/response middleware --------------------------------
    # Configure a stream handler once (idempotent across factory calls/imports).
    _logger = logging.getLogger("naik.api")
    if not _logger.handlers:
        _handler = logging.StreamHandler()
        _handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        _logger.addHandler(_handler)
        _logger.setLevel(getattr(logging, getattr(cfg, "log_level", "INFO"), logging.INFO))
        _logger.propagate = False

    @app.before_request
    def _start_request():  # noqa: ANN202
        """Stamp each request with a correlation id and a start time."""
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        g.start_time = time.perf_counter()

    @app.after_request
    def _log_request(response):  # noqa: ANN001, ANN202
        """Emit one structured line per request and echo the correlation id."""
        duration_ms = (time.perf_counter() - getattr(g, "start_time", time.perf_counter())) * 1000.0
        req_id = getattr(g, "request_id", "-")
        _logger.info(
            "%s %s -> %d (%.1f ms) req=%s",
            request.method, request.path, response.status_code, duration_ms, req_id,
        )
        response.headers["X-Request-Id"] = req_id
        return response

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

    @app.get("/eval-summary")
    def eval_summary():  # noqa: ANN202
        """Aggregate eval metrics for the Vercel eval page metric cards.

        Returns the mean score across the four eval metrics, taken from the
        most recent run per persona (so re-running run_eval.py does not skew
        the averages). When no eval data exists the endpoint returns status
        ``"no_data"`` with null metrics so the frontend can show ``"—"``
        gracefully without treating it as an error.

        Response shape::

            {
              "status":                  "ok" | "no_data" | "error",
              "personas_evaluated":      50,
              "suitability":             0.980,
              "fund_rank_correctness":   1.000,
              "claim_trigger_precision": 0.960,
              "do_no_harm":              1.000,
              "last_run":                "2026-06-05T09:41:00+00:00"
            }
        """
        from sqlalchemy import text as sqlt

        engine = get_engine()

        # No DB configured — return no_data, not an error (keeps the page clean
        # during local dev without a Postgres instance).
        if engine is None:
            return jsonify(_no_data_payload())

        try:
            with engine.connect() as conn:
                row = conn.execute(sqlt("""
                    WITH latest AS (
                        SELECT DISTINCT ON (persona_id)
                            scores,
                            COALESCE(created_at, NOW()) AS created_at
                        FROM eval_runs
                        ORDER BY persona_id, created_at DESC NULLS LAST
                    )
                    SELECT
                        COUNT(*)                                         AS personas_evaluated,
                        AVG((scores->>'suitability')::float)             AS suitability,
                        AVG((scores->>'fund_rank_correctness')::float)   AS fund_rank_correctness,
                        AVG((scores->>'claim_trigger_precision')::float) AS claim_trigger_precision,
                        AVG((scores->>'do_no_harm')::float)              AS do_no_harm,
                        MAX(created_at)                                  AS last_run
                    FROM latest
                    WHERE (scores->>'success')::boolean = true
                """)).fetchone()

            if row is None or (row[0] or 0) == 0:
                return jsonify(_no_data_payload())

            def _round(v: object) -> Optional[float]:
                return round(float(v), 3) if v is not None else None

            last_run = row[5]
            return jsonify({
                "status":                  "ok",
                "personas_evaluated":      int(row[0]),
                "suitability":             _round(row[1]),
                "fund_rank_correctness":   _round(row[2]),
                "claim_trigger_precision": _round(row[3]),
                "do_no_harm":              _round(row[4]),
                "last_run": (
                    last_run.isoformat()
                    if hasattr(last_run, "isoformat") else str(last_run)
                ) if last_run else None,
            })

        except Exception:  # noqa: BLE001
            _logger.exception("eval-summary query failed")
            return jsonify({"status": "error", "error": "query_failed"}), 500

    @app.errorhandler(404)
    def not_found(_err):  # noqa: ANN001, ANN202
        """Return JSON (not HTML) for unknown routes — friendlier to fetch()."""
        return jsonify({"status": "error", "error": "not_found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_err):  # noqa: ANN001, ANN202
        """JSON for wrong-method requests (e.g. GET on a POST-only route)."""
        return jsonify({"status": "error", "error": "method_not_allowed"}), 405

    @app.errorhandler(500)
    def internal_error(_err):  # noqa: ANN001, ANN202
        """JSON (not an HTML stack trace) for any unhandled server error."""
        logging.getLogger("naik.api").exception("unhandled error")
        return jsonify({"status": "error", "error": "internal_error"}), 500

    # Agent gateway routes — real agent pipeline (diagnostic, wealth, insurance,
    # compliance, orchestrate).
    from .routes import agents_bp

    app.register_blueprint(agents_bp)

    # Realtime API ephemeral-token endpoint (voice path).
    from .realtime import realtime_bp

    app.register_blueprint(realtime_bp)

    # Pre-warm the pricing GLM in a background thread so the first real
    # /orchestrate request after a Render dyno wake doesn't bear the ~1s
    # joblib cold-load cost. The lru_cache in tools.py persists the loaded
    # model for the lifetime of the process.
    import threading

    def _prewarm_glm() -> None:
        try:
            from naik_agents.tools import _load_pricing_bundle, _model_path
            _load_pricing_bundle(str(_model_path()))
            _logger.info("GLM pricing model pre-warmed.")
        except Exception:  # noqa: BLE001 — warm-up is best-effort
            pass

    threading.Thread(target=_prewarm_glm, daemon=True, name="glm-prewarm").start()

    return app


def _no_data_payload() -> dict:
    """Shared empty-state payload when eval_runs has no successful rows."""
    return {
        "status":                  "no_data",
        "personas_evaluated":      0,
        "suitability":             None,
        "fund_rank_correctness":   None,
        "claim_trigger_precision": None,
        "do_no_harm":              None,
        "last_run":                None,
    }
