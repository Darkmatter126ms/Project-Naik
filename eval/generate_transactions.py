"""eval/generate_transactions.py — Sher Min Block 2.

Generates 90 days of synthetic Shopee/GoPay transaction history per eval
persona and optionally persists to Postgres.

Behavioural rules
-----------------
Gig worker
    Four weekly income credits (variable ±15%), not a single monthly deposit —
    this makes the income-velocity path in insurance.py trigger correctly.
    Elevated GoFood (3–5 orders/week), heavy fuel spend, one motorbike-part
    purchase per month (shopping category, explicit description).

Halal constrained
    All merchant names drawn from a halal-safe list. Alcohol-adjacent SKUs
    ("Circle K", beer descriptions, etc.) are excluded. Food and entertainment
    merchants are restricted to OJK/MUI-certified halal operators.

Lebaran 2026 (Idul Fitri 1447H, est. 20 March 2026)
    T−14 → T−8 : moderate clothing + grocery uplift (early baju lebaran shopping)
    T−7  → T−1 : peak spike — shopping ×3.2, groceries ×2.5, food ×2.0
                 (kue lebaran, hampers, last-minute baju baru)
    T    → T+2 : THR transfer spike, most spending suppressed (family time)
    T+3  → T+10: gradual normalisation (-3 %/day back to baseline)

Spending amounts
    Scale linearly with monthly_income_idr relative to a 5 M IDR baseline.
    Utilities (PLN, PDAM, internet) are near-fixed monthly costs and do NOT
    scale with income — they are anchored to realistic Indonesian tariff bands.

Postgres persistence
    Personas are upserted by user_id (data JSONB, no duplicate rows).
    Transactions are delete-then-reinsert per persona so re-runs are
    idempotent without unique-constraint complexity.

Usage
-----
    # dry-run: print stats only, no DB write
    python eval/generate_transactions.py --dry-run

    # full run for canonical 50 personas (needs DATABASE_URL)
    python eval/generate_transactions.py

    # custom seed / count
    python eval/generate_transactions.py --n 5 --seed 42 --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.schemas import (  # noqa: E402
    DiagnosticInput,
    Transaction,
    TransactionCategory,
    TransactionDirection,
)
from eval.generate_personas import PersonaMeta, generate_personas  # noqa: E402

# ── Evaluation window ─────────────────────────────────────────────────────── #
# Fixed 90-day window: 5 Mar 2026 → 2 Jun 2026.
# Lebaran (20 Mar) falls at day 15 — captures the peak pre-Lebaran shopping
# corridor and 70+ days of post-holiday normalcy.
WINDOW_END = date(2026, 6, 2)
WINDOW_DAYS = 90
WINDOW_START = WINDOW_END - timedelta(days=WINDOW_DAYS - 1)  # 2026-03-05

# Idul Fitri 1447H: ~20 March 2026 (Indonesian moon-sighting estimate)
LEBARAN_2026 = date(2026, 3, 20)

SEED = 2026

# ── Merchant catalogues ───────────────────────────────────────────────────── #
# Halal-safe lists (usable for ALL personas, including halal-constrained ones).
# Non-halal additions are appended only for non-halal personas at ~10 % rate.

_FOOD_HALAL = [
    # GoFood weighted 3× — dominant for gig workers
    "GoFood", "GoFood", "GoFood",
    "GrabFood", "GrabFood",
    "ShopeeFood",
    "Warung Padang Sederhana",
    "Warung Makan Bu Tini",
    "Bakmi GM",
    "Es Teler 77",
    "McDonald's",     # halal-certified in Indonesia
    "KFC",            # halal-certified in Indonesia
    "Pizza Hut",      # halal-certified in Indonesia
    "Bebek Goreng Pak Ndut",
    "Nasi Goreng Pak Kumis",
]
_FOOD_NON_HALAL_ADD = [
    "Circle K",    # sells beer / alcohol
    "Lawson",      # some branches stock alcohol
    "FamilyMart",  # selected branches
]
_FOOD_DESCRIPTIONS_HALAL = [
    "Nasi Padang + es teh", "Ayam geprek level 3", "Mie Ayam + bakso",
    "Nasi Goreng Spesial", "Indomie rebus double", "Paket hemat KFC",
    "McD 2 chicken + fries", "Bakmi Jawa goreng", "Es Teler campur",
    "Bebek goreng + lalapan", "Ayam bakar + nasi", "Siomay + batagor",
    "GoFood order malam", "GrabFood makan siang", "ShopeeFood promo",
]
_FOOD_DESCRIPTIONS_NON_HALAL_ADD = [
    "Circle K snacks + minuman", "Bir Bintang 2 kaleng",
    "Lawson onigiri + minuman", "Minuman kaleng import",
]

_GROCERY_MERCHANTS = [
    "Alfamart", "Alfamart", "Alfamart",   # most ubiquitous
    "Indomaret", "Indomaret",
    "Hypermart",
    "Giant Supermarket",
    "Transmart Carrefour",
]
_GROCERY_DESCRIPTIONS = [
    "Belanja harian Alfamart", "Sembako mingguan", "Bahan masak dapur",
    "Sabun + shampo + odol", "Telur, beras, minyak goreng",
    "Snack + minuman + susu", "Deterjen + pembersih lantai",
]

_TRANSPORT_MERCHANTS = [
    "Pertamina MyPertamina", "Pertamina MyPertamina",  # dominant for ojek
    "Shell", "Vivo Energy",
    "Gojek",  "Grab",
    "TransJakarta", "KRL Commuter Line", "MRT Jakarta",
]
_TRANSPORT_DESCRIPTIONS = [
    "Isi bensin Pertalite motor", "Full tank Pertamax motor",
    "Bensin Honda Beat", "Isi BBM motor Yamaha",
    "Gojek ke kantor", "Grab ke stasiun",
    "Tiket TransJakarta", "Bayar KRL pulang kerja",
]

_SHOPPING_MERCHANTS = [
    "Shopee", "Shopee", "Shopee",
    "Tokopedia", "Tokopedia",
    "Lazada", "Blibli",
    "Miniso", "ACE Hardware", "IKEA",
]
_SHOPPING_LEBARAN_MERCHANTS = [
    "Matahari Department Store", "Ramayana",
    "Batik Keris", "Centro",
    "Shopee (Lebaran)", "Tokopedia (Baju Lebaran)",
    "Pasar Tanah Abang Online",
]
_SHOPPING_LEBARAN_DESCRIPTIONS = [
    "Baju koko lebaran", "Gamis lebaran ibu",
    "Kemeja batik ayah", "Baju anak-anak lebaran",
    "Kue nastar + kastengel lebaran", "Parcel sembako lebaran",
    "Hamper lebaran teman kantor", "Baju baru lebaran",
    "Mukena baru lebaran", "Peci + sarung lebaran",
]

_MOTORBIKE_MERCHANTS = [
    "Shopee Otomotif",
    "Tokopedia Motor",
    "Bengkel Motor Pak Hadi",
    "Toko Onderdil Motor Jaya",
    "Astra Motor Parts",
]
_MOTORBIKE_DESCRIPTIONS = [
    "Rantai dan kampas rem motor",
    "Oli mesin 4T + filter udara",
    "Ban dalam motor Honda Beat",
    "Busi Denso + kabel kopling",
    "Kampas rem cakram depan",
    "Lampu LED motor + grip stang",
    "Sparepart motor rutin bulanan",
    "Aki motor + kabel aki",
]

_UTILITY_SCHEDULE = [
    # (merchant, category_value, description, monthly_amount_idr, amount_spread)
    ("PLN Mobile",           "utilities_bills", "Tagihan listrik bulan ini",        250_000, 0.30),
    ("PDAM Jaya",            "utilities_bills", "Tagihan air bersih PDAM",           130_000, 0.15),
    ("Indihome Telkom",      "utilities_bills", "Langganan internet Indihome",       250_000, 0.10),
    ("Telkomsel MyTelkomsel","utilities_bills", "Paket data bulanan Telkomsel",       80_000, 0.05),
]

_ENTERTAINMENT_HALAL = [
    ("Cinema 21",    "Tiket bioskop 2 orang"),
    ("CGV Cinemas",  "Tiket film CGV weekend"),
    ("Netflix",      "Langganan Netflix bulan ini"),
    ("Spotify",      "Spotify Premium bulan ini"),
    ("Voucher Game", "Top-up Mobile Legends 500 diamond"),
    ("Voucher Game", "Top-up PUBG Mobile UC"),
    ("Tiket.com",    "Tiket acara hiburan"),
]
_ENTERTAINMENT_NON_HALAL_ADD = [
    ("Circle K",     "Minuman alkohol + snack"),
    ("Beer Garden",  "Makan malam + minuman"),
]

_LOAN_MERCHANTS = [
    ("SPayLater",   "Cicilan SPayLater bulan ini"),
    ("GoPay Later", "Cicilan GoPay Later bulan ini"),
    ("Kredivo",     "Angsuran Kredivo"),
    ("Akulaku",     "Cicilan Akulaku bulan ini"),
    ("Bank BCA",    "Cicilan kartu kredit BCA"),
]

_INCOME_GIG_DESCRIPTIONS = [
    "Penghasilan driver ojek online - Gojek Mitra",
    "Bayaran ojek mingguan Grab Driver",
    "Hasil narik ojek minggu ini",
    "Transfer penghasilan ojek online",
    "Gojek weekly earning disbursement",
]
_INCOME_SALARY_DESCRIPTION = "Gaji bulanan transfer bank"


# ── Helper dataclass ──────────────────────────────────────────────────────── #

@dataclass
class _Budget:
    """Monthly spending budget per category, derived from persona income."""
    food_beverage: int      # IDR/month
    groceries: int
    transport: int
    shopping: int
    entertainment: int
    # Utilities are near-fixed costs — not income-proportional
    pln: int           # electricity
    pdam: int          # water
    internet: int
    phone: int
    # Gig-worker specifics
    motorbike_part: int   # per purchase (0 if not gig_worker)


def _build_budget(persona: DiagnosticInput) -> _Budget:
    inc = persona.monthly_income_idr
    is_gig = persona.is_gig_worker

    # Spending fractions (empirically calibrated to Indonesian gig economy)
    # Gig workers: more food delivery (time-poor), more fuel, less entertainment
    food_frac = 0.30 if is_gig else 0.22
    trans_frac = 0.22 if is_gig else 0.10

    # Utilities: banded by income (kWh/power tier correlates with income)
    if inc < 3_000_000:
        pln, pdam, internet, phone = 160_000, 80_000, 0, 55_000
    elif inc < 6_000_000:
        pln, pdam, internet, phone = 230_000, 110_000, 200_000, 75_000
    else:
        pln, pdam, internet, phone = 320_000, 140_000, 280_000, 90_000

    return _Budget(
        food_beverage=round(inc * food_frac),
        groceries=round(inc * 0.14),
        transport=round(inc * trans_frac),
        shopping=round(inc * 0.15),
        entertainment=round(inc * (0.03 if is_gig else 0.06)),
        pln=pln, pdam=pdam, internet=internet, phone=phone,
        motorbike_part=round(inc * 0.04) if is_gig else 0,
    )


# ── Core utilities ────────────────────────────────────────────────────────── #

def _build_rng(user_id: str, base_seed: int) -> np.random.Generator:
    """Deterministic per-persona RNG so re-runs produce identical transactions."""
    h = int(hashlib.sha256(user_id.encode()).hexdigest()[:16], 16)
    # XOR-fold hash into seed space without overflow
    combined = (base_seed * 6364136223846793005 ^ h) & 0xFFFFFFFFFFFFFFFF
    return np.random.default_rng(combined)


def _is_halal(persona: DiagnosticInput) -> bool:
    """Detect halal constraint from structured goals and transcript keywords."""
    goals_text = " ".join(persona.financial_goals or []).lower()
    transcript = (persona.voice_transcript or "").lower()
    keywords = ("halal_investing", "halal", "syariah", "sharia", "islami")
    return any(kw in goals_text or kw in transcript for kw in keywords)


def _draw_idr(
    rng: np.random.Generator,
    base_min: int,
    base_max: int,
    scale: float = 1.0,
) -> int:
    """Draw a rupiah amount, scaled by income, rounded to nearest 1 000 IDR."""
    raw = rng.uniform(base_min * scale, base_max * scale)
    return max(1_000, round(raw / 1_000) * 1_000)


def _income_scale(income: int) -> float:
    """Scale factor relative to 5 M IDR baseline. Capped at 3× to avoid outliers."""
    return min(3.0, income / 5_000_000)


def _ts(d: date, rng: np.random.Generator) -> datetime:
    """Random time within a day (07:00–22:00 WIB → UTC+7)."""
    hour = int(rng.integers(7, 22))
    minute = int(rng.integers(0, 60))
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)


def _make_tx(
    tid: str,
    d: date,
    amount: int,
    direction: TransactionDirection,
    category: TransactionCategory,
    merchant: str | None = None,
    description: str | None = None,
    rng: np.random.Generator | None = None,
) -> Transaction:
    ts = _ts(d, rng) if rng is not None else datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc)
    return Transaction(
        transaction_id=tid,
        timestamp=ts,
        amount_idr=amount,
        direction=direction,
        category=category,
        merchant=merchant,
        description=description,
    )


# ── Lebaran multiplier ────────────────────────────────────────────────────── #

def _lebaran_mult(d: date, cat: TransactionCategory, is_halal: bool) -> float:
    """Return a spending multiplier for Lebaran season.

    Halal personas get the full spike (more religiously engaged in the holiday).
    Non-halal personas still experience some Lebaran effect (Indonesia is 87 %
    Muslim; THR, clothing gifts, and holiday food affect everyone).
    """
    delta = (d - LEBARAN_2026).days
    halal_boost = 1.0 if is_halal else 0.65

    if -14 <= delta < -7:   # Phase 1: early preparation
        mults = {
            TransactionCategory.SHOPPING:      1.8,
            TransactionCategory.GROCERIES:     1.5,
            TransactionCategory.FOOD_BEVERAGE: 1.2,
        }
    elif -7 <= delta < 0:   # Phase 2: peak Lebaran shopping
        mults = {
            TransactionCategory.SHOPPING:      3.2,   # baju lebaran!
            TransactionCategory.GROCERIES:     2.5,   # kue + bahan masak
            TransactionCategory.FOOD_BEVERAGE: 2.0,   # kue lebaran beli jadi
            TransactionCategory.TRANSFER:      2.0,   # kirim uang ke keluarga
        }
    elif 0 <= delta <= 2:   # Lebaran day(s): family time
        mults = {
            TransactionCategory.TRANSFER:      4.0,   # THR / kirim uang
            TransactionCategory.FOOD_BEVERAGE: 0.2,   # makan di rumah
            TransactionCategory.SHOPPING:      0.2,
            TransactionCategory.TRANSPORT:     0.5,   # mudik
        }
        return mults.get(cat, 0.3)  # default: most spending suppressed
    elif 3 <= delta <= 10:  # gradual normalisation
        recovery = 1.0 - 0.03 * (delta - 3)
        return max(0.7, recovery)
    else:
        return 1.0

    base_mult = mults.get(cat, 1.0)
    if base_mult != 1.0:
        return 1.0 + (base_mult - 1.0) * halal_boost
    return 1.0


# ── Income schedule ───────────────────────────────────────────────────────── #

def _gig_income_schedule(
    persona: DiagnosticInput,
    start: date,
    end: date,
    rng: np.random.Generator,
) -> list[tuple[date, int]]:
    """Four weekly income credits per month for gig workers.

    Payments arrive on a consistent weekday (Mon–Wed) with ±15 % variability
    in amount — matching ojek platform weekly payout behaviour.
    Min span across all credits exceeds 14 days (MIN_INCOME_SPAN_DAYS) so the
    insurance agent's transaction-velocity path activates.
    """
    weekly_base = round(persona.monthly_income_idr / (52 / 12))  # ≈ monthly/4.333
    # Consistent payday: Mon (0) to Wed (2) offset per persona
    pay_offset = int(rng.integers(0, 3))  # 0=Mon, 1=Tue, 2=Wed

    schedule: list[tuple[date, int]] = []
    current = start
    while current <= end:
        # Align to the persona's payday weekday
        days_ahead = (pay_offset - current.weekday()) % 7
        pay_date = current + timedelta(days=days_ahead)
        if pay_date > end:
            break
        # Variable amount: lognormal around weekly base, σ=15 %
        amount = round(
            rng.lognormal(mean=0.0, sigma=0.15) * weekly_base / 1_000
        ) * 1_000
        amount = max(500_000, amount)  # floor
        schedule.append((pay_date, amount))
        current = pay_date + timedelta(days=7)  # advance exactly one week

    return schedule


def _salary_schedule(
    persona: DiagnosticInput,
    start: date,
    end: date,
    rng: np.random.Generator,
) -> list[tuple[date, int]]:
    """One monthly salary credit per month, on a fixed day 25–28."""
    payday = int(rng.integers(25, 29))  # consistent across months
    schedule: list[tuple[date, int]] = []

    # Walk month by month
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        import calendar
        last_day = calendar.monthrange(y, m)[1]
        day = min(payday, last_day)
        pay_date = date(y, m, day)
        if start <= pay_date <= end:
            # Net pay ≈ gross − small tax/deduction (2 % noise)
            amount = round(persona.monthly_income_idr * rng.normal(0.98, 0.01) / 1_000) * 1_000
            amount = max(persona.monthly_income_idr - 500_000, amount)
            schedule.append((pay_date, amount))
        m += 1
        if m > 12:
            m = 1; y += 1

    return schedule


# ── Motorbike parts schedule (gig workers) ────────────────────────────────── #

def _motorbike_schedule(
    persona: DiagnosticInput,
    budget: _Budget,
    start: date,
    end: date,
    rng: np.random.Generator,
) -> list[tuple[date, int, str, str]]:
    """One motorbike part purchase per month for gig workers.

    Returns (date, amount, merchant, description) tuples.
    Amounts: 75 k–350 k IDR, independent of income (spare parts have fixed prices).
    """
    if not persona.is_gig_worker:
        return []

    schedule: list[tuple[date, int, str, str]] = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        import calendar
        last_day = calendar.monthrange(y, m)[1]
        # Random day 5–20 of the month (not at month-end when cash is tight)
        day = int(rng.integers(5, min(21, last_day + 1)))
        purchase_date = date(y, m, day)
        if start <= purchase_date <= end:
            amount = _draw_idr(rng, 75_000, 350_000, scale=1.0)  # price-fixed
            merchant = str(rng.choice(_MOTORBIKE_MERCHANTS))
            description = str(rng.choice(_MOTORBIKE_DESCRIPTIONS))
            schedule.append((purchase_date, amount, merchant, description))
        m += 1
        if m > 12:
            m = 1; y += 1

    return schedule


# ── Utility bills schedule ────────────────────────────────────────────────── #

def _utility_schedule(
    persona: DiagnosticInput,
    budget: _Budget,
    start: date,
    end: date,
    rng: np.random.Generator,
) -> list[tuple[date, int, str, str]]:
    """Monthly utility bills: PLN, PDAM, internet, phone."""
    scheduled: list[tuple[date, int, str, str]] = []
    amounts = [budget.pln, budget.pdam, budget.internet, budget.phone]

    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        import calendar
        last_day = calendar.monthrange(y, m)[1]
        for (merchant, _cat_val, description, base_amt, spread), budget_amt in zip(
            _UTILITY_SCHEDULE, amounts
        ):
            if budget_amt == 0:
                continue
            # Stagger bills across days 5–15 of each month
            base_day = 5 + _UTILITY_SCHEDULE.index((merchant, _cat_val, description, base_amt, spread)) * 2
            bill_day = min(base_day + int(rng.integers(0, 3)), last_day)
            bill_date = date(y, m, bill_day)
            if start <= bill_date <= end:
                # Small noise on utility bills (seasonal/usage variation)
                amount = round(budget_amt * rng.normal(1.0, spread) / 1_000) * 1_000
                amount = max(10_000, amount)
                scheduled.append((bill_date, amount, merchant, description))

        m += 1
        if m > 12:
            m = 1; y += 1

    return scheduled


# ── Loan repayment schedule ───────────────────────────────────────────────── #

def _loan_schedule(
    persona: DiagnosticInput,
    rng: np.random.Generator,
    start: date,
    end: date,
) -> list[tuple[date, int, str, str]]:
    """Monthly SPayLater / credit repayments for ~55 % of personas.

    Probability increases at lower income levels (lower-income users rely more
    on BNPL to smooth purchases).
    """
    inc = persona.monthly_income_idr
    # P(has loan): 70 % for <3M, 55 % for 3–6M, 30 % for >6M
    if inc < 3_000_000:
        prob = 0.70
    elif inc < 6_000_000:
        prob = 0.55
    else:
        prob = 0.30

    # Deterministic per-persona: use a stable draw from a seeded uniform
    if rng.uniform() > prob:
        return []

    merchant, description = _LOAN_MERCHANTS[int(rng.integers(0, len(_LOAN_MERCHANTS)))]
    # Monthly installment: 5–12 % of income
    monthly_payment = round(inc * rng.uniform(0.05, 0.12) / 1_000) * 1_000
    payday = int(rng.integers(10, 25))  # consistent repayment date

    schedule: list[tuple[date, int, str, str]] = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        import calendar
        day = min(payday, calendar.monthrange(y, m)[1])
        repay_date = date(y, m, day)
        if start <= repay_date <= end:
            # Slight amount variation (partial payments, fees)
            amount = round(monthly_payment * rng.normal(1.0, 0.05) / 1_000) * 1_000
            amount = max(50_000, amount)
            schedule.append((repay_date, amount, merchant, description))
        m += 1
        if m > 12:
            m = 1; y += 1

    return schedule


# ── Daily spending ────────────────────────────────────────────────────────── #

def _daily_food_transactions(
    persona: DiagnosticInput,
    budget: _Budget,
    is_halal: bool,
    rng: np.random.Generator,
    d: date,
) -> list[tuple[int, str | None, str | None]]:
    """(amount, merchant, description) tuples for food_beverage on one day."""
    mult = _lebaran_mult(d, TransactionCategory.FOOD_BEVERAGE, is_halal)
    scale = _income_scale(persona.monthly_income_idr)

    # Expected food orders per day
    if persona.is_gig_worker:
        lam = 0.55 * mult          # ~3.85/week for gig
    else:
        lam = 0.22 * mult          # ~1.54/week for salaried

    count = int(rng.poisson(lam))
    if count == 0:
        return []

    merchants = _FOOD_HALAL.copy()
    descriptions = _FOOD_DESCRIPTIONS_HALAL.copy()
    if not is_halal and rng.uniform() < 0.10:
        merchants += _FOOD_NON_HALAL_ADD
        descriptions += _FOOD_DESCRIPTIONS_NON_HALAL_ADD

    results = []
    for _ in range(count):
        merchant = str(rng.choice(merchants))
        desc = str(rng.choice(descriptions))
        amount = _draw_idr(rng, 25_000, 58_000, scale=scale)
        results.append((amount, merchant, desc))
    return results


def _daily_grocery_transactions(
    persona: DiagnosticInput,
    budget: _Budget,
    rng: np.random.Generator,
    d: date,
    is_halal: bool,
) -> list[tuple[int, str | None, str | None]]:
    mult = _lebaran_mult(d, TransactionCategory.GROCERIES, is_halal)
    scale = _income_scale(persona.monthly_income_idr)
    lam = 0.35 * mult   # ~2.45 trips/week
    count = int(rng.poisson(lam))
    results = []
    for _ in range(count):
        merchant = str(rng.choice(_GROCERY_MERCHANTS))
        desc = str(rng.choice(_GROCERY_DESCRIPTIONS))
        # Household size scales grocery spend
        hh_scale = 1.0 + max(0, persona.household_size - 1) * 0.15
        amount = _draw_idr(rng, 50_000, 220_000, scale=scale * hh_scale)
        results.append((amount, merchant, desc))
    return results


def _daily_transport_transactions(
    persona: DiagnosticInput,
    budget: _Budget,
    rng: np.random.Generator,
    d: date,
    is_halal: bool,
) -> list[tuple[int, str | None, str | None]]:
    mult = _lebaran_mult(d, TransactionCategory.TRANSPORT, is_halal)
    scale = _income_scale(persona.monthly_income_idr)

    # Gig workers fill up fuel 2–3× per week; salaried only 1–2× per month
    lam = (0.35 if persona.is_gig_worker else 0.08) * mult
    count = int(rng.poisson(lam))
    results = []
    for _ in range(count):
        merchant = str(rng.choice(_TRANSPORT_MERCHANTS))
        desc = str(rng.choice(_TRANSPORT_DESCRIPTIONS))
        if persona.is_gig_worker:
            amount = _draw_idr(rng, 40_000, 80_000, scale=1.0)  # fuel: price-fixed
        else:
            amount = _draw_idr(rng, 15_000, 60_000, scale=scale)
        results.append((amount, merchant, desc))
    return results


def _daily_shopping_transactions(
    persona: DiagnosticInput,
    budget: _Budget,
    is_halal: bool,
    rng: np.random.Generator,
    d: date,
) -> list[tuple[int, str | None, str | None]]:
    mult = _lebaran_mult(d, TransactionCategory.SHOPPING, is_halal)
    scale = _income_scale(persona.monthly_income_idr)
    lam = 0.28 * mult  # ~2/week baseline
    count = int(rng.poisson(lam))
    results = []

    # In Lebaran peak, draw from special Lebaran merchant list
    is_lebaran_peak = -7 <= (d - LEBARAN_2026).days < 2
    for _ in range(count):
        if is_lebaran_peak and rng.uniform() < 0.60:
            merchant = str(rng.choice(_SHOPPING_LEBARAN_MERCHANTS))
            desc = str(rng.choice(_SHOPPING_LEBARAN_DESCRIPTIONS))
            amount = _draw_idr(rng, 120_000, 500_000, scale=scale)
        else:
            merchant = str(rng.choice(_SHOPPING_MERCHANTS))
            desc = f"Shopee order #{rng.integers(10000, 99999)}" if "Shopee" in merchant else "Belanja online"
            amount = _draw_idr(rng, 35_000, 350_000, scale=scale)
        results.append((amount, merchant, desc))
    return results


def _daily_entertainment_transactions(
    persona: DiagnosticInput,
    is_halal: bool,
    rng: np.random.Generator,
    d: date,
) -> list[tuple[int, str | None, str | None]]:
    scale = _income_scale(persona.monthly_income_idr)
    # Gig workers have less disposable income / time for entertainment
    lam = 0.04 if persona.is_gig_worker else 0.08
    count = int(rng.poisson(lam))
    results = []
    pool = _ENTERTAINMENT_HALAL.copy()
    if not is_halal and rng.uniform() < 0.15:
        pool += _ENTERTAINMENT_NON_HALAL_ADD
    for _ in range(count):
        merchant, desc = pool[int(rng.integers(0, len(pool)))]
        amount = _draw_idr(rng, 45_000, 120_000, scale=scale)
        results.append((amount, str(merchant), str(desc)))
    return results


def _daily_lebaran_transfer(
    persona: DiagnosticInput,
    rng: np.random.Generator,
    d: date,
    is_halal: bool,
) -> list[tuple[int, str | None, str | None]]:
    """THR family transfers on Lebaran days."""
    delta = (d - LEBARAN_2026).days
    if not (0 <= delta <= 2):
        return []

    scale = _income_scale(persona.monthly_income_idr)
    # THR: typically 1× monthly income split across family + colleagues
    if rng.uniform() < 0.70:   # most people send THR
        amount = _draw_idr(rng, 200_000, 1_500_000, scale=scale)
        desc = rng.choice([
            "THR lebaran ke keluarga kampung",
            "Kirim uang lebaran orang tua",
            "Transfer Lebaran ke saudara",
        ])
        return [(amount, "Transfer Bank", str(desc))]
    return []


# ── Main generator ────────────────────────────────────────────────────────── #

def generate_transactions(
    persona: DiagnosticInput,
    meta: Optional[PersonaMeta] = None,
    *,
    days: int = 90,
    end_date: date = WINDOW_END,
    base_seed: int = SEED,
) -> list[Transaction]:
    """Generate `days` of synthetic Shopee/GoPay transactions for *persona*.

    Parameters
    ----------
    persona :
        Validated DiagnosticInput (must have user_id, monthly_income_idr,
        is_gig_worker, financial_goals).
    meta :
        Optional PersonaMeta sidecar with explicit halal_investing flag.
        If None, halal is inferred from persona.financial_goals / transcript.
    days :
        Window length in days (default 90 ≈ 3 months).
    end_date :
        Last day of the window (default 2 June 2026, fixed for reproducibility).
    base_seed :
        Base RNG seed; per-persona seed = hash(user_id) ⊕ base_seed.

    Returns
    -------
    list[Transaction]
        Validated Transaction objects sorted by timestamp, ready to attach to
        the persona before calling /orchestrate.
    """
    rng = _build_rng(persona.user_id, base_seed)
    start = end_date - timedelta(days=days - 1)
    is_halal = (meta.halal_investing if meta is not None else None) or _is_halal(persona)
    budget = _build_budget(persona)

    txns: list[Transaction] = []
    tx_counter = 0

    def new_tid() -> str:
        nonlocal tx_counter
        tx_counter += 1
        return f"{persona.user_id}-{tx_counter:05d}"

    # ── 1. Income credits ────────────────────────────────────────────────── #
    if persona.is_gig_worker:
        income_schedule = _gig_income_schedule(persona, start, end_date, rng)
        income_descriptions = _INCOME_GIG_DESCRIPTIONS
    else:
        income_schedule = _salary_schedule(persona, start, end_date, rng)
        income_descriptions = [_INCOME_SALARY_DESCRIPTION]

    for inc_date, amount in income_schedule:
        desc = str(rng.choice(income_descriptions))
        txns.append(_make_tx(
            new_tid(), inc_date, amount,
            TransactionDirection.CREDIT, TransactionCategory.INCOME,
            merchant="Gojek Mitra" if persona.is_gig_worker else "Transfer Bank",
            description=desc, rng=rng,
        ))

    # ── 2. Utility bills (scheduled) ─────────────────────────────────────── #
    for bill_date, amount, merchant, description in _utility_schedule(
        persona, budget, start, end_date, rng
    ):
        txns.append(_make_tx(
            new_tid(), bill_date, amount,
            TransactionDirection.DEBIT, TransactionCategory.UTILITIES_BILLS,
            merchant=merchant, description=description, rng=rng,
        ))

    # ── 3. Loan repayments (probabilistic scheduled) ─────────────────────── #
    for repay_date, amount, merchant, description in _loan_schedule(
        persona, rng, start, end_date
    ):
        txns.append(_make_tx(
            new_tid(), repay_date, amount,
            TransactionDirection.DEBIT, TransactionCategory.LOAN_REPAYMENT,
            merchant=merchant, description=description, rng=rng,
        ))

    # ── 4. Motorbike parts (gig workers, monthly) ─────────────────────────── #
    for part_date, amount, merchant, description in _motorbike_schedule(
        persona, budget, start, end_date, rng
    ):
        txns.append(_make_tx(
            new_tid(), part_date, amount,
            TransactionDirection.DEBIT, TransactionCategory.SHOPPING,
            merchant=merchant, description=description, rng=rng,
        ))

    # ── 5. Daily variable spending ────────────────────────────────────────── #
    for day_offset in range(days):
        d = start + timedelta(days=day_offset)

        # food_beverage
        for amt, merch, desc in _daily_food_transactions(persona, budget, is_halal, rng, d):
            txns.append(_make_tx(
                new_tid(), d, amt,
                TransactionDirection.DEBIT, TransactionCategory.FOOD_BEVERAGE,
                merchant=merch, description=desc, rng=rng,
            ))

        # groceries
        for amt, merch, desc in _daily_grocery_transactions(persona, budget, rng, d, is_halal):
            txns.append(_make_tx(
                new_tid(), d, amt,
                TransactionDirection.DEBIT, TransactionCategory.GROCERIES,
                merchant=merch, description=desc, rng=rng,
            ))

        # transport
        for amt, merch, desc in _daily_transport_transactions(persona, budget, rng, d, is_halal):
            txns.append(_make_tx(
                new_tid(), d, amt,
                TransactionDirection.DEBIT, TransactionCategory.TRANSPORT,
                merchant=merch, description=desc, rng=rng,
            ))

        # shopping (includes Lebaran spike)
        for amt, merch, desc in _daily_shopping_transactions(persona, budget, is_halal, rng, d):
            txns.append(_make_tx(
                new_tid(), d, amt,
                TransactionDirection.DEBIT, TransactionCategory.SHOPPING,
                merchant=merch, description=desc, rng=rng,
            ))

        # entertainment
        for amt, merch, desc in _daily_entertainment_transactions(persona, is_halal, rng, d):
            txns.append(_make_tx(
                new_tid(), d, amt,
                TransactionDirection.DEBIT, TransactionCategory.ENTERTAINMENT,
                merchant=merch, description=desc, rng=rng,
            ))

        # Lebaran THR transfers
        for amt, merch, desc in _daily_lebaran_transfer(persona, rng, d, is_halal):
            txns.append(_make_tx(
                new_tid(), d, amt,
                TransactionDirection.DEBIT, TransactionCategory.TRANSFER,
                merchant=merch, description=desc, rng=rng,
            ))

    return sorted(txns, key=lambda t: t.timestamp)


# ── Postgres persistence ──────────────────────────────────────────────────── #

def _json_dumps(obj) -> str:
    """Compact JSON with datetime serialisation."""
    return json.dumps(obj, ensure_ascii=False, default=str)


def get_or_create_persona_id(engine, persona: DiagnosticInput, meta: PersonaMeta) -> str | None:
    """Upsert persona to Postgres; return the row UUID string.

    Matches on user_id inside the JSONB data column.  If the persona already
    exists the existing UUID is returned without modification (idempotent).
    """
    if engine is None:
        return None

    from sqlalchemy import text as sqlt

    data_json = _json_dumps({
        **persona.model_dump(mode="json"),
        "_meta": {
            "halal_investing": meta.halal_investing,
            "current_funds": meta.current_funds,
            "current_insurance": meta.current_insurance,
            "flood_risk_score": meta.flood_risk_score,
        },
    })

    with engine.begin() as conn:
        # Check for existing row by user_id inside JSONB
        row = conn.execute(
            sqlt("SELECT id FROM personas WHERE data->>'user_id' = :uid LIMIT 1"),
            {"uid": persona.user_id},
        ).fetchone()

        if row:
            return str(row[0])

        result = conn.execute(
            sqlt("INSERT INTO personas (data) VALUES (CAST(:data AS jsonb)) RETURNING id"),
            {"data": data_json},
        )
        return str(result.fetchone()[0])


def save_transactions(engine, persona_uuid: str, txns: list[Transaction]) -> int:
    """Delete existing transactions for persona then bulk-insert new ones.

    Returns the number of rows inserted.
    """
    if engine is None or not txns:
        return 0

    from sqlalchemy import text as sqlt

    # Batch all inserts in a single transaction
    rows = [
        {"persona_id": persona_uuid, "data": _json_dumps(t.model_dump(mode="json"))}
        for t in txns
    ]

    with engine.begin() as conn:
        conn.execute(
            sqlt("DELETE FROM transactions WHERE persona_id = :pid"),
            {"pid": persona_uuid},
        )
        conn.execute(
            sqlt("INSERT INTO transactions (persona_id, data) VALUES (:persona_id, CAST(:data AS jsonb))"),
            rows,
        )

    return len(txns)


# ── Batch runner ──────────────────────────────────────────────────────────── #

def _print_stats(persona: DiagnosticInput, txns: list[Transaction], meta: PersonaMeta) -> None:
    """Print per-persona transaction summary to stdout."""
    debits = [t for t in txns if t.direction == TransactionDirection.DEBIT]
    credits = [t for t in txns if t.direction == TransactionDirection.CREDIT]
    food = [t for t in debits if t.category == TransactionCategory.FOOD_BEVERAGE]
    total_debit = sum(t.amount_idr for t in debits)
    total_credit = sum(t.amount_idr for t in credits)
    food_share = sum(t.amount_idr for t in food) / max(total_debit, 1)
    print(
        f"  {persona.user_id:12s} | income={persona.monthly_income_idr//1000:5d}k "
        f"| gig={int(persona.is_gig_worker)} halal={int(meta.halal_investing)} "
        f"| tx={len(txns):4d} (cr={len(credits):3d} db={len(debits):3d}) "
        f"| debit 3M={total_debit//1000:6d}k credit={total_credit//1000:6d}k "
        f"| food%={food_share:.0%}"
    )


def persist_all(
    personas: list[tuple[DiagnosticInput, PersonaMeta]],
    *,
    days: int = 90,
    dry_run: bool = False,
    base_seed: int = SEED,
) -> None:
    """Generate and optionally persist transactions for all personas.

    In dry-run mode statistics are printed to stdout; no DB writes occur.
    """
    from api.db import get_engine
    engine = None if dry_run else get_engine()

    if engine is None and not dry_run:
        print(
            "WARNING: DATABASE_URL not configured — running in dry-run mode. "
            "Set DATABASE_URL to persist to Postgres."
        )

    total_saved = 0
    print(f"\nGenerating {WINDOW_DAYS}-day transactions for {len(personas)} personas "
          f"(window {WINDOW_START} → {WINDOW_END}, Lebaran {LEBARAN_2026}) …\n")
    print(f"  {'persona':12s} | {'income':>7s} | {'flags':>10s} | "
          f"{'tx count':>8s} | {'3-month totals':>24s} | {'food%':>6s}")
    print("  " + "─" * 90)

    for persona, meta in personas:
        txns = generate_transactions(persona, meta, days=days, base_seed=base_seed)
        _print_stats(persona, txns, meta)

        if engine is not None:
            try:
                persona_uuid = get_or_create_persona_id(engine, persona, meta)
                if persona_uuid:
                    saved = save_transactions(engine, persona_uuid, txns)
                    total_saved += saved
            except Exception as exc:  # noqa: BLE001 — one failure must not abort the run
                print(f"    ⚠ DB error for {persona.user_id}: {exc}")

    print(f"\n{'─'*60}")
    print(f"Done.  {total_saved:,} transaction rows saved to Postgres.")
    print(f"{'─'*60}\n")


# ── Self-check ────────────────────────────────────────────────────────────── #

def _self_check(personas: list[tuple[DiagnosticInput, PersonaMeta]]) -> int:
    """Validate key behavioural invariants across the generated set."""
    errors = 0
    for persona, meta in personas[:5]:  # spot-check first 5
        txns = generate_transactions(persona, meta)
        inc_txns = [t for t in txns if t.category == TransactionCategory.INCOME]
        food_txns = [t for t in txns if t.category == TransactionCategory.FOOD_BEVERAGE]
        motorbike_txns = [
            t for t in txns
            if t.category == TransactionCategory.SHOPPING
            and t.description and "motor" in t.description.lower()
        ]
        halal_check = all(
            m not in (t.merchant or "")
            for t in txns
            for m in _FOOD_NON_HALAL_ADD
        ) if meta.halal_investing else True

        if len(inc_txns) < 2:
            print(f"  FAIL {persona.user_id}: fewer than 2 income transactions ({len(inc_txns)})")
            errors += 1
        if persona.is_gig_worker and len(food_txns) < 20:
            print(f"  FAIL {persona.user_id}: gig worker has too few GoFood transactions ({len(food_txns)})")
            errors += 1
        if persona.is_gig_worker and len(motorbike_txns) == 0:
            print(f"  FAIL {persona.user_id}: gig worker has no motorbike-part transactions")
            errors += 1
        if not halal_check:
            print(f"  FAIL {persona.user_id}: halal persona has non-halal merchant")
            errors += 1

        # Verify income span >= 14 days
        inc_dates = sorted(t.timestamp.date() for t in inc_txns)
        if len(inc_dates) >= 2:
            span = (inc_dates[-1] - inc_dates[0]).days
            if span < 14:
                print(f"  FAIL {persona.user_id}: income span {span} days < 14 (insurance velocity path won't activate)")
                errors += 1

    return errors


# ── CLI ───────────────────────────────────────────────────────────────────── #

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic transaction history for eval personas"
    )
    parser.add_argument("--n",        type=int,  default=50,   help="Number of personas")
    parser.add_argument("--seed",     type=int,  default=SEED, help="RNG seed")
    parser.add_argument("--days",     type=int,  default=90,   help="Transaction window (days)")
    parser.add_argument("--dry-run",  action="store_true",      help="Skip DB write, print stats only")
    parser.add_argument("--check",    action="store_true",      help="Run behavioural self-checks")
    args = parser.parse_args()

    print(f"Generating {args.n} personas (seed={args.seed}) …")
    personas = generate_personas(n=args.n, seed=args.seed)

    if args.check:
        print("Running behavioural self-checks …")
        errors = _self_check(personas)
        if errors:
            print(f"SELF-CHECK FAILED: {errors} error(s)")
            return 1
        print("Self-check PASSED.\n")

    persist_all(
        personas,
        days=args.days,
        dry_run=args.dry_run,
        base_seed=args.seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
