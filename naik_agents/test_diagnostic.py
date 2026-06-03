"""Block 4 test: Sari's diagnostic.

Build-plan requirement: on Sari's hand-crafted transcript, ``risk_management``
should score low and ``priority_gap`` should be ``'risk_management'``.

Runs the deterministic heuristic path (no API key needed), so it is reproducible
in CI and offline. Also exercises the CRRA weighting and the schema guarantee.

Run from the repo root:
    python agents/test_diagnostic.py
"""

from __future__ import annotations

import os
import sys

# Make repo-root imports work regardless of where this is invoked.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
for p in (_ROOT, os.path.join(_ROOT, "api")):
    if p not in sys.path:
        sys.path.insert(0, p)

from naik_agents.crra import crra_weights, gamma_for  # noqa: E402
from naik_agents.diagnostic import run_diagnostic, summarise_transactions  # noqa: E402
from naik_agents.personas import make_sari  # noqa: E402
from api.schemas import RiskProfile, WellnessDimension  # noqa: E402


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

    sari = make_sari()
    print("Transaction summary:")
    print("  " + summarise_transactions(sari.transactions))
    print()

    result = run_diagnostic(sari, force_heuristic=True)  # offline, deterministic
    v = result.vector
    scores = {
        "diversification": v.diversification,
        "liquidity": v.liquidity,
        "growth": v.growth,
        "risk_management": v.risk_management,
        "tax_efficiency": v.tax_efficiency,
        "emergency_fund": v.emergency_fund,
        "behavioural_resilience": v.behavioural_resilience,
    }
    print(f"Scored via: {result.source}")
    for k, val in sorted(scores.items(), key=lambda kv: kv[1]):
        bar = "█" * int(val // 4)
        print(f"  {k:24s} {val:6.1f}  {bar}")
    print(f"  {'overall':24s} {v.overall_score:6.1f}")
    print(f"\npriority_gap = {v.priority_gap.value}")
    print(f"rationale    = {v.rationale}")
    print()

    # --- Required assertions (the build-plan test) ---
    lowest_dim = min(scores, key=scores.get)
    check(
        "risk_management is the lowest-scoring dimension",
        lowest_dim == "risk_management",
        f"lowest was '{lowest_dim}' ({scores[lowest_dim]:.1f})",
    )
    check(
        "priority_gap == 'risk_management'",
        v.priority_gap is WellnessDimension.RISK_MANAGEMENT,
        f"got '{v.priority_gap.value}'",
    )
    check(
        "risk_management score is genuinely low (< 35)",
        v.risk_management < 35.0,
        f"score = {v.risk_management:.1f}",
    )

    # --- CRRA context checks ---
    w = crra_weights(RiskProfile.CONSERVATIVE)
    rm_w = w[WellnessDimension.RISK_MANAGEMENT]
    gr_w = w[WellnessDimension.GROWTH]
    check(
        "conservative CRRA weights protective > growth",
        rm_w > gr_w,
        f"risk_mgmt={rm_w:.3f} > growth={gr_w:.3f}, gamma={gamma_for(RiskProfile.CONSERVATIVE):.1f}",
    )
    check("CRRA weights sum to ~1.0", abs(sum(w.values()) - 1.0) < 1e-2)

    # --- Schema guarantee check (priority_gap can't disagree with data) ---
    check(
        "schema confirms priority_gap is a minimum dimension",
        abs(scores[v.priority_gap.value] - min(scores.values())) < 1e-6,
    )

    print(f"\nRESULT: {ok} passed, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
