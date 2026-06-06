"""Naik API — agent gateway routes.

Five POST endpoints, each driving the real agent pipeline:

    POST /diagnostic   DiagnosticInput -> WellnessVector
    POST /wealth       DiagnosticInput -> WealthRecommendation
    POST /insurance    DiagnosticInput -> InsuranceQuote
    POST /compliance   DiagnosticInput -> ComplianceVerdict
    POST /orchestrate  DiagnosticInput -> FinalResponse

Every endpoint validates its JSON body against ``DiagnosticInput`` and returns a
422 with field-level errors on failure (see ``_validate``). On success it runs
the corresponding agent(s) and returns the validated model as JSON.

Design choices:
* All five endpoints accept the SAME input model (``DiagnosticInput``) — the
  frontend only ever holds the user's intake, so one payload reaches any route.
* The single-agent endpoints (/diagnostic, /wealth, /insurance) return that
  agent's RAW output (running diagnostic first where a WellnessVector is needed).
  /compliance and /orchestrate run the full pipeline; /orchestrate returns the
  compliance-gated FinalResponse, /compliance returns just the verdict.
* The agents own all asyncio: ``run_naik`` is a synchronous entry point that runs
  the parallel wealth∥insurance fan-out via ``asyncio.run`` internally (with a
  running-loop guard), so these sync WSGI views just call it.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Callable

from flask import Blueprint, jsonify, request
from pydantic import BaseModel, ValidationError

# Make the repo root importable so `naik_agents` resolves regardless of CWD
# (the agents in turn import `api.schemas`, which also needs the repo root).
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from .schemas import DiagnosticInput  # noqa: E402
from naik_agents.diagnostic import run_diagnostic  # noqa: E402
from naik_agents.insurance import run_insurance  # noqa: E402
from naik_agents.orchestrator import run_naik  # noqa: E402
from naik_agents.wealth import resolve_sharia_only, run_wealth  # noqa: E402

logger = logging.getLogger("naik.api")

agents_bp = Blueprint("agents", __name__)


def _validate(model: type[BaseModel]) -> tuple[BaseModel | None, tuple | None]:
    """Parse and validate the request JSON against ``model``.

    Returns ``(instance, None)`` on success, or ``(None, (response, status))``
    on failure so the caller can ``return`` it directly. Handles three failure
    modes distinctly: non-JSON body, malformed JSON, and schema-invalid JSON.
    """
    if not request.is_json:
        return None, (
            jsonify({
                "status": "error",
                "error": "unsupported_media_type",
                "detail": "Content-Type must be application/json.",
            }),
            415,
        )
    try:
        payload = request.get_json(silent=False)
    except Exception:  # noqa: BLE001 - malformed JSON body
        return None, (
            jsonify({
                "status": "error",
                "error": "invalid_json",
                "detail": "Request body is not valid JSON.",
            }),
            400,
        )
    if payload is None:
        return None, (
            jsonify({
                "status": "error",
                "error": "empty_body",
                "detail": "Request body is empty; expected a JSON object.",
            }),
            400,
        )
    try:
        instance = model.model_validate(payload)
    except ValidationError as exc:
        # errors() can include a non-serialisable ``ctx`` (e.g. the original
        # exception raised by a model validator). Strip ctx to keep the 422
        # body JSON-safe while preserving the useful loc/msg/type fields.
        safe_errors = [
            {k: v for k, v in err.items() if k != "ctx"}
            for err in exc.errors(include_url=False)
        ]
        return None, (
            jsonify({
                "status": "error",
                "error": "validation_error",
                "model": model.__name__,
                "detail": safe_errors,
            }),
            422,
        )
    return instance, None


def _agent_route(produce: Callable[[DiagnosticInput], BaseModel]):
    """Build a view: validate DiagnosticInput, run ``produce``, serialise.

    Wraps the agent call so an unexpected agent failure becomes a clean JSON 500
    (with a correlation id), never an HTML stack trace leaked to the client.
    """

    def view():  # noqa: ANN202
        inp, err = _validate(DiagnosticInput)
        if err is not None:
            return err
        assert isinstance(inp, DiagnosticInput)  # for type-checkers
        try:
            result = produce(inp)
        except Exception:  # noqa: BLE001 - agent failure must not leak a stack trace
            logger.exception("agent error on %s for user=%s", request.path, inp.user_id)
            return (
                jsonify({
                    "status": "error",
                    "error": "agent_error",
                    "detail": "The pipeline failed to produce a result.",
                }),
                500,
            )
        return jsonify(result.model_dump(mode="json")), 200

    return view


# --- produce functions: each maps a validated DiagnosticInput to a model -----


def _produce_diagnostic(inp: DiagnosticInput) -> BaseModel:
    return run_diagnostic(inp).vector


def _produce_wealth(inp: DiagnosticInput) -> BaseModel:
    vector = run_diagnostic(inp).vector
    sharia = resolve_sharia_only(inp, None)
    return run_wealth(vector, inp, sharia_only=sharia).recommendation


def _produce_insurance(inp: DiagnosticInput) -> BaseModel:
    vector = run_diagnostic(inp).vector
    return run_insurance(vector, inp).quote


def _produce_compliance(inp: DiagnosticInput) -> BaseModel:
    # Full pipeline, but surface only the gate verdict.
    return run_naik(inp).compliance


agents_bp.add_url_rule("/diagnostic", view_func=_agent_route(_produce_diagnostic),
                       methods=["POST"], endpoint="diagnostic")
agents_bp.add_url_rule("/wealth", view_func=_agent_route(_produce_wealth),
                       methods=["POST"], endpoint="wealth")
agents_bp.add_url_rule("/insurance", view_func=_agent_route(_produce_insurance),
                       methods=["POST"], endpoint="insurance")
agents_bp.add_url_rule("/compliance", view_func=_agent_route(_produce_compliance),
                       methods=["POST"], endpoint="compliance")


# --- /orchestrate ------------------------------------------------------------
@agents_bp.post("/orchestrate")
def orchestrate():  # noqa: ANN202
    """Full pipeline: validate input, run run_naik, return the FinalResponse.

    ``run_naik`` runs diagnostic, then wealth ∥ insurance in parallel
    (``asyncio.gather`` under an internal ``asyncio.run``), then the compliance
    gate, and assembles a validated FinalResponse.
    """
    inp, err = _validate(DiagnosticInput)
    if err is not None:
        return err
    assert isinstance(inp, DiagnosticInput)
    try:
        result = run_naik(inp)
    except Exception:  # noqa: BLE001
        logger.exception("orchestrate error for user=%s", inp.user_id)
        return (
            jsonify({
                "status": "error",
                "error": "agent_error",
                "detail": "The pipeline failed to produce a result.",
            }),
            500,
        )
    return jsonify(result.model_dump(mode="json")), 200


# --- /issue + /admin/issue-form -----------------------------------------------

from pathlib import Path as _Path
from flask import send_file as _send_file
from .schemas import IssuanceRequest, IssuanceResponse  # noqa: E402


@agents_bp.get("/admin/issue-form")
def admin_issue_form():  # noqa: ANN202
    """Serve the MoneeInsure mock admin UI at a stable Flask URL.

    Both the Playwright driver (server-side) and the iframe (browser-side) use
    this URL so there is a single source of HTML.  No X-Frame-Options is set,
    which means any origin can embed the iframe — intentional for the
    cross-origin Vercel → Render demo configuration.
    """
    html_path = _Path(__file__).resolve().parent.parent / "eval" / "mock_admin_ui.html"
    return _send_file(html_path, mimetype="text/html", max_age=0)


@agents_bp.post("/issue")
def issue():  # noqa: ANN202
    """Issue a MoneeInsure policy from a pre-computed InsuranceQuote + persona.

    Request body: ``IssuanceRequest`` (quote + persona identity).
    Returns: ``IssuanceResponse`` (form_data the iframe will animate + the
    issuance result containing polis_id, status, timestamps, etc.)

    Playwright is best-effort: if it is not installed on this host (Render
    free tier does not include headless browsers), the endpoint still returns
    200 with valid form_data and a server-generated polis_id so the iframe
    can animate the fill theatrically without blocking the demo.
    """
    import time as _time
    import datetime as _dt

    # -- Parse + validate ------------------------------------------------------
    body = request.get_json(silent=True) or {}
    try:
        req = IssuanceRequest.model_validate(body)
    except Exception as exc:  # noqa: BLE001
        return (
            jsonify({"status": "error", "error": "validation_error", "detail": str(exc)}),
            422,
        )

    # -- Build form data (deterministic — always succeeds) ---------------------
    from naik_agents.computer_use import (
        build_form_data_from_quote_and_persona,
        assert_submittable,
    )

    quote_dict   = req.quote.model_dump(mode="json")
    persona_dict = req.persona.model_dump(mode="json")

    try:
        form_data = build_form_data_from_quote_and_persona(quote_dict, persona_dict)
        assert_submittable(form_data)
    except ValueError as exc:
        return (
            jsonify({"status": "error", "error": "form_invalid", "detail": str(exc)}),
            422,
        )

    # -- Generate a polis_id server-side (matches the admin UI's genPolisId()) --
    def _server_polis_id(kecamatan: str) -> str:
        """MNI-{KECfirst4}-{timestamp-base36-last6} — identical format to the UI."""
        kec_prefix = kecamatan.replace(" ", "").upper()[:4]
        ts = int(_time.time() * 1000)
        chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        result = ""
        n = ts
        while n:
            result = chars[n % 36] + result
            n //= 36
        ts_b36 = (result or "0")[-6:]
        return f"MNI-{kec_prefix}-{ts_b36}"

    kecamatan = req.quote.trigger.kecamatan
    now_iso   = _dt.datetime.now(_dt.timezone.utc).isoformat()

    # -- Best-effort Playwright issuance (skipped silently if not installed) ---
    issuance: dict = {}
    try:
        from naik_agents.computer_use import run_issuance
        issuance = run_issuance(form_data)
    except Exception as exc:  # noqa: BLE001  – playwright absent or any error
        logger.warning(
            "playwright issuance skipped for user=%s (%s: %s) — using generated polis_id",
            req.persona.user_id, type(exc).__name__, exc,
        )

    # -- If playwright succeeded, use its polis_id; otherwise generate one -----
    if not issuance.get("polis_id"):
        issuance = {
            "status":                    "issued",
            "polis_id":                  _server_polis_id(kecamatan),
            "user_id":                   req.persona.user_id,
            "applicant_name":            form_data.get("applicant_name", req.persona.user_id.title()),
            "kecamatan":                 kecamatan,
            "trigger_metric":            quote_dict["trigger"]["metric"],
            "trigger_threshold":         quote_dict["trigger"]["threshold"],
            "payout_per_event_idr":      req.quote.payout_per_event_idr,
            "premium_idr":               req.quote.premium_idr,
            "coverage_term_days":        req.quote.coverage_term_days,
            "start_date":                form_data.get("start_date", now_iso[:10]),
            "end_date":                  form_data.get("end_date", ""),
            "requires_human_confirmation": True,
            "issued_at":                 now_iso,
            "source":                    "server_generated",
        }

    # -- Return ----------------------------------------------------------------
    resp = IssuanceResponse(form_data=form_data, issuance=issuance)
    return jsonify(resp.model_dump(mode="json")), 200
