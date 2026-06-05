"""Flask gateway test — real agent routes, validation errors, logging middleware.

Run from the repo root:
    python api/test_api.py
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
for p in (_ROOT, os.path.join(_ROOT, "api")):
    if p not in sys.path:
        sys.path.insert(0, p)

from api.app import create_app  # noqa: E402
from naik_agents.personas import make_sari  # noqa: E402


def main() -> int:
    ok = fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok, fail
        mark = "PASS" if cond else "FAIL"
        if cond:
            ok += 1
        else:
            fail += 1
        print(f"  {mark}  {name}" + (f"  — {detail}" if detail else ""))

    app = create_app()
    client = app.test_client()
    sari_body = make_sari().model_dump(mode="json")

    # --- /health ---------------------------------------------------------------
    print("/health")
    r = client.get("/health")
    check("health returns 200", r.status_code == 200, str(r.status_code))
    check("health is JSON with status ok", r.is_json and r.get_json().get("status") == "ok")

    # --- /orchestrate: the headline — a REAL FinalResponse ---------------------
    print("\nPOST /orchestrate (real pipeline, Sari)")
    r = client.post("/orchestrate", json=sari_body)
    body = r.get_json()
    check("orchestrate returns 200", r.status_code == 200, str(r.status_code))
    check("response carries the wellness vector", "wellness" in body)
    check("priority_gap == risk_management",
          body["wellness"]["priority_gap"] == "risk_management",
          body["wellness"].get("priority_gap"))
    check("wealth recommendation present", body.get("wealth") is not None)
    check("insurance quote present", body.get("insurance") is not None)
    check("compliance verdict present", body.get("compliance") is not None)
    check("requires_human_confirmation True",
          body["compliance"]["requires_human_confirmation"] is True)
    check("next_step is confirm_both", body.get("next_step") == "confirm_both", body.get("next_step"))
    check("at least one disclaimer", len(body.get("disclaimers", [])) >= 1)
    check("narrative is non-empty Bahasa text", bool(body.get("narrative")))
    print(f"  next_step={body.get('next_step')} | premium=Rp {body['insurance']['premium_idr']:,} "
          f"| disclaimers={len(body.get('disclaimers', []))}")

    # --- single-agent endpoints return real agent outputs ----------------------
    print("\nPOST single-agent endpoints")
    rd = client.post("/diagnostic", json=sari_body).get_json()
    check("/diagnostic returns a WellnessVector", rd.get("priority_gap") == "risk_management")
    rw = client.post("/wealth", json=sari_body).get_json()
    check("/wealth returns picks", isinstance(rw.get("picks"), list) and len(rw["picks"]) >= 1)
    ri = client.post("/insurance", json=sari_body).get_json()
    check("/insurance returns a trigger at Penjaringan",
          ri.get("trigger", {}).get("kecamatan") == "Penjaringan")
    rc = client.post("/compliance", json=sari_body).get_json()
    check("/compliance returns a verdict (is_general_guidance True)",
          rc.get("is_general_guidance") is True)

    # --- Pydantic validation → 422 ---------------------------------------------
    print("\nvalidation errors")
    bad = dict(sari_body)
    bad.pop("monthly_income_idr", None)  # drop a required field
    r422 = client.post("/orchestrate", json=bad)
    b422 = r422.get_json()
    check("missing required field → 422", r422.status_code == 422, str(r422.status_code))
    check("422 body flags validation_error", b422.get("error") == "validation_error")
    check("422 detail names the missing field",
          any("monthly_income_idr" in str(e.get("loc", "")) for e in b422.get("detail", [])))

    # Out-of-range value (age < 17) also 422
    bad2 = dict(sari_body)
    bad2["age"] = 5
    check("out-of-range value → 422", client.post("/orchestrate", json=bad2).status_code == 422)

    # Empty-signal input (no transcript, no transactions) → 422 (schema validator)
    bad3 = dict(sari_body)
    bad3["transactions"] = []
    bad3["voice_transcript"] = ""
    check("no-signal input → 422 (do-no-harm validator)",
          client.post("/diagnostic", json=bad3).status_code == 422)

    # --- wrong content type → 415 ----------------------------------------------
    print("\ncontent-type handling")
    r415 = client.post("/orchestrate", data="not json", content_type="text/plain")
    check("non-JSON body → 415", r415.status_code == 415, str(r415.status_code))

    # --- wrong method → 405, unknown route → 404 (JSON, not HTML) ---------------
    check("GET on POST-only route → 405", client.get("/orchestrate").status_code == 405)
    r404 = client.get("/nope")
    check("unknown route → 404 JSON", r404.status_code == 404 and r404.is_json)

    # --- logging middleware: correlation id echoed -----------------------------
    print("\nlogging middleware")
    r = client.post("/orchestrate", json=sari_body)
    check("response echoes an X-Request-Id header", bool(r.headers.get("X-Request-Id")))
    r2 = client.post("/orchestrate", json=sari_body, headers={"X-Request-Id": "trace-123"})
    check("provided X-Request-Id is preserved", r2.headers.get("X-Request-Id") == "trace-123")

    print(f"\nRESULT: {ok} passed, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
