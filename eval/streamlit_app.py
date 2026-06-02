"""Naik — ops / eval dashboard (Streamlit).

Block 2 role: a second deployed client that independently proves the cloud path
by pinging the Flask API's ``/health`` and rendering the response. Later blocks
grow this into the 50-persona evaluation dashboard (suitability, fund-rank
correctness, claim-trigger precision, do-no-harm guardrail).

Deploy on Streamlit Community Cloud with:
    Main file path : eval/streamlit_app.py
    Dependencies   : eval/requirements.txt
    Secret/env     : API_BASE_URL = https://naik-api.onrender.com
"""

from __future__ import annotations

import os

import requests
import streamlit as st

DEFAULT_API_BASE = os.environ.get("API_BASE_URL", "http://localhost:5050")
REQUEST_TIMEOUT_S = 10

st.set_page_config(page_title="Naik · Ops", page_icon="📈", layout="centered")

st.title("Naik — Ops & Eval")
st.caption("Cloud-path probe and (soon) the 50-persona evaluation dashboard.")

api_base = st.text_input(
    "API base URL",
    value=DEFAULT_API_BASE,
    help="The deployed Render backend, e.g. https://naik-api.onrender.com",
).rstrip("/")

if st.button("Ping /health", type="primary"):
    url = f"{api_base}/health"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        payload = resp.json()
    except requests.exceptions.RequestException as exc:
        st.error(f"Could not reach {url}\n\n{exc}")
    except ValueError:
        st.error(f"Reached {url} but the response was not JSON.")
    else:
        ok = payload.get("status") == "ok"
        st.success("Backend reachable ✓" if ok else "Reached backend, status not ok")
        col1, col2, col3 = st.columns(3)
        col1.metric("Status", payload.get("status", "?"))
        col2.metric("Version", payload.get("version", "?"))
        col3.metric("Database", payload.get("db", "?"))
        st.json(payload)

st.divider()
st.info(
    "Placeholder surface. The evaluation harness (scenario library + scorers) "
    "is wired in a later block.",
    icon="🧭",
)
