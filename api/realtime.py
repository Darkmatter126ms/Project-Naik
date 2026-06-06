"""Realtime API ephemeral-token endpoint (Block 2, Hilda's voice path).

The browser must NOT hold the real OpenAI key, so it asks this endpoint to mint
a short-lived ephemeral token via OpenAI's GA endpoint
``POST /v1/realtime/client_secrets``. The browser then uses that token to
negotiate its WebRTC session directly with OpenAI (``POST /v1/realtime/calls``).
The session is pre-configured here for Bahasa Indonesia transcription so the
browser inherits it.

Note (GA migration): the endpoint names changed at GA. It is
``/v1/realtime/client_secrets`` (mint) — NOT the older ``/v1/realtime/sessions``,
which now returns 404 and was the cause of the "no ephemeral token returned"
failure on the intake page. See ``design/realtime-api-notes.md``.

Requires OPENAI_API_KEY in the environment (Render env var + local .env).

Route:
    POST /realtime/token  ->  { "value": "ek_...", "expires_at": ..., ... }
"""

from __future__ import annotations

import os

import requests
from flask import Blueprint, jsonify

realtime_bp = Blueprint("realtime", __name__)

# GA endpoint for minting browser/mobile ephemeral credentials.
# IMPORTANT: this is /client_secrets, NOT the pre-GA /sessions (which 404s).
CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
# Default to the GA model name. The browser's SDP call MUST use the same model
# (see web/lib/useRealtimeVoice.ts REALTIME_MODEL) or the call is rejected.
REALTIME_MODEL = os.environ.get("NAIK_REALTIME_MODEL", "gpt-realtime")


@realtime_bp.post("/realtime/token")
def realtime_token():  # noqa: ANN202
    """Mint an ephemeral Realtime token, pre-bound to Bahasa transcription."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return (
            jsonify({
                "status": "error",
                "error": "not_configured",
                "detail": "OPENAI_API_KEY not set on the server.",
            }),
            503,
        )

    # GA shape: the client_secrets endpoint takes a `session` object whose
    # config is bound to the minted token, so the browser inherits it on connect.
    # We pin Indonesian input transcription + server-side VAD here (and the
    # browser repeats it via session.update as belt-and-suspenders). `type` must
    # be "realtime" for the GA interface.
    payload = {
        "session": {
            "type": "realtime",
            "model": REALTIME_MODEL,
            "audio": {
                "input": {
                    "transcription": {
                        "model": "gpt-4o-transcribe",
                        "language": "id",
                    },
                    "turn_detection": {"type": "server_vad"},
                },
            },
        },
    }

    try:
        resp = requests.post(
            CLIENT_SECRETS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                # Bind a privacy-preserving safety identifier to the session.
                "OpenAI-Safety-Identifier": "naik-demo",
            },
            json=payload,
            timeout=15,
        )
    except requests.RequestException as exc:
        return (
            jsonify({"status": "error", "error": "upstream_unreachable",
                     "detail": str(exc)}),
            502,
        )

    if resp.status_code >= 400:
        return (
            jsonify({"status": "error", "error": "mint_failed",
                     "detail": resp.text[:400]}),
            502,
        )

    # Pass OpenAI's response straight through (contains client_secret.value).
    return jsonify(resp.json()), 200
