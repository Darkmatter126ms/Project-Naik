"""Hardcoded, schema-valid stub outputs for the Flask gateway.

Block 1 (Xinyue): the five agent routes return these fixtures so Hilda can build
and test the frontend tonight, before the real agents exist. Every fixture is
built by constructing the actual Pydantic model from ``api.schemas`` and dumping
it — never hand-written JSON — so a stub can never drift from the contract. If
Allen renames a field, these constructors fail loudly at import, which is
exactly the early warning we want.

The fixtures describe Sari (Naik's canonical demo persona): a 26-year-old
Jakarta ojek driver, uninsured, one ghosted Bibit fund — so her priority gap is
``risk_management`` and the recommendations lead with income protection.

When the real agents land (Phase 2), these functions are replaced by live calls;
the route signatures and output shapes stay identical.
"""

from __future__ import annotations

from api.schemas import (
    ComplianceStatus,
    ComplianceVerdict,
    FinalResponse,
    FundPick,
    FundRiskLevel,
    FundType,
    InsuranceQuote,
    NextStep,
    ParametricTrigger,
    PremiumFrequency,
    RiskProfile,
    TriggerMetric,
    WealthRecommendation,
    WellnessVector,
)

# Shared Bahasa disclaimer used across compliance + final response.
_DISCLAIMER_ID = (
    "Ini adalah panduan umum, bukan nasihat keuangan personal. "
    "Konfirmasi manusia diperlukan sebelum transaksi apa pun."
)


def stub_wellness() -> WellnessVector:
    """Sari's diagnostic: protection is the weakest dimension."""
    return WellnessVector.from_scores(
        diversification=72.0,
        liquidity=80.0,
        growth=86.0,
        risk_management=15.0,   # uninsured + gig-exposed -> lowest
        tax_efficiency=54.0,
        emergency_fund=71.0,
        behavioural_resilience=40.0,
        rationale=(
            "Prioritas utama Anda adalah proteksi penghasilan: Anda bekerja "
            "sebagai pengemudi ojek tanpa asuransi, sehingga banjir bisa "
            "menghentikan pendapatan Anda."
        ),
    )


def stub_wealth() -> WealthRecommendation:
    """A conservative, short-horizon fund pick for Sari."""
    pick = FundPick(
        fund_id="SUCORINVEST-MMF",
        fund_name="Sucorinvest Money Market Fund",
        fund_type=FundType.MONEY_MARKET,
        manager="Sucorinvest Asset Management",
        risk_level=FundRiskLevel.LOW,
        expense_ratio_pct=0.50,
        return_1y_pct=5.2,
        return_3y_annualised_pct=5.0,
        aum_idr=4_500_000_000_000,
        min_investment_idr=10_000,
        is_ojk_licensed=True,
        is_sharia=False,
        match_score=88.0,
        rationale=(
            "Cocok untuk profil konservatif dan horizon pendek: likuiditas "
            "tinggi dan risiko rendah, sambil Anda membangun proteksi."
        ),
    )
    return WealthRecommendation(
        user_id="sari",
        risk_profile_used=RiskProfile.CONSERVATIVE,
        investment_horizon_years=3.0,
        recommended_monthly_contribution_idr=300_000,
        target_amount_idr=10_000_000,
        picks=[pick],
        allocation_pct=[100.0],
        rationale=(
            "Mulai dari reksa dana pasar uang berlisensi OJK untuk menjaga dana "
            "tetap likuid selama Anda memprioritaskan proteksi penghasilan."
        ),
    )


def stub_insurance() -> InsuranceQuote:
    """A parametric income-protection micro-cover keyed to Sari's kecamatan."""
    trigger = ParametricTrigger(
        metric=TriggerMetric.RAINFALL_MM,
        threshold=100.0,
        unit="mm/24h",
        kecamatan="Penjaringan",
        observation_window_hours=24,
        data_source="BMKG",
    )
    return InsuranceQuote(
        quote_id="NAIK-INC-0001",
        user_id="sari",
        product_name="Naik Income Shield",
        trigger=trigger,
        estimated_daily_earnings_idr=200_000,
        payout_multiple=3.0,
        payout_per_event_idr=600_000,
        max_payouts_per_term=2,
        coverage_term_days=90,
        premium_idr=18_000,
        premium_frequency=PremiumFrequency.MONTHLY,
        expected_annual_loss_idr=120_000,
        loss_ratio_estimate=0.55,
    )


def stub_compliance() -> ComplianceVerdict:
    """The compliance gate, framing everything as general guidance under OJK."""
    return ComplianceVerdict(
        verdict_id="NAIK-CMP-0001",
        status=ComplianceStatus.APPROVED_WITH_CONDITIONS,
        is_general_guidance=True,
        requires_human_confirmation=True,
        reviewed=["wellness", "wealth", "insurance"],
        flags=[],
        disclaimers=[_DISCLAIMER_ID],
        rationale=(
            "Rekomendasi sesuai profil risiko dan terjangkau terhadap "
            "penghasilan. Disajikan sebagai panduan umum."
        ),
    )


def stub_final_response(request_id: str, user_id: str) -> FinalResponse:
    """The assembled end-to-end stub the orchestrator returns."""
    return FinalResponse(
        request_id=request_id,
        user_id=user_id,
        language="id",
        wellness=stub_wellness(),
        wealth=stub_wealth(),
        insurance=stub_insurance(),
        compliance=stub_compliance(),
        narrative=(
            "Prioritas pertama Anda adalah melindungi penghasilan dari risiko "
            "banjir. Kami menyarankan micro-cover proteksi penghasilan, lalu "
            "mulai menabung di reksa dana pasar uang yang likuid. Semua ini "
            "adalah panduan umum dan memerlukan konfirmasi Anda."
        ),
        next_step=NextStep.CONFIRM_BOTH,
        disclaimers=[_DISCLAIMER_ID],
    )
