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
