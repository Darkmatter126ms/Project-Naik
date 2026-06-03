"""Naik API — agent gateway routes (Block 1 stubs).

Five POST endpoints mirroring the agent pipeline:

    POST /diagnostic   DiagnosticInput  -> WellnessVector
    POST /wealth       DiagnosticInput  -> WealthRecommendation
    POST /insurance    DiagnosticInput  -> InsuranceQuote
    POST /compliance   DiagnosticInput  -> ComplianceVerdict
    POST /orchestrate  DiagnosticInput  -> FinalResponse

Every endpoint validates its JSON body against the expected Pydantic model and
returns a 422 with field-level errors on failure. On success it returns a
hardcoded, schema-valid stub (see ``api.stubs``). Real agent calls replace the
stub bodies in Phase 2; the request/response contract does not change.

Design choice: all five endpoints accept the SAME input model
(``DiagnosticInput``). The frontend only ever holds the user's intake data, so a
single request shape lets Hilda call any endpoint with one payload tonight.
Endpoints that will later need upstream context (wealth/insurance/compliance)
derive everything they need from the stub for now.
"""

from __future__ import annotations

from typing import Callable
from uuid import uuid4

from flask import Blueprint, jsonify, request
from pydantic import BaseModel, ValidationError

from .schemas import DiagnosticInput
from . import stubs

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


def _stub_route(produce: Callable[[DiagnosticInput], BaseModel]):
    """Build a view function: validate DiagnosticInput, then return a stub.

    ``produce`` maps the validated input to the output model. Kept generic so
    Phase 2 can swap ``produce`` for a real agent call without touching the
    validation/serialisation plumbing.
    """

    def view():  # noqa: ANN202
        inp, err = _validate(DiagnosticInput)
        if err is not None:
            return err
        assert isinstance(inp, DiagnosticInput)  # for type-checkers
        result = produce(inp)
        return jsonify(result.model_dump(mode="json")), 200

    return view


# --- /diagnostic -------------------------------------------------------------
agents_bp.add_url_rule(
    "/diagnostic", view_func=_stub_route(lambda _inp: stubs.stub_wellness()),
    methods=["POST"], endpoint="diagnostic",
)

# --- /wealth -----------------------------------------------------------------
agents_bp.add_url_rule(
    "/wealth", view_func=_stub_route(lambda _inp: stubs.stub_wealth()),
    methods=["POST"], endpoint="wealth",
)

# --- /insurance --------------------------------------------------------------
agents_bp.add_url_rule(
    "/insurance", view_func=_stub_route(lambda _inp: stubs.stub_insurance()),
    methods=["POST"], endpoint="insurance",
)

# --- /compliance -------------------------------------------------------------
agents_bp.add_url_rule(
    "/compliance", view_func=_stub_route(lambda _inp: stubs.stub_compliance()),
    methods=["POST"], endpoint="compliance",
)


# --- /orchestrate ------------------------------------------------------------
@agents_bp.post("/orchestrate")
def orchestrate():  # noqa: ANN202
    """Full-pipeline stub: validate input, return an assembled FinalResponse.

    Uses the input's ``user_id`` so the response correlates with the request;
    generates a fresh ``request_id`` per call.
    """
    inp, err = _validate(DiagnosticInput)
    if err is not None:
        return err
    assert isinstance(inp, DiagnosticInput)
    result = stubs.stub_final_response(
        request_id=f"req-{uuid4().hex[:12]}",
        user_id=inp.user_id,
    )
    return jsonify(result.model_dump(mode="json")), 200
