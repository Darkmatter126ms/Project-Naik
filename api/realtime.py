"""Realtime API ephemeral-token endpoint (Block 2, Hilda's voice path).

The browser must NOT hold the real OpenAI key, so it asks this endpoint to mint
a short-lived ephemeral token via OpenAI's /v1/realtime/client_secrets. The
browser then uses that token to negotiate its WebRTC session directly with
OpenAI. The session is pre-configured here for Bahasa Indonesia transcription.

Requires OPENAI_API_KEY in the environment (Render env var + local .env).

Route:
    POST /realtime/token  ->  { "client_secret": { "value": "...", ... } }
"""

from __future__ import annotations

import os

import requests
from flask import Blueprint, jsonify

realtime_bp = Blueprint("realtime", __name__)

# GA endpoint for minting browser/mobile ephemeral credentials.
CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
REALTIME_MODEL = os.environ.get("NAIK_REALTIME_MODEL", "gpt-4o-realtime-preview")


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

    # Session config baked into the token: Indonesian input transcription,
    # server-side VAD. The browser inherits this when it connects.
    # Top-level fields — do NOT wrap in "session": {} for this endpoint.
    payload = {
        "model": REALTIME_MODEL,
        "modalities": ["audio", "text"],
        "instructions": "Anda hanya mendengarkan wawancara keuangan; jangan menjawab.",
        "input_audio_transcription": {
            "model": "gpt-4o-transcribe",
            "language": "id",
        },
        "turn_detection": {"type": "server_vad"},
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
