"""Compliance agent test: the four OJK rules + clean pass-through + idempotency.

Run from the repo root:
    python naik_agents/test_compliance.py
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
for p in (_ROOT, os.path.join(_ROOT, "api")):
    if p not in sys.path:
        sys.path.insert(0, p)

from api.schemas import (  # noqa: E402
    ComplianceStatus,
    FundPick,
    FundRiskLevel,
    FundType,
    RiskProfile,
    WealthRecommendation,
)
from naik_agents.compliance import run_compliance, sanitize_text  # noqa: E402
from naik_agents.diagnostic import run_diagnostic  # noqa: E402
from naik_agents.insurance import run_insurance  # noqa: E402
from naik_agents.personas import make_sari  # noqa: E402
from naik_agents.wealth import run_wealth  # noqa: E402


def _pick(rationale: str, *, is_sharia: bool = True, fund_id: str = "F1") -> FundPick:
    return FundPick(
        fund_id=fund_id,
        fund_name="Test Fund",
        fund_type=FundType.MONEY_MARKET,
        manager="Test MI",
        risk_level=FundRiskLevel.LOW,
        expense_ratio_pct=1.0,
        min_investment_idr=10_000,
        is_ojk_licensed=True,
        is_sharia=is_sharia,
        match_score=80.0,
        rationale=rationale,
    )


def _reco(picks, rationale: str, user_id: str = "tester") -> WealthRecommendation:
    return WealthRecommendation(
        user_id=user_id,
        risk_profile_used=RiskProfile.CONSERVATIVE,
        investment_horizon_years=3.0,
        recommended_monthly_contribution_idr=300_000,
        picks=picks,
        rationale=rationale,
    )


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

    # --- Clean pass-through: Sari's real outputs should not be rewritten -------
    print("clean pass-through (Sari's real heuristic outputs)")
    sari = make_sari()
    wellness = run_diagnostic(sari).vector
    wealth = run_wealth(wellness, sari, force_heuristic=True).recommendation
    ins = run_insurance(wellness, sari, force_heuristic=True)
    res = run_compliance(
        wealth=wealth, insurance=ins.quote, insurance_description=ins.bahasa_description,
        wellness=wellness, inp=sari,
    )
    v = res.verdict
    print(f"  status={v.status.value}  flags={v.flags}  reviewed={v.reviewed}")
    check("is_general_guidance is True", v.is_general_guidance is True)
    check("requires_human_confirmation is True (Rule 4)", v.requires_human_confirmation is True)
    check("reviewed lists all three stages",
          set(v.reviewed) == {"wellness", "wealth", "insurance"}, str(v.reviewed))
    check("clean heuristic text → APPROVED, no flags",
          v.status is ComplianceStatus.APPROVED and not v.flags, f"{v.status.value} {v.flags}")
    check("a disclaimer contains 'konfirmasi manual diperlukan' (Rule 4)",
          any("konfirmasi manual diperlukan" in d.lower() for d in v.disclaimers))
    check("wealth rationale unchanged on clean input",
          res.wealth.rationale == wealth.rationale)

    # --- Rule 1: rewrite specific return predictions ---------------------------
    print("\nRule 1 — return predictions")
    reco = _reco(
        [_pick("Dana ini akan menghasilkan 18% per tahun, sangat menguntungkan.")],
        "Portofolio ini menargetkan imbal hasil 12% setahun.",
    )
    r = run_compliance(wealth=reco)
    txt = r.wealth.rationale + " " + r.wealth.picks[0].rationale
    check("specific % return figures removed", "18%" not in txt and "12%" not in txt, txt)
    check("hedge phrasing inserted", "tidak menjamin hasil" in txt.lower())
    check("flag return_prediction_rewritten raised", "return_prediction_rewritten" in r.flags)
    check("status APPROVED_WITH_CONDITIONS", r.verdict.status is ComplianceStatus.APPROVED_WITH_CONDITIONS)

    # --- Rule 1 false-positive guard: expense ratios must survive --------------
    print("\nRule 1 — expense-ratio guard (must NOT rewrite fees)")
    fee_text = "Dana pasar uang dengan biaya pengelolaan 1.50% per tahun."
    clean, ret_changed, _ = sanitize_text(fee_text)
    check("expense ratio 1.50% preserved", "1.50%" in clean and not ret_changed, clean)

    # --- Rule 2: rewrite guarantee language ------------------------------------
    print("\nRule 2 — guarantee language")
    reco2 = _reco(
        [_pick("Investasi ini dijamin untung dan 100% aman.")],
        "Keuntungan pasti naik, tanpa risiko sama sekali.",
    )
    r2 = run_compliance(wealth=reco2)
    t2 = (r2.wealth.rationale + " " + r2.wealth.picks[0].rationale).lower()
    check("guarantee words removed", "dijamin" not in t2 and "pasti naik" not in t2, t2)
    check("no-risk claim removed", "tanpa risiko" not in t2 and "100% aman" not in t2, t2)
    check("flag guarantee_language_rewritten raised", "guarantee_language_rewritten" in r2.flags)

    # --- Rule 3: sharia non-compliance flagged to a halal investor -------------
    print("\nRule 3 — sharia suitability for a halal investor")
    reco3 = _reco(
        [_pick("Dana konvensional dengan likuiditas tinggi.", is_sharia=False, fund_id="CONV1"),
         _pick("Dana syariah pasar uang.", is_sharia=True, fund_id="SYAR1")],
        "Pilihan dana untuk Anda.",
    )
    r3 = run_compliance(wealth=reco3, halal_investor=True)
    conv_pick = next(p for p in r3.wealth.picks if p.fund_id == "CONV1")
    syar_pick = next(p for p in r3.wealth.picks if p.fund_id == "SYAR1")
    check("non-sharia pick flagged in its rationale", "belum tersertifikasi syariah" in conv_pick.rationale)
    check("sharia pick left untouched", "PERLU TINJAUAN" not in (syar_pick.rationale or ""))
    check("flag sharia_non_compliant_fund raised", "sharia_non_compliant_fund" in r3.flags)
    check("status escalates to NEEDS_HUMAN_REVIEW", r3.verdict.status is ComplianceStatus.NEEDS_HUMAN_REVIEW)
    # Non-halal investor: same funds must NOT be flagged.
    r3b = run_compliance(wealth=reco3, halal_investor=False)
    check("non-halal investor → no sharia flag", "sharia_non_compliant_fund" not in r3b.flags)

    # --- Rule 4: always require human confirmation -----------------------------
    print("\nRule 4 — manual confirmation always on")
    for label, rr in (("clean", res), ("rewritten", r2), ("sharia", r3)):
        check(f"requires_human_confirmation True ({label})", rr.verdict.requires_human_confirmation is True)

    # --- Idempotency: re-running compliance changes nothing further ------------
    print("\nidempotency")
    once = run_compliance(wealth=reco, insurance_description="Dijamin untung 30% per tahun.")
    twice = run_compliance(
        wealth=once.wealth, insurance_description=once.insurance_description
    )
    check("wealth rationale stable on second pass",
          once.wealth.rationale == twice.wealth.rationale)
    check("insurance copy stable on second pass",
          once.insurance_description == twice.insurance_description)
    check("second pass raises no new flags", not twice.flags, str(twice.flags))

    # --- Insurance parametric language preserved -------------------------------
    print("\ninsurance parametric wording preserved")
    desc = ins.bahasa_description
    cleaned, rc, gc = sanitize_text(desc)
    check("'cair otomatis' parametric wording not mangled",
          ("cair otomatis" in cleaned) and not rc and not gc)

    print(f"\nRESULT: {ok} passed, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
