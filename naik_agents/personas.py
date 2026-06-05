"""Hand-crafted test persona: Sari.

Sari is Naik's target user — a 26-year-old Shopee shopper and SPayLater holder
in Jakarta, ~Rp 6M/month, who bought one Bibit fund once and ghosted, with no
cover beyond the SPayLater credit-life policy. She rides an ojek for income and
lives in a flood-prone kecamatan. Her transcript makes the PROTECTION gap
explicit: she has a little invested, saves a bit, but is completely exposed to
an income shock if a flood stops her working.

Expected diagnostic outcome (per the build plan): ``risk_management`` should
score lowest, so ``priority_gap`` resolves to ``risk_management``.
"""

from __future__ import annotations

from datetime import datetime, timezone

try:
    from api.schemas import (
        DiagnosticInput,
        RiskProfile,
        Transaction,
        TransactionCategory,
        TransactionDirection,
    )
except ImportError:  # pragma: no cover - script/direct execution fallback
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
    from schemas import (  # type: ignore
        DiagnosticInput,
        RiskProfile,
        Transaction,
        TransactionCategory,
        TransactionDirection,
    )


def _tx(tid, day, amount, direction, category, desc=None):
    return Transaction(
        transaction_id=tid,
        timestamp=datetime(2026, 1, day, 12, 0, tzinfo=timezone.utc),
        amount_idr=amount,
        direction=direction,
        category=category,
        description=desc,
    )


# Bahasa transcript. Translation of the key lines:
#   "I once bought a mutual fund on Bibit through Shopee, but only once and then
#    I left it. I don't have any insurance. I work as an online ojek driver, so
#    if there's a flood and I can't go out, my income just stops — I have no
#    protection at all. I save a little, but I'm always tempted to checkout when
#    there are discounts."
SARI_TRANSCRIPT = (
    "Dulu saya pernah beli reksa dana di Bibit lewat Shopee, tapi cuma sekali "
    "lalu saya tinggal begitu saja. Saya tidak punya asuransi apa pun. Saya "
    "kerja sebagai driver ojek online, jadi kalau banjir dan saya tidak bisa "
    "keluar, penghasilan saya langsung berhenti — saya tidak terlindungi sama "
    "sekali. Saya menabung sedikit, tapi sering tergoda checkout kalau ada diskon."
)


def make_sari() -> DiagnosticInput:
    """Construct Sari's DiagnosticInput fixture."""
    txns = [
        _tx("sari-001", 2, 1_400_000, TransactionDirection.CREDIT, TransactionCategory.INCOME, "ojek earnings wk1"),
        _tx("sari-002", 9, 1_350_000, TransactionDirection.CREDIT, TransactionCategory.INCOME, "ojek earnings wk2"),
        _tx("sari-003", 16, 1_500_000, TransactionDirection.CREDIT, TransactionCategory.INCOME, "ojek earnings wk3"),
        _tx("sari-004", 23, 1_300_000, TransactionDirection.CREDIT, TransactionCategory.INCOME, "ojek earnings wk4"),
        _tx("sari-010", 3, 850_000, TransactionDirection.DEBIT, TransactionCategory.FOOD_BEVERAGE, "makan"),
        _tx("sari-011", 5, 600_000, TransactionDirection.DEBIT, TransactionCategory.TRANSPORT, "bensin"),
        _tx("sari-012", 7, 450_000, TransactionDirection.DEBIT, TransactionCategory.SHOPPING, "shopee checkout diskon"),
        _tx("sari-013", 12, 500_000, TransactionDirection.DEBIT, TransactionCategory.LOAN_REPAYMENT, "SPayLater"),
        _tx("sari-014", 14, 300_000, TransactionDirection.DEBIT, TransactionCategory.UTILITIES_BILLS, "listrik"),
        _tx("sari-015", 18, 380_000, TransactionDirection.DEBIT, TransactionCategory.SHOPPING, "shopee checkout"),
        _tx("sari-016", 20, 250_000, TransactionDirection.DEBIT, TransactionCategory.ENTERTAINMENT, "streaming + jajan"),
        # one small, one-off investment — the fund she bought then ghosted
        _tx("sari-017", 6, 100_000, TransactionDirection.DEBIT, TransactionCategory.INVESTMENT, "Bibit reksa dana (sekali)"),
    ]
    return DiagnosticInput(
        user_id="sari",
        age=26,
        monthly_income_idr=6_000_000,
        kecamatan="Penjaringan",  # flood-prone North Jakarta district
        city="Jakarta",
        risk_tolerance=RiskProfile.CONSERVATIVE,
        household_size=2,
        is_gig_worker=True,
        investment_horizon_years=5.0,
        existing_holdings_idr=100_000,
        financial_goals=["dana darurat", "perlindungan penghasilan"],
        voice_transcript=SARI_TRANSCRIPT,
        transactions=txns,
    )


# --------------------------------------------------------------------------- #
# Persona suite — used to validate the offline heuristic across many shapes.   #
# Each entry: (DiagnosticInput, expected_priority_gap_dimension_value).        #
# "expected" is the dimension a human would call the weakest from the evidence;#
# it documents intent and lets the suite flag drift, not enforce a single fit. #
# --------------------------------------------------------------------------- #


def _persona(
    uid, age, income, kec, risk, hh, gig, transcript, txns, *, city="Jakarta",
    horizon=5.0, goals=None,
):
    return DiagnosticInput(
        user_id=uid, age=age, monthly_income_idr=income, kecamatan=kec, city=city,
        risk_tolerance=risk, household_size=hh, is_gig_worker=gig,
        investment_horizon_years=horizon, financial_goals=goals or [],
        voice_transcript=transcript, transactions=txns,
    )


def _T(i, amt, d, c):
    return Transaction(
        transaction_id=f"p{i}",
        timestamp=datetime(2026, 1, (i % 27) + 1, 12, 0, tzinfo=timezone.utc),
        amount_idr=amt, direction=d, category=c,
    )


def _income(amt, n=4):
    """n income inflows spaced one week apart across the month.

    Spacing weekly (not on consecutive days) makes the income *cadence*
    observable, so the insurance agent's transaction-velocity path can estimate
    weekly income from the ledger rather than deferring to the self-report.
    Amounts are identical, so income variability (income_cv) — and therefore the
    diagnostic's scoring and the wealth agent's irregular-income signal — is
    unchanged; only the timestamps move.
    """
    return [
        Transaction(
            transaction_id=f"inc{i}",
            timestamp=datetime(2026, 1, 1 + i * 7, 12, 0, tzinfo=timezone.utc),
            amount_idr=amt,
            direction=TransactionDirection.CREDIT,
            category=TransactionCategory.INCOME,
        )
        for i in range(n)
    ]


def persona_suite() -> list[tuple[DiagnosticInput, str]]:
    """Return (input, expected_priority_gap) pairs spanning many weakest-dims."""
    D, C = TransactionDirection.DEBIT, TransactionDirection.CREDIT
    Cat = TransactionCategory
    suite: list[tuple[DiagnosticInput, str]] = []

    # 1. Sari — protection gap (gig, flood-exposed, uninsured)
    suite.append((make_sari(), "risk_management"))

    # 2. Budi — well-protected, diversified saver; weakest is tax_efficiency
    suite.append((_persona(
        "budi", 35, 18_000_000, "Menteng", RiskProfile.MODERATE, 3, False,
        "Saya sudah punya asuransi kesehatan dan asuransi jiwa. Saya rutin investasi "
        "tiap bulan di reksa dana saham dan obligasi, juga ada deposito. Dana darurat "
        "saya cukup untuk enam bulan ke depan.",
        _income(4_500_000) + [
            _T(1, 1_500_000, D, Cat.INVESTMENT), _T(2, 800_000, D, Cat.INSURANCE),
            _T(3, 2_000_000, D, Cat.FOOD_BEVERAGE), _T(4, 1_000_000, D, Cat.UTILITIES_BILLS),
            _T(5, 900_000, D, Cat.TRANSPORT),
        ],
    ), "tax_efficiency"))

    # 3. Citra — insured + buffer but never invested; weakest is growth
    suite.append((_persona(
        "citra", 29, 9_000_000, "Cilandak", RiskProfile.AGGRESSIVE, 1, False,
        "Saya sudah punya asuransi dari kantor dan tabungan darurat lumayan, tapi saya "
        "belum pernah investasi sama sekali. Semua uang saya cuma di tabungan biasa.",
        _income(2_250_000) + [
            _T(1, 700_000, D, Cat.INSURANCE), _T(2, 1_200_000, D, Cat.FOOD_BEVERAGE),
            _T(3, 600_000, D, Cat.TRANSPORT),
        ],
    ), "growth"))

    # 4. Dewi — spends everything, impulsive, no buffer. Genuinely ambiguous:
    #    "can't save / no emergency fund" AND "impulsive" are both stated, and an
    #    impulsive non-saver is arguably a behavioural problem at root. Accept
    #    either emergency_fund or behavioural_resilience as the gap.
    suite.append((_persona(
        "dewi", 24, 5_500_000, "Tebet", RiskProfile.MODERATE, 1, False,
        "Gaji saya selalu habis sebelum akhir bulan, sering tergoda checkout kalau ada "
        "diskon. Saya tidak bisa menabung dan tidak punya dana darurat.",
        _income(1_375_000) + [
            _T(1, 1_400_000, D, Cat.SHOPPING), _T(2, 900_000, D, Cat.ENTERTAINMENT),
            _T(3, 1_500_000, D, Cat.FOOD_BEVERAGE), _T(4, 700_000, D, Cat.SHOPPING),
        ],
    ), {"emergency_fund", "behavioural_resilience"}))

    # 5. Eko — gig driver, uninsured, flood area; weakest risk_management
    suite.append((_persona(
        "eko", 31, 7_000_000, "Kapuk", RiskProfile.CONSERVATIVE, 4, True,
        "Saya driver ojek online. Saya tidak punya asuransi apa pun dan kalau banjir "
        "saya tidak bisa kerja, penghasilan langsung berhenti. Saya merasa rentan.",
        _income(1_750_000) + [
            _T(1, 1_000_000, D, Cat.TRANSPORT), _T(2, 1_300_000, D, Cat.FOOD_BEVERAGE),
            _T(3, 500_000, D, Cat.LOAN_REPAYMENT),
        ],
    ), "risk_management"))

    # 6. Fitri — disciplined but everything in one place; weakest diversification
    suite.append((_persona(
        "fitri", 38, 14_000_000, "Kebayoran", RiskProfile.MODERATE, 2, False,
        "Saya sudah punya asuransi dan rutin menabung tiap bulan dengan disiplin. Dana "
        "darurat saya aman. Tapi semua investasi saya hanya di satu reksa dana saham.",
        _income(3_500_000) + [
            _T(1, 2_000_000, D, Cat.INVESTMENT), _T(2, 600_000, D, Cat.INSURANCE),
            _T(3, 1_500_000, D, Cat.FOOD_BEVERAGE),
        ],
    ), "diversification"))

    # 7. Gita — high earner, insured, invests, but cash-poor; weakest liquidity
    suite.append((_persona(
        "gita", 42, 25_000_000, "Pondok Indah", RiskProfile.AGGRESSIVE, 3, False,
        "Saya sudah punya asuransi lengkap dan portofolio investasi yang beragam: saham, "
        "obligasi, properti. Tapi hampir semua uang saya terkunci di investasi, kas saya "
        "sangat sedikit dan susah dicairkan.",
        _income(6_250_000) + [
            _T(1, 5_000_000, D, Cat.INVESTMENT), _T(2, 1_000_000, D, Cat.INSURANCE),
            _T(3, 2_000_000, D, Cat.FOOD_BEVERAGE), _T(4, 1_500_000, D, Cat.SHOPPING),
            _T(5, 800_000, D, Cat.HEALTH),
        ],
    ), "liquidity"))

    # 8. Hadi — balanced, healthy across the board (sanity: no extreme gap expected)
    suite.append((_persona(
        "hadi", 33, 12_000_000, "Cibubur", RiskProfile.MODERATE, 3, False,
        "Saya sudah punya asuransi kesehatan dan jiwa, dana darurat enam bulan, investasi "
        "rutin di beberapa reksa dana yang beragam, dan saya disiplin menabung tiap bulan.",
        _income(3_000_000) + [
            _T(1, 1_000_000, D, Cat.INVESTMENT), _T(2, 500_000, D, Cat.INSURANCE),
            _T(3, 1_200_000, D, Cat.FOOD_BEVERAGE), _T(4, 600_000, D, Cat.UTILITIES_BILLS),
            _T(5, 400_000, D, Cat.TRANSPORT), _T(6, 300_000, D, Cat.HEALTH),
        ],
    ), None))  # None => no single dominant gap asserted

    # 9. Negation test: says "tidak punya asuransi" — must read as WEAK protection
    suite.append((_persona(
        "neg_uninsured", 27, 6_500_000, "Duren Sawit", RiskProfile.CONSERVATIVE, 2, False,
        "Saya rutin menabung dan punya dana darurat, tapi saya tidak punya asuransi sama sekali.",
        _income(1_625_000) + [_T(1, 800_000, D, Cat.FOOD_BEVERAGE)],
    ), "risk_management"))

    # 10. Positive test: says "sudah punya asuransi" — must NOT flag protection
    suite.append((_persona(
        "pos_insured", 30, 8_000_000, "Bekasi", RiskProfile.MODERATE, 2, False,
        "Saya sudah punya asuransi kesehatan dan jiwa yang lengkap, tapi saya belum pernah "
        "investasi dan tidak tahu cara mulai.",
        _income(2_000_000) + [_T(1, 700_000, D, Cat.INSURANCE), _T(2, 900_000, D, Cat.FOOD_BEVERAGE)],
    ), "growth"))

    return suite
