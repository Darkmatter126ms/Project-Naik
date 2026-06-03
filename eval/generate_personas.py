"""eval/generate_personas.py — Sher Min Block 1.

Generates 50 synthetic Indonesian personas for pipeline evaluation. Each
persona is a validated :class:`DiagnosticInput` that can be passed directly to
``run_naik()`` or posted to ``/orchestrate``.

Design principles
-----------------
* All distributions are grounded in Indonesian demographic reality (BPS 2024,
  OJK financial literacy survey 2024, Grab/Shopee gig-economy reports).
* Variables are *correlated*, not independent — a 24-year-old ojek driver
  in a flood-prone kecamatan with Rp 3M income is conservative by necessity,
  not by random chance. This makes the eval set more diagnostic than a purely
  random draw.
* The build-plan fields not present in DiagnosticInput directly (halal_investing,
  current_funds, current_insurance) are encoded into financial_goals as
  structured tags that the diagnostic agent's prompt can parse, and stored in
  the persona_meta sidecar dict for Sher Min's eval scoring.
* Reproducible: default seed 2026 for the 50-persona canonical set; pass
  --seed N for different draws.
* Self-documenting: prints a distribution summary table after generation.

Usage
-----
    # canonical 50 personas (seed 2026)
    python eval/generate_personas.py

    # different draw
    python eval/generate_personas.py --seed 42 --n 100

    # write to file
    python eval/generate_personas.py --out eval/fixtures/personas.json

Schema dependency: api/schemas.py (DiagnosticInput). Run from the repo root.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

# ── repo root on path ────────────────────────────────────────────────────── #
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.schemas import DiagnosticInput, RiskProfile  # noqa: E402

try:
    from faker import Faker
except ImportError:  # pragma: no cover
    raise SystemExit("pip install faker")

# ── 30 Indonesian districts with flood risk scores ────────────────────────── #
# Each entry: (kecamatan_name, city, flood_risk_score 0-1)
# Scores derived from BNPB flood risk maps + local knowledge:
#   >0.7 = high (North Jakarta coast, low-lying Surabaya, delta Medan)
#   0.4-0.7 = medium
#   <0.4 = lower (higher elevation, better drainage)
DISTRICTS = [
    # Jakarta (15 kecamatan — highest flood exposure in the study)
    ("Penjaringan",    "Jakarta",   0.92),  # North Jakarta, coastal, chronic flooding
    ("Pluit",          "Jakarta",   0.88),
    ("Kapuk",          "Jakarta",   0.85),
    ("Muara Baru",     "Jakarta",   0.83),
    ("Cengkareng",     "Jakarta",   0.75),
    ("Kalideres",      "Jakarta",   0.72),
    ("Tambora",        "Jakarta",   0.68),
    ("Cilincing",      "Jakarta",   0.65),
    ("Tanjung Priok",  "Jakarta",   0.60),
    ("Duren Sawit",    "Jakarta",   0.55),
    ("Tebet",          "Jakarta",   0.45),
    ("Menteng",        "Jakarta",   0.30),
    ("Kebayoran",      "Jakarta",   0.25),
    ("Cilandak",       "Jakarta",   0.22),
    ("Pondok Indah",   "Jakarta",   0.18),
    # Surabaya (9 kecamatan)
    ("Kenjeran",       "Surabaya",  0.82),  # Coastal north Surabaya
    ("Semampir",       "Surabaya",  0.78),
    ("Krembangan",     "Surabaya",  0.72),
    ("Benowo",         "Surabaya",  0.68),
    ("Asemrowo",       "Surabaya",  0.64),
    ("Pabean Cantikan","Surabaya",  0.58),
    ("Wonokromo",      "Surabaya",  0.42),
    ("Rungkut",        "Surabaya",  0.32),
    ("Gubeng",         "Surabaya",  0.25),
    # Medan (6 kecamatan — Deli river flood exposure)
    ("Medan Belawan",  "Medan",     0.86),  # Coastal, Belawan port area
    ("Medan Deli",     "Medan",     0.78),
    ("Medan Labuhan",  "Medan",     0.72),
    ("Medan Barat",    "Medan",     0.58),
    ("Medan Helvetia", "Medan",     0.40),
    ("Medan Baru",     "Medan",     0.22),
]
assert len(DISTRICTS) == 30, f"expected 30 districts, got {len(DISTRICTS)}"

# Index by name for quick lookup
DISTRICT_MAP = {d[0]: d for d in DISTRICTS}

# ── Persona metadata sidecar ──────────────────────────────────────────────── #
@dataclass
class PersonaMeta:
    """Fields from the build plan that extend DiagnosticInput for eval scoring.

    Stored alongside the DiagnosticInput so Sher Min's eval harness can score
    do-no-harm (halal), suitability, and trigger precision without re-parsing
    financial_goals strings.
    """
    persona_index: int
    halal_investing: bool
    current_funds: str        # "empty" | "single_fund" | "multi_fund"
    current_insurance: str    # "none" | "credit_life_only" | "full"
    flood_risk_score: float
    expected_priority_gap: Optional[str] = None  # human-labelled expected gap


# ── Distribution helpers ──────────────────────────────────────────────────── #

def lognormal_income(rng: np.random.Generator) -> int:
    """Monthly income in IDR. Lognormal, mean ≈ Rp 4.5M, floor Rp 1.2M."""
    # log(4_200_000) ≈ 15.25; sigma 0.55 gives mean ≈ 4.5M after E[X]=exp(mu+σ²/2)
    mu = math.log(4_200_000)
    sigma = 0.55
    raw = rng.lognormal(mean=mu, sigma=sigma)
    return int(max(1_200_000, min(raw, 30_000_000)))  # cap at 30M (99th pct)


def lognormal_age(rng: np.random.Generator) -> int:
    """Age in years. Lognormal targeting mean ≈ 28, range 18-55."""
    mu = math.log(26.5)
    sigma = 0.22
    raw = rng.lognormal(mean=mu, sigma=sigma)
    return int(max(18, min(round(raw), 55)))


def family_size(rng: np.random.Generator) -> int:
    """Household size. Roughly: 1→15%, 2→25%, 3→25%, 4→20%, 5+→15%."""
    return int(rng.choice([1, 2, 3, 4, 5, 6], p=[0.12, 0.25, 0.27, 0.21, 0.10, 0.05]))


def risk_tolerance(
    income: int, gig: bool, age: int, rng: np.random.Generator
) -> RiskProfile:
    """Risk tolerance derived from income, employment, and age.

    Conservative: low income (<3M) or gig worker or young (<25). Aggressive:
    high income (>12M) and salaried and older (>35). Moderate: everyone else.
    A small jitter lets similar profiles vary.
    """
    score = 0.0
    if income >= 12_000_000: score += 2.0
    elif income >= 6_000_000: score += 1.0
    if not gig: score += 1.0
    if age >= 35: score += 0.5
    elif age <= 24: score -= 0.5
    score += rng.normal(0, 0.5)  # jitter

    if score < 0.8:
        return RiskProfile.CONSERVATIVE
    elif score < 2.2:
        return RiskProfile.MODERATE
    else:
        return RiskProfile.AGGRESSIVE


def investment_horizon(age: int, risk: RiskProfile, rng: np.random.Generator) -> float:
    """Horizon in years: correlated with age and risk tolerance."""
    base = max(1.0, 55.0 - age)  # years to notional retirement
    if risk is RiskProfile.CONSERVATIVE:
        base *= 0.25
    elif risk is RiskProfile.MODERATE:
        base *= 0.45
    else:
        base *= 0.65
    jitter = rng.normal(0, 1.5)
    return round(max(1.0, min(base + jitter, 30.0)), 1)


def existing_holdings(
    income: int, current_funds: str, rng: np.random.Generator
) -> int:
    """Existing investment holdings in IDR, 0 if no funds."""
    if current_funds == "empty":
        return 0
    if current_funds == "single_fund":
        # 1-3 months income as holdings
        months = rng.uniform(1.0, 3.0)
    else:  # multi_fund
        months = rng.uniform(3.0, 12.0)
    return int(income * months)


def financial_goals_tags(
    halal: bool,
    current_funds: str,
    current_insurance: str,
    flood_risk: float,
) -> list[str]:
    """Encode build-plan metadata as structured goal tags in financial_goals.

    The diagnostic agent's prompt reads these; the eval harness also uses them.
    """
    goals: list[str] = []
    if halal:
        goals.append("halal_investing")
    if current_funds == "empty":
        goals.append("mulai_investasi")   # wants to start investing
    elif current_funds == "single_fund":
        goals.append("diversifikasi_portofolio")
    else:
        goals.append("optimasi_portofolio")
    if current_insurance in ("none", "credit_life_only"):
        goals.append("perlindungan_penghasilan")
    if flood_risk >= 0.65:
        goals.append("dana_darurat")       # high-risk area → build buffer
    return goals


def synthetic_transcript(
    gig: bool,
    halal: bool,
    current_funds: str,
    current_insurance: str,
    flood_risk: float,
    rng: np.random.Generator,
) -> str:
    """Generate a minimal Bahasa Indonesia transcript stub for each persona.

    Realistic enough for the offline heuristic scorer to produce meaningful
    scores, but clearly structured from the persona's attributes.
    Transactions (filled by generate_transactions.py) will provide the richer
    signal; this ensures the no-signal validator passes at generation time.
    """
    parts: list[str] = []

    # Employment
    if gig:
        parts.append(rng.choice([
            "Saya kerja sebagai driver ojek online.",
            "Saya freelance, penghasilan tidak tetap tiap bulan.",
            "Saya pekerja lepas, kadang ada kadang tidak.",
        ]))
    else:
        parts.append(rng.choice([
            "Saya karyawan tetap di perusahaan swasta.",
            "Saya pegawai dengan gaji bulanan tetap.",
        ]))

    # Insurance status
    if current_insurance == "none":
        parts.append("Saya tidak punya asuransi sama sekali.")
    elif current_insurance == "credit_life_only":
        parts.append("Saya hanya punya asuransi jiwa kredit dari bank, tidak ada yang lain.")
    else:
        parts.append("Saya sudah punya asuransi kesehatan dan jiwa yang lengkap.")

    # Fund status
    if current_funds == "empty":
        parts.append(rng.choice([
            "Saya belum pernah investasi sama sekali.",
            "Saya tidak punya reksa dana atau investasi apa pun.",
        ]))
    elif current_funds == "single_fund":
        if halal:
            parts.append("Saya punya satu reksa dana syariah tapi jarang saya perhatikan.")
        else:
            parts.append("Saya punya satu reksa dana pasar uang tapi tidak rutin menambah.")
    else:
        parts.append("Saya sudah punya beberapa reksa dana di beberapa manajer investasi.")

    # Flood / location context
    if flood_risk >= 0.65:
        parts.append("Daerah saya sering banjir kalau musim hujan.")

    # Halal preference
    if halal:
        parts.append("Saya ingin investasi yang sesuai prinsip syariah.")

    return " ".join(parts)

def generate_persona(
    index: int,
    rng: np.random.Generator,
    fake: Faker,
    *,
    gig_override: bool | None = None,
    halal_override: bool | None = None,
    funds_override: str | None = None,
    ins_override: str | None = None,
) -> tuple[DiagnosticInput, PersonaMeta]:
    """Generate one persona as (DiagnosticInput, PersonaMeta).

    Override parameters allow the caller (generate_personas) to apply
    stratified sampling for exact build-plan proportions.
    """

    # Structural draws
    district, city, flood_risk = DISTRICTS[rng.integers(0, 30)]
    age = lognormal_age(rng)
    income = lognormal_income(rng)
    gig   = gig_override   if gig_override   is not None else bool(rng.random() < 0.40)
    halal = halal_override if halal_override is not None else bool(rng.random() < 0.35)
    hh = family_size(rng)
    risk = risk_tolerance(income, gig, age, rng)
    horizon = investment_horizon(age, risk, rng)

    # Asset / insurance status
    if funds_override is not None:
        current_funds = funds_override
    else:
        empty_prob = 0.70 - min(0.30, (income - 1_200_000) / 30_000_000)
        r = rng.random()
        if r < empty_prob:
            current_funds = "empty"
        elif r < empty_prob + 0.20:
            current_funds = "single_fund"
        else:
            current_funds = "multi_fund"

    if ins_override is not None:
        current_insurance = ins_override
    else:
        ins_r = rng.random()
        if ins_r < 0.10:
            current_insurance = "none"
        elif ins_r < 0.90:
            current_insurance = "credit_life_only"
        else:
            current_insurance = "full"

    holdings = existing_holdings(income, current_funds, rng)
    goals = financial_goals_tags(halal, current_funds, current_insurance, flood_risk)
    transcript = synthetic_transcript(gig, halal, current_funds, current_insurance, flood_risk, rng)

    persona = DiagnosticInput(
        user_id=f"eval_{index:03d}",
        locale="id-ID",
        age=age,
        monthly_income_idr=income,
        kecamatan=district,
        city=city,
        risk_tolerance=risk,
        household_size=hh,
        is_gig_worker=gig,
        investment_horizon_years=horizon,
        existing_holdings_idr=holdings if holdings > 0 else None,
        financial_goals=goals,
        voice_transcript=transcript,
        transactions=[],
    )

    meta = PersonaMeta(
        persona_index=index,
        halal_investing=halal,
        current_funds=current_funds,
        current_insurance=current_insurance,
        flood_risk_score=round(float(flood_risk), 3),
    )

    return persona, meta


def generate_personas(
    n: int = 50, seed: int = 2026
) -> list[tuple[DiagnosticInput, PersonaMeta]]:
    """Generate ``n`` personas with a fixed RNG seed for reproducibility.

    Key build-plan flags (gig_worker, halal_investing, current_funds,
    current_insurance) are assigned via stratified sampling — every n=50 run
    guarantees counts that hit the build-plan targets exactly, not just in
    expectation. Continuous variables (age, income, etc.) remain lognormal.
    """
    rng = np.random.default_rng(seed)
    fake = Faker("id_ID")
    fake.seed_instance(seed)

    # ── Stratified counts (exact targets) ──────────────────────────────────
    n_gig   = round(n * 0.40)   # 40% gig → 20
    n_halal = round(n * 0.35)   # 35% halal → 17/18
    # current_funds: 70% empty, 20% single, 10% multi
    n_empty  = round(n * 0.70)
    n_single = round(n * 0.20)
    n_multi  = n - n_empty - n_single
    # current_insurance: 10% none, 80% credit_life_only, 10% full
    n_ins_none = round(n * 0.10)
    n_ins_full = round(n * 0.10)
    n_ins_clo  = n - n_ins_none - n_ins_full

    # Build shuffled flag arrays then assign by index
    gig_arr   = rng.permutation(np.array([True]*n_gig + [False]*(n-n_gig)))
    halal_arr = rng.permutation(np.array([True]*n_halal + [False]*(n-n_halal)))
    funds_arr = rng.permutation(
        np.array(["empty"]*n_empty + ["single_fund"]*n_single + ["multi_fund"]*n_multi)
    )
    ins_arr = rng.permutation(
        np.array(["none"]*n_ins_none + ["credit_life_only"]*n_ins_clo + ["full"]*n_ins_full)
    )

    personas = []
    for i in range(n):
        p, m = generate_persona(
            i, rng, fake,
            gig_override=bool(gig_arr[i]),
            halal_override=bool(halal_arr[i]),
            funds_override=str(funds_arr[i]),
            ins_override=str(ins_arr[i]),
        )
        personas.append((p, m))
    return personas


# ── Distribution summary ──────────────────────────────────────────────────── #

def print_summary(personas: list[tuple[DiagnosticInput, PersonaMeta]]) -> None:
    inputs = [p for p, _ in personas]
    metas = [m for _, m in personas]

    def pct(n, total=len(personas)):
        return f"{n}/{total} ({100*n//total}%)"

    ages = [p.age for p in inputs]
    incomes = [p.monthly_income_idr / 1_000_000 for p in inputs]

    print("\n" + "═" * 58)
    print(" PERSONA DISTRIBUTION SUMMARY  (n={})".format(len(personas)))
    print("═" * 58)

    print(f"\n{'AGE':}")
    print(f"  mean={sum(ages)/len(ages):.1f}  median={sorted(ages)[len(ages)//2]}  "
          f"min={min(ages)}  max={max(ages)}")

    print(f"\nINCOME (Rp juta/bulan):")
    print(f"  mean={sum(incomes)/len(incomes):.2f}  median={sorted(incomes)[len(incomes)//2]:.2f}  "
          f"min={min(incomes):.2f}  max={max(incomes):.2f}")

    # Risk profile
    risk_counts = {r.value: sum(1 for p in inputs if p.risk_tolerance == r)
                   for r in RiskProfile}
    print("\nRISK PROFILE:")
    for k, v in risk_counts.items():
        print(f"  {k:12s} {pct(v)}")

    # Gig / halal / funds / insurance
    n_gig   = sum(1 for p in inputs if p.is_gig_worker)
    n_halal = sum(1 for m in metas if m.halal_investing)
    print(f"\nGIG WORKER:         {pct(n_gig)}")
    print(f"HALAL INVESTING:    {pct(n_halal)}")

    for label, key in [("CURRENT FUNDS", "current_funds"),
                        ("CURRENT INSURANCE", "current_insurance")]:
        from collections import Counter
        counts = Counter(getattr(m, key) for m in metas)
        print(f"\n{label}:")
        for k, v in sorted(counts.items()):
            print(f"  {k:20s} {pct(v)}")

    # City distribution
    from collections import Counter
    cities = Counter(p.city for p in inputs)
    print("\nCITY:")
    for city, count in sorted(cities.items()):
        print(f"  {city:12s} {pct(count)}")

    # Flood risk buckets
    high   = sum(1 for m in metas if m.flood_risk_score >= 0.65)
    medium = sum(1 for m in metas if 0.40 <= m.flood_risk_score < 0.65)
    low    = sum(1 for m in metas if m.flood_risk_score < 0.40)
    print(f"\nFLOOD RISK:")
    print(f"  high   (≥0.65)  {pct(high)}")
    print(f"  medium (0.4-0.65) {pct(medium)}")
    print(f"  low    (<0.4)   {pct(low)}")

    print("\n" + "═" * 58 + "\n")


# ── Serialisation helpers ─────────────────────────────────────────────────── #

def personas_to_json(
    personas: list[tuple[DiagnosticInput, PersonaMeta]]
) -> list[dict]:
    """Serialise to a list of dicts with both DiagnosticInput and meta fields."""
    out = []
    for p, m in personas:
        d = p.model_dump(mode="json")
        d["_meta"] = {
            "halal_investing": m.halal_investing,
            "current_funds": m.current_funds,
            "current_insurance": m.current_insurance,
            "flood_risk_score": m.flood_risk_score,
        }
        out.append(d)
    return out


# ── CLI entry point ───────────────────────────────────────────────────────── #

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic eval personas")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", type=str, default=None,
                        help="Write JSON to this path (e.g. eval/fixtures/personas.json)")
    args = parser.parse_args()

    print(f"Generating {args.n} personas (seed={args.seed}) …")
    personas = generate_personas(n=args.n, seed=args.seed)

    # Validate: every persona must round-trip through DiagnosticInput.
    errors = 0
    for i, (p, _) in enumerate(personas):
        try:
            DiagnosticInput.model_validate(p.model_dump(mode="json"))
        except Exception as e:
            print(f"  FAIL validation persona {i}: {e}")
            errors += 1
    if errors:
        print(f"VALIDATION FAILED: {errors} personas invalid")
        return 1

    print_summary(personas)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "_meta": {
                "description": "50 synthetic eval personas for the Naik pipeline.",
                "seed": args.seed,
                "n": args.n,
                "schema": "DiagnosticInput (api/schemas.py); _meta carries eval-only fields",
            },
            "personas": personas_to_json(personas),
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Written {args.out} ({len(personas)} personas)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
