"""Orchestrator test: run_naik(sari) → valid FinalResponse, parallelism, sharia path.

Run from the repo root:
    python naik_agents/test_orchestrator.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
for p in (_ROOT, os.path.join(_ROOT, "api")):
    if p not in sys.path:
        sys.path.insert(0, p)

from api.schemas import ComplianceStatus, FinalResponse, NextStep  # noqa: E402
from naik_agents.orchestrator import run_naik, run_naik_async  # noqa: E402
from naik_agents.personas import make_sari, persona_suite  # noqa: E402


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

    # --- Build-plan assertion: run_naik(sari) → valid FinalResponse ------------
    print("run_naik(sari) — the headline pipeline")
    sari = make_sari()
    res = run_naik(sari, force_heuristic=True)
    print(f"  request_id        {res.request_id}")
    print(f"  priority_gap      {res.wellness.priority_gap.value}")
    print(f"  next_step         {res.next_step.value}")
    print(f"  compliance.status {res.compliance.status.value}")
    print(f"  wealth picks      {len(res.wealth.picks) if res.wealth else 0}")
    print(f"  insurance premium Rp {res.insurance.premium_idr:,}" if res.insurance else "  no insurance")
    print(f"  disclaimers       {len(res.disclaimers)}")
    print(f"  narrative         {res.narrative[:160]}…")

    check("returns a FinalResponse", isinstance(res, FinalResponse))
    check("priority_gap == 'risk_management'", res.wellness.priority_gap.value == "risk_management")
    check("wealth recommendation present", res.wealth is not None)
    check("insurance quote present", res.insurance is not None)
    check("compliance verdict present", res.compliance is not None)
    check("is_general_guidance True", res.compliance.is_general_guidance is True)
    check("requires_human_confirmation True", res.compliance.requires_human_confirmation is True)
    check("at least one disclaimer", len(res.disclaimers) >= 1)
    check("a disclaimer requires manual confirmation",
          any("konfirmasi manual diperlukan" in d.lower() for d in res.disclaimers))
    check("next_step is CONFIRM_BOTH (both outputs, clean gate)",
          res.next_step is NextStep.CONFIRM_BOTH, res.next_step.value)
    check("narrative names the priority gap (perlindungan)", "perlindungan" in res.narrative.lower())
    check("narrative carries the insurance trigger (Penjaringan)", "penjaringan" in res.narrative.lower())
    check("user_id propagated", res.user_id == "sari")

    # --- Sharia path: halal Sari gets only sharia funds, gate still clean ------
    print("\nrun_naik(sari, sharia_only=True) — halal investor")
    res_h = run_naik(sari, sharia_only=True, force_heuristic=True)
    check("all wealth picks are sharia", all(p.is_sharia for p in res_h.wealth.picks))
    check("no sharia flag raised when picks are compliant",
          "sharia_non_compliant_fund" not in res_h.compliance.flags)
    check("still CONFIRM_BOTH on the clean sharia path", res_h.next_step is NextStep.CONFIRM_BOTH)

    # --- Parallelism: gather should overlap, not serialise ---------------------
    # Use the async core directly with two artificially-slowed agents to prove
    # wealth and insurance overlap (wall-clock < sum of the two delays).
    print("\nparallelism proof (wealth ∥ insurance overlap)")
    import naik_agents.orchestrator as orch

    real_wealth, real_ins = orch.run_wealth, orch.run_insurance

    def slow_wealth(*a, **k):
        time.sleep(0.5)
        return real_wealth(*a, **k)

    def slow_ins(*a, **k):
        time.sleep(0.5)
        return real_ins(*a, **k)

    orch.run_wealth, orch.run_insurance = slow_wealth, slow_ins
    try:
        t0 = time.perf_counter()
        asyncio.run(run_naik_async(sari, force_heuristic=True))
        elapsed = time.perf_counter() - t0
    finally:
        orch.run_wealth, orch.run_insurance = real_wealth, real_ins
    print(f"  two 0.5s agents finished in {elapsed:.2f}s (serial would be ≥1.0s)")
    check("wealth and insurance ran concurrently (<0.9s for 2×0.5s)", elapsed < 0.9, f"{elapsed:.2f}s")

    # --- Safe when called from inside a running event loop ---------------------
    print("\nrunning-loop safety")

    async def _from_loop():
        # run_naik (sync) called from within a live loop must not raise.
        return run_naik(sari, force_heuristic=True)

    res_loop = asyncio.run(_from_loop())
    check("run_naik works from inside a running loop", isinstance(res_loop, FinalResponse))

    # --- Persona sweep: every persona yields a valid, consistent FinalResponse -
    print("\npersona sweep")
    bad = []
    for inp, expected_gap in persona_suite():
        r = run_naik(inp, force_heuristic=True)
        # FinalResponse construction already validates attachment/next_step
        # agreement; just sanity-check the invariants here.
        if not (r.compliance.is_general_guidance and r.compliance.requires_human_confirmation):
            bad.append(inp.user_id)
    check("every persona → valid FinalResponse with invariants held", not bad, str(bad))

    print(f"\nRESULT: {ok} passed, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
