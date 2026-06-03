"""Block 1 test: the wealth agent.

Build-plan requirements for the wealth output (the parts this block owns):
  * returns the top 3 OJK-licensed funds, best-first, as a valid WealthRecommendation;
  * for a halal persona, the top fund is sharia-compliant;
  * for an irregular-income / protection-first persona (Sari), the ranking tilts
    to capital-preserving pasar uang, the effective risk profile is conservative,
    and the justification names the irregular income (the Shopee wedge);
  * the result is deterministic (same inputs -> same ordering).

Runs the deterministic heuristic path (no API key), so it is reproducible in CI
and offline.

Run from the repo root:
    python agents/test_wealth.py
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

from naik_agents.diagnostic import run_diagnostic  # noqa: E402
from naik_agents.personas import make_sari  # noqa: E402
from naik_agents.wealth import run_wealth  # noqa: E402
from api.schemas import FundRiskLevel, FundType, RiskProfile  # noqa: E402


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

    # Diagnose Sari first (offline), then rank funds for her as a halal investor.
    sari = make_sari()
    wellness = run_diagnostic(sari, force_heuristic=True).vector
    print(f"Sari priority_gap = {wellness.priority_gap.value}, "
          f"risk_management = {wellness.risk_management:.1f}\n")

    result = run_wealth(wellness, sari, sharia_only=True, force_heuristic=True)
    rec = result.recommendation

    print(f"Scored via: {result.source}")
    print(f"effective risk profile used = {rec.risk_profile_used.value}")
    print(f"monthly contribution = Rp {rec.recommended_monthly_contribution_idr:,}")
    print(f"allocation_pct = {rec.allocation_pct}\n")
    print("Ranked picks (best-first):")
    for i, p in enumerate(rec.picks, 1):
        sharia = "syariah" if p.is_sharia else "konvensional"
        print(f"  {i}. [{p.match_score:5.1f}] {p.fund_name[:40]:42s} "
              f"{p.fund_type.value:16s} {p.risk_level.value:7s} {sharia} er={p.expense_ratio_pct:.2f}")
        print(f"       -> {p.rationale}")
    print(f"\nrationale: {rec.rationale}\n")

    top = rec.picks[0]

    # --- Required checks (build plan) ---
    check("returns exactly 3 picks", len(rec.picks) == 3, f"got {len(rec.picks)}")
    check(
        "picks are ordered best-first by match_score",
        all(rec.picks[i].match_score >= rec.picks[i + 1].match_score for i in range(len(rec.picks) - 1)),
        f"scores={[p.match_score for p in rec.picks]}",
    )
    check("top fund is sharia-compliant (halal persona)", top.is_sharia, top.fund_name)
    check("every pick is sharia-compliant under sharia_only", all(p.is_sharia for p in rec.picks))
    check(
        "top fund is capital-preserving (pasar uang / pendapatan tetap)",
        top.fund_type in (FundType.MONEY_MARKET, FundType.FIXED_INCOME),
        top.fund_type.value,
    )
    check("top fund is low risk", top.risk_level is FundRiskLevel.LOW, top.risk_level.value)
    check(
        "effective risk profile is conservative (protection-first, gig income)",
        rec.risk_profile_used is RiskProfile.CONSERVATIVE,
        rec.risk_profile_used.value,
    )
    check(
        "justification names irregular income (the Shopee wedge)",
        ("tidak tetap" in (top.rationale or "").lower())
        or ("tidak tetap" in rec.rationale.lower()),
        "looked for 'tidak tetap'",
    )
    check("every pick is OJK-licensed", all(p.is_ojk_licensed for p in rec.picks))

    # --- Determinism ---
    again = run_wealth(wellness, sari, sharia_only=True, force_heuristic=True).recommendation
    check(
        "ranking is deterministic across runs",
        [p.fund_id for p in again.picks] == [p.fund_id for p in rec.picks],
    )

    # --- The wedge actually moves the ranking ---
    # An aggressive, well-protected, salaried investor (no protection gap, no
    # irregular income) should get a growthier top pick than Sari does.
    growth_persona = make_sari()
    growth_persona = growth_persona.model_copy(update={
        "user_id": "growth-investor",
        "is_gig_worker": False,
        "risk_tolerance": RiskProfile.AGGRESSIVE,
        "voice_transcript": (
            "Saya sudah punya asuransi lengkap dan dana darurat enam bulan. Saya "
            "ingin pertumbuhan jangka panjang dan nyaman dengan risiko tinggi."
        ),
    })
    gw_wellness = run_diagnostic(growth_persona, force_heuristic=True).vector
    gw_rec = run_wealth(gw_wellness, growth_persona, sharia_only=False, force_heuristic=True).recommendation
    print(f"growth-investor effective profile = {gw_rec.risk_profile_used.value}, "
          f"top fund = {gw_rec.picks[0].fund_name} ({gw_rec.picks[0].fund_type.value})")
    check(
        "wedge works: growth persona ranks a riskier fund-type than Sari",
        _type_growthiness(gw_rec.picks[0].fund_type) > _type_growthiness(top.fund_type),
        f"growth top={gw_rec.picks[0].fund_type.value} vs sari top={top.fund_type.value}",
    )

    print(f"\nRESULT: {ok} passed, {fail} failed")
    return 1 if fail else 0


def _type_growthiness(t: FundType) -> int:
    """Ordinal 'growthiness' of a fund type for comparing rankings."""
    order = {
        FundType.MONEY_MARKET: 0,
        FundType.FIXED_INCOME: 1,
        FundType.BALANCED: 2,
        FundType.INDEX: 3,
        FundType.EQUITY: 4,
    }
    return order[t]


if __name__ == "__main__":
    raise SystemExit(main())
