"""Naik wealth agent.

Ranks OJK-licensed reksa dana for a user and emits a validated
:class:`WealthRecommendation` (top-three picks, best-first, with one-sentence
Bahasa justifications). It consumes the diagnostic agent's
:class:`WellnessVector` and the user's :class:`DiagnosticInput`, and calls the
``get_fund_list`` tool for its candidate universe.

The wedge over Bibit's standalone robo advisor is explicit: Naik sees the user's
anonymised Shopee transaction patterns. A user whose spend is dominated by food
delivery, or who is a gig worker, or whose income arrives irregularly, very
likely has *irregular income* — so we weight capital-preserving pasar uang and
short-duration obligasi (pendapatan tetap) funds more heavily than saham for
them, and we say so in the rationale. Bibit's six generic questions cannot do
this.

Two execution paths, same output contract (mirrors :mod:`agents.diagnostic`):

* **Heuristic path** (default; used when no ``OPENAI_API_KEY`` is set — offline
  dev, CI, flaky-wifi demo): calls ``get_fund_list`` directly, scores every
  candidate with the deterministic ranker below, takes the top three, and writes
  template Bahasa justifications. Fully reproducible.
* **Model path** (when a key is present): runs a genuine tool-calling loop so the
  model invokes ``get_fund_list`` (deciding ``sharia_only`` from persona
  context), THEN we apply the SAME deterministic ranker to choose and order the
  picks, and let the model author the per-fund and overall Bahasa justifications.

Design principle borrowed from the diagnostic/CRRA work: the *selection* is
computed deterministically in Python so it is auditable and reproducible; the
model only ever adds the natural-language layer. A model hiccup falls back to the
heuristic path and never breaks the pipeline.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel

try:  # deployed import style
    from api.schemas import (
        DiagnosticInput,
        FundPick,
        FundRiskLevel,
        FundType,
        RiskProfile,
        TransactionDirection,
        WealthRecommendation,
        WellnessDimension,
        WellnessVector,
    )
    from naik_agents.tools import AGENTS_SDK_AVAILABLE, WEALTH_TOOLS, get_fund_list
except ImportError:  # pragma: no cover - script/direct execution fallback
    import sys

    _HERE = os.path.dirname(__file__)
    sys.path.insert(0, os.path.join(_HERE, ".."))
    sys.path.insert(0, os.path.join(_HERE, "..", "api"))
    from schemas import (  # type: ignore
        DiagnosticInput,
        FundPick,
        FundRiskLevel,
        FundType,
        RiskProfile,
        TransactionDirection,
        WealthRecommendation,
        WellnessDimension,
        WellnessVector,
    )
    from tools import AGENTS_SDK_AVAILABLE, WEALTH_TOOLS, get_fund_list  # type: ignore

DEFAULT_MODEL = os.environ.get("NAIK_WEALTH_MODEL", "gpt-5.5")

# Number of picks the recommendation surfaces (build plan: top 3).
TOP_N = 3

# --------------------------------------------------------------------------- #
# System prompt (model path)                                                  #
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """\
You are Naik's wealth agent for Indonesian users. You recommend OJK-licensed \
reksa dana (mutual funds). You have a get_fund_list tool; call it once to get \
the candidate funds. Call it with sharia_only=true when the user requires \
syariah-compliant (halal) investments.

You have access to this user's Shopee transaction patterns, which Bibit's \
standalone robo advisor does not. A user spending 60% on food delivery likely \
has irregular income; weight pasar uang and short-duration obligasi \
(pendapatan tetap) funds more heavily than saham for them. Protection comes \
before growth: if the user's weakest wellness dimension is risk_management, \
emergency_fund, or liquidity, lead with capital-preserving, liquid funds while \
they close that gap — do not push equity (saham) funds.

Rank candidates by: (1) match to the user's effective risk level, (2) sharia \
compliance when required, (3) low expense ratio, (4) return consistency \
(1-year and 3-year returns close together and positive). Return the top 3.

You will be given the deterministically-chosen ranked picks. Your job is the \
LANGUAGE, not the maths: write ONE natural sentence of Bahasa Indonesia per \
fund explaining why it fits THIS user (reference their irregular income / \
Shopee spend pattern where relevant), plus one short overall rationale \
sentence in Bahasa. Do not invent funds or numbers; use only the picks given. \
Output JSON only, no prose, no code fences.
"""


# --------------------------------------------------------------------------- #
# Risk-profile / fund-type mappings                                           #
# --------------------------------------------------------------------------- #

_PROFILE_RANK: dict[RiskProfile, int] = {
    RiskProfile.CONSERVATIVE: 0,
    RiskProfile.MODERATE: 1,
    RiskProfile.AGGRESSIVE: 2,
}
_RANK_PROFILE: dict[int, RiskProfile] = {v: k for k, v in _PROFILE_RANK.items()}

_PROFILE_TO_FUND_RISK: dict[RiskProfile, FundRiskLevel] = {
    RiskProfile.CONSERVATIVE: FundRiskLevel.LOW,
    RiskProfile.MODERATE: FundRiskLevel.MEDIUM,
    RiskProfile.AGGRESSIVE: FundRiskLevel.HIGH,
}
_FUND_RISK_RANK: dict[FundRiskLevel, int] = {
    FundRiskLevel.LOW: 0,
    FundRiskLevel.MEDIUM: 1,
    FundRiskLevel.HIGH: 2,
}

# Per-target-risk fund-type preference (1.0 = ideal vehicle, 0.0 = inappropriate).
# Low target (protection-first / irregular income) favours capital preservation;
# high target favours growth. INDEX sits near EQUITY on the growth side.
_TYPE_PREF: dict[FundRiskLevel, dict[FundType, float]] = {
    FundRiskLevel.LOW: {
        FundType.MONEY_MARKET: 1.00,
        FundType.FIXED_INCOME: 0.65,
        FundType.BALANCED: 0.35,
        FundType.INDEX: 0.20,
        FundType.EQUITY: 0.10,
    },
    FundRiskLevel.MEDIUM: {
        FundType.FIXED_INCOME: 1.00,
        FundType.BALANCED: 0.85,
        FundType.MONEY_MARKET: 0.60,
        FundType.INDEX: 0.55,
        FundType.EQUITY: 0.50,
    },
    FundRiskLevel.HIGH: {
        FundType.EQUITY: 1.00,
        FundType.INDEX: 0.90,
        FundType.BALANCED: 0.70,
        FundType.FIXED_INCOME: 0.40,
        FundType.MONEY_MARKET: 0.20,
    },
}

# Wellness dimensions whose weakness means "shore up the foundation before
# reaching for growth" — they downgrade the effective risk one tier.
_PROTECTION_GAPS = {
    WellnessDimension.RISK_MANAGEMENT,
    WellnessDimension.EMERGENCY_FUND,
    WellnessDimension.LIQUIDITY,
}

# Ranking component weights (sum to 1.0). risk_fit dominates because matching the
# user's capacity for loss is the primary instruction; type_fit carries the
# Shopee/irregular-income wedge.
_W_RISK_FIT = 0.40
_W_TYPE_FIT = 0.25
_W_COST_FIT = 0.15
_W_CONSISTENCY_FIT = 0.20

# Halal-intent keywords scanned in goals/transcript when sharia_only is not set.
_SHARIA_KEYWORDS = ("syariah", "sharia", "halal", "sesuai syariah", "islami")


# --------------------------------------------------------------------------- #
# Persona signals derived from Shopee transactions (the wedge)                #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class IncomeSignal:
    """What the transaction history says about income stability.

    ``irregular`` is the headline used to tilt the ranking and the rationale;
    the components are kept so the justification can name the evidence.
    """

    irregular: bool
    is_gig_worker: bool
    food_delivery_share: float  # share of debits on food & beverage
    income_cv: float            # coefficient of variation of income inflows


def _coefficient_of_variation(values: list[int]) -> float:
    """Std/mean of a list of positive amounts; 0 when fewer than two points."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    if mean <= 0:
        return 0.0
    var = sum((v - mean) ** 2 for v in values) / n
    return (var ** 0.5) / mean


def assess_income(inp: DiagnosticInput, wellness: WellnessVector) -> IncomeSignal:
    """Infer income irregularity from the Shopee ledger + profile + wellness.

    The build plan's worked example — "spending 60% on food delivery likely has
    irregular income" — is one of three signals we combine: a high food-delivery
    share of spend, an explicit gig-worker flag, and a high coefficient of
    variation across income inflows. A weak liquidity/emergency-fund score
    reinforces it. Any strong signal flips ``irregular`` to True.
    """
    txns = inp.transactions
    debits = [t for t in txns if t.direction is TransactionDirection.DEBIT]
    debit_total = sum(t.amount_idr for t in debits) or 1
    food_delivery = sum(
        t.amount_idr for t in debits if t.category is t.category.FOOD_BEVERAGE
    )
    food_share = food_delivery / debit_total
    # A high food-delivery share only signals irregular income across a basket
    # big enough to be a pattern — one large order in a thin history does not.
    food_signal = food_share if len(debits) >= 5 else 0.0

    incomes = [
        t.amount_idr
        for t in txns
        if t.direction is TransactionDirection.CREDIT and t.category is t.category.INCOME
    ]
    income_cv = _coefficient_of_variation(incomes)

    weak_buffer = (
        wellness.liquidity < 45.0 or wellness.emergency_fund < 45.0
    )

    irregular = (
        inp.is_gig_worker
        or food_signal >= 0.40
        or income_cv >= 0.25
        or (weak_buffer and food_signal >= 0.30)
    )
    return IncomeSignal(
        irregular=irregular,
        is_gig_worker=inp.is_gig_worker,
        food_delivery_share=food_share,
        income_cv=income_cv,
    )


def resolve_sharia_only(
    inp: DiagnosticInput, explicit: Optional[bool]
) -> bool:
    """Decide whether to restrict to syariah-compliant funds.

    ``explicit`` (from the orchestrator / a persona fixture carrying a
    halal-investing flag) wins when provided. Otherwise we infer halal intent
    from the user's stated goals and voice transcript — the only halal signals
    the frozen ``DiagnosticInput`` schema can carry without a field change.
    """
    if explicit is not None:
        return explicit
    haystack = " ".join(inp.financial_goals + [inp.voice_transcript]).lower()
    return any(kw in haystack for kw in _SHARIA_KEYWORDS)


# --------------------------------------------------------------------------- #
# Effective risk profile (declared profile, tempered by the diagnosis)        #
# --------------------------------------------------------------------------- #


def effective_risk_profile(
    inp: DiagnosticInput, wellness: WellnessVector, signal: IncomeSignal
) -> RiskProfile:
    """The risk profile the ranking actually assumes.

    Starts from the user's self-declared profile and downgrades it (toward
    capital preservation) when the foundation is shaky: a protection/liquidity
    priority gap, or irregular income. Never upgrades — Naik does not talk a
    cautious user into more risk than they declared.
    """
    rank = _PROFILE_RANK[inp.risk_tolerance]
    if wellness.priority_gap in _PROTECTION_GAPS:
        rank -= 1
    if signal.irregular:
        rank -= 1
    rank = max(0, min(2, rank))
    return _RANK_PROFILE[rank]


# --------------------------------------------------------------------------- #
# Deterministic ranker (shared by both paths)                                 #
# --------------------------------------------------------------------------- #


def _risk_fit(fund_risk: FundRiskLevel, target: FundRiskLevel) -> float:
    """1.0 for an exact tier match, decaying with distance."""
    diff = abs(_FUND_RISK_RANK[fund_risk] - _FUND_RISK_RANK[target])
    return {0: 1.0, 1: 0.5, 2: 0.15}.get(diff, 0.15)


def _cost_fit(expense_ratio_pct: float) -> float:
    """Lower expense ratio -> higher fit. 0.50% -> 1.0, 2.00% -> 0.0 (clamped)."""
    return max(0.0, min(1.0, 1.0 - (expense_ratio_pct - 0.5) / 1.5))


def _consistency_fit(return_1y: Optional[float], return_3y: Optional[float]) -> float:
    """Reward returns that are stable (1y close to 3y) AND positive.

    Missing data is treated as neutral (0.5) rather than penalised, so a fund
    with a short track record is not unfairly buried.
    """
    if return_1y is None and return_3y is None:
        return 0.5
    r1 = return_1y if return_1y is not None else return_3y
    r3 = return_3y if return_3y is not None else return_1y
    gap = abs(r1 - r3)
    stability = max(0.0, min(1.0, 1.0 - gap / 5.0))   # within 5pp -> good
    positivity = max(0.0, min(1.0, r3 / 8.0))          # ~8% 3y -> full marks
    return 0.6 * stability + 0.4 * positivity


def score_fund(
    fund: dict, *, target_risk: FundRiskLevel
) -> float:
    """Score one fund 0–100 for this user. Pure, deterministic, auditable."""
    fund_type = FundType(fund["fund_type"])
    fund_risk = FundRiskLevel(fund["risk_level"])

    risk_fit = _risk_fit(fund_risk, target_risk)
    type_fit = _TYPE_PREF[target_risk].get(fund_type, 0.3)
    cost_fit = _cost_fit(float(fund["expense_ratio_pct"]))
    consistency_fit = _consistency_fit(
        fund.get("return_1y_pct"), fund.get("return_3y_annualised_pct")
    )

    score = 100.0 * (
        _W_RISK_FIT * risk_fit
        + _W_TYPE_FIT * type_fit
        + _W_COST_FIT * cost_fit
        + _W_CONSISTENCY_FIT * consistency_fit
    )
    return round(max(0.0, min(100.0, score)), 1)


def rank_funds(
    candidates: list[dict], *, target_risk: FundRiskLevel, top_n: int = TOP_N
) -> list[tuple[dict, float]]:
    """Return the top-N (fund, score) pairs, best-first.

    Deterministic tie-breaks: higher score, then lower expense ratio, then
    fund_id — so the same inputs always yield the same ordering (CI-safe).
    """
    scored = [(f, score_fund(f, target_risk=target_risk)) for f in candidates]
    scored.sort(
        key=lambda fs: (-fs[1], float(fs[0]["expense_ratio_pct"]), str(fs[0].get("fund_id", "")))
    )
    return scored[:top_n]


# --------------------------------------------------------------------------- #
# Bahasa justifications (heuristic path)                                       #
# --------------------------------------------------------------------------- #

_TYPE_LABEL_ID: dict[FundType, str] = {
    FundType.MONEY_MARKET: "reksa dana pasar uang",
    FundType.FIXED_INCOME: "reksa dana pendapatan tetap",
    FundType.BALANCED: "reksa dana campuran",
    FundType.EQUITY: "reksa dana saham",
    FundType.INDEX: "reksa dana indeks",
}


def _fund_justification_id(
    fund: dict, *, signal: IncomeSignal, sharia: bool, rank: int
) -> str:
    """One natural Bahasa sentence explaining why this fund fits the user.

    ``rank`` is 0-indexed: 0 = top pick (most personalised), 1 = strong
    alternative (different track-record angle), 2 = third option (comparison
    or diversification within the same category).
    """
    fund_type = FundType(fund["fund_type"])
    label = _TYPE_LABEL_ID[fund_type]
    sharia_clause = "sesuai prinsip syariah, " if (sharia and fund.get("is_sharia")) else ""
    er = float(fund["expense_ratio_pct"])

    if fund_type in (FundType.MONEY_MARKET, FundType.FIXED_INCOME):
        liquid_clause = (
            "likuiditas tinggi dan risiko rendah sehingga dana mudah dicairkan kapan pun dibutuhkan"
            if fund_type is FundType.MONEY_MARKET
            else "risiko moderat dengan potensi imbal hasil sedikit lebih tinggi dari pasar uang"
        )
        if rank == 0:
            if signal.is_gig_worker:
                persona_clause = (
                    ", pilihan utama kami untuk penghasilan tidak tetap seperti driver ojek online"
                )
            elif signal.irregular:
                persona_clause = (
                    ", cocok untuk penghasilan yang berfluktuasi seperti pola Anda"
                )
            else:
                persona_clause = ""
            return (
                f"{label.capitalize()} {sharia_clause}menawarkan {liquid_clause}"
                f"{persona_clause}, dengan biaya pengelolaan rendah ({er:.2f}%)."
            )
        # For ranks 1 and 2 the sharia_clause (which ends with ", ") would break
        # the grammar before "adalah" / "melengkapi"; append a clean suffix instead.
        sharia_suffix = " (syariah)" if (sharia and fund.get("is_sharia")) else ""
        if rank == 1:
            return (
                f"{label.capitalize()}{sharia_suffix} adalah alternatif kuat dengan rekam "
                f"jejak manajer investasi yang berbeda, memberi diversifikasi manajer "
                f"dengan biaya pengelolaan {er:.2f}%."
            )
        else:
            return (
                f"{label.capitalize()}{sharia_suffix} melengkapi dua pilihan di atas "
                f"dan dapat menjadi cadangan jika slot investasi salah satunya sudah penuh, "
                f"dengan biaya pengelolaan {er:.2f}%."
            )
    return (
        f"{label.capitalize()} {sharia_clause}memberi potensi pertumbuhan jangka panjang "
        f"saat fondasi perlindungan sudah terpasang, dengan biaya pengelolaan {er:.2f}%."
    )


def _overall_rationale_id(
    *, effective: RiskProfile, signal: IncomeSignal, protection_first: bool, sharia: bool
) -> str:
    """The recommendation-level Bahasa summary (one natural sentence)."""
    if signal.irregular:
        text = (
            "Pola pengeluaran Shopee Anda menunjukkan penghasilan yang cenderung tidak tetap, "
            "jadi kami memprioritaskan dana yang likuid dan berisiko rendah"
        )
    else:
        text = (
            "Berdasarkan profil dan pola transaksi Anda, kami memilih dana yang sesuai dengan "
            "tingkat risiko Anda"
        )
    if protection_first:
        text += (
            " untuk saat ini; tingkatkan ke dana pertumbuhan setelah "
            "perlindungan penghasilan Anda terpasang"
        )
    if sharia:
        text += ", dan semuanya sesuai prinsip syariah"
    return text + "."


# --------------------------------------------------------------------------- #
# Contribution / horizon helpers                                              #
# --------------------------------------------------------------------------- #


def _recommended_monthly_contribution(inp: DiagnosticInput, protection_first: bool) -> int:
    """A modest, affordable monthly top-up in whole rupiah.

    Base ~10% of monthly income, halved while protection is the priority gap (we
    do not steer money into investing before the user is protected). Rounded to
    the nearest Rp 50k for a clean, human number.
    """
    base = inp.monthly_income_idr * (0.05 if protection_first else 0.10)
    rounded = int(round(base / 50_000.0)) * 50_000
    return max(0, rounded)


def _allocation_pct(scores: list[float]) -> Optional[list[float]]:
    """Allocation across picks, proportional to score, summing to ~100.

    Returns None for a single pick (the schema treats absent allocation as
    100% to the one fund). The last entry absorbs rounding so the sum is exact.
    """
    if len(scores) <= 1:
        return None
    total = sum(scores) or 1.0
    pct = [round(s / total * 100.0, 1) for s in scores]
    pct[-1] = round(100.0 - sum(pct[:-1]), 1)  # make it sum to exactly 100.0
    return pct


# --------------------------------------------------------------------------- #
# Assembly                                                                     #
# --------------------------------------------------------------------------- #


def _build_recommendation(
    inp: DiagnosticInput,
    wellness: WellnessVector,
    ranked: list[tuple[dict, float]],
    *,
    effective: RiskProfile,
    signal: IncomeSignal,
    sharia: bool,
    justifications: Optional[list[str]] = None,
    overall_rationale: Optional[str] = None,
) -> WealthRecommendation:
    """Turn ranked funds into a validated WealthRecommendation.

    ``justifications``/``overall_rationale`` are supplied by the model path; when
    absent (heuristic path) we generate them from templates. Either way the
    picks, scores, allocation, contribution and horizon are deterministic.
    """
    protection_first = wellness.priority_gap in _PROTECTION_GAPS

    picks: list[FundPick] = []
    for i, (fund, score) in enumerate(ranked):
        rationale = (
            justifications[i]
            if justifications and i < len(justifications)
            else _fund_justification_id(fund, signal=signal, sharia=sharia, rank=i)
        )
        picks.append(
            FundPick(
                fund_id=fund["fund_id"],
                fund_name=fund["fund_name"],
                fund_type=FundType(fund["fund_type"]),
                manager=fund["manager"],
                risk_level=FundRiskLevel(fund["risk_level"]),
                expense_ratio_pct=float(fund["expense_ratio_pct"]),
                return_1y_pct=fund.get("return_1y_pct"),
                return_3y_annualised_pct=fund.get("return_3y_annualised_pct"),
                aum_idr=fund.get("aum_idr"),
                min_investment_idr=int(fund["min_investment_idr"]),
                is_ojk_licensed=True,
                is_sharia=bool(fund.get("is_sharia", False)),
                match_score=score,
                rationale=rationale,
            )
        )

    horizon = inp.investment_horizon_years if inp.investment_horizon_years is not None else 3.0

    return WealthRecommendation(
        user_id=inp.user_id,
        risk_profile_used=effective,
        investment_horizon_years=float(horizon),
        recommended_monthly_contribution_idr=_recommended_monthly_contribution(inp, protection_first),
        target_amount_idr=None,  # no explicit goal target inferred; set by goal-planning later
        picks=picks,
        allocation_pct=_allocation_pct([p.match_score for p in picks]),
        rationale=(
            overall_rationale
            or _overall_rationale_id(
                effective=effective, signal=signal, protection_first=protection_first, sharia=sharia
            )
        ),
    )


# --------------------------------------------------------------------------- #
# Model path                                                                   #
# --------------------------------------------------------------------------- #

class _WealthJustifications(BaseModel):
    """Structured output the wealth agent returns: Bahasa prose only.

    The SDK enforces this shape via the agent's ``output_type``. The picks
    themselves are ranked deterministically in Python and never come from the
    model — it authors only the per-pick sentences (same order) and one overall
    rationale.
    """

    fund_justifications: list[str]
    overall_rationale: str


def _persona_context_block(
    inp: DiagnosticInput, wellness: WellnessVector, signal: IncomeSignal
) -> str:
    """Compact persona + diagnosis + Shopee-signal context for the model."""
    return (
        f"User: age {inp.age}, income Rp {inp.monthly_income_idr:,}/month, "
        f"kecamatan {inp.kecamatan}, gig worker: {'yes' if inp.is_gig_worker else 'no'}, "
        f"declared risk: {inp.risk_tolerance.value}, "
        f"horizon: {inp.investment_horizon_years or 'unknown'} years.\n"
        f"Diagnosis: priority gap is {wellness.priority_gap.value} "
        f"(overall {wellness.overall_score}); risk_management={wellness.risk_management}, "
        f"liquidity={wellness.liquidity}, growth={wellness.growth}.\n"
        f"Shopee signal: irregular income = {signal.irregular} "
        f"(food-delivery share {signal.food_delivery_share:.0%}, "
        f"income variability {signal.income_cv:.2f})."
    )


def _justify_with_model(
    inp: DiagnosticInput,
    wellness: WellnessVector,
    ranked: list[tuple[dict, float]],
    *,
    sharia_only: bool,
    model: str,
) -> tuple[list[str], str]:
    """Author Bahasa justifications via the OpenAI Agents SDK.

    Builds an :class:`Agent` carrying the ``get_fund_list`` tool (so the model
    can inspect the catalogue, faithful to the build plan's "calls get_fund_list
    tool") and a structured ``output_type``. The picks are already ranked
    deterministically in Python; the agent only writes one Bahasa sentence per
    pick (same order) plus an overall rationale. Raises on any SDK/parse error
    so the caller can fall back to templates.
    """
    from agents import Agent, Runner  # lazy: offline/no-SDK runs never reach here

    context = _persona_context_block(inp, wellness, signal=assess_income(inp, wellness))
    picks_for_model = [
        {
            "fund_name": f["fund_name"],
            "fund_type": f["fund_type"],
            "risk_level": f["risk_level"],
            "expense_ratio_pct": f["expense_ratio_pct"],
            "return_1y_pct": f.get("return_1y_pct"),
            "return_3y_annualised_pct": f.get("return_3y_annualised_pct"),
            "is_sharia": f.get("is_sharia", False),
            "match_score": s,
        }
        for f, s in ranked
    ]
    instruction = (
        "These are the final ranked picks (do not change or reorder them). You "
        "may call get_fund_list to inspect the catalogue. Write one Bahasa "
        "Indonesia sentence per fund in this exact order explaining the fit for "
        "this user, plus one overall rationale sentence. "
        f"sharia_required={sharia_only}.\n"
        + json.dumps(picks_for_model, ensure_ascii=False)
    )

    agent = Agent(
        name="Naik Wealth",
        instructions=SYSTEM_PROMPT,
        model=model,
        tools=WEALTH_TOOLS,
        output_type=_WealthJustifications,
    )
    result = Runner.run_sync(agent, f"{context}\n\n{instruction}")
    out: _WealthJustifications = result.final_output
    return list(out.fund_justifications), str(out.overall_rationale)


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #


@dataclass
class WealthResult:
    """Wraps the recommendation with provenance (which path produced it)."""

    recommendation: WealthRecommendation
    source: str  # "model" or "heuristic"


def run_wealth(
    wellness: WellnessVector,
    inp: DiagnosticInput,
    *,
    sharia_only: Optional[bool] = None,
    model: Optional[str] = None,
    force_heuristic: bool = False,
) -> WealthResult:
    """Rank funds for a user and return a validated :class:`WealthRecommendation`.

    Args:
        wellness: the diagnostic agent's output (drives protection-first tilt).
        inp: the user's intake (transactions feed the irregular-income wedge).
        sharia_only: force the sharia filter; when None it is inferred from the
            user's goals/transcript (a halal persona fixture should pass True).
        model: override the model name for the model path.
        force_heuristic: skip the model path even if a key is present (CI/tests).

    The selection (which funds, in what order, with what scores) is deterministic
    in every path; the model, when available, only authors the Bahasa
    justifications. A model error falls back to templated Bahasa and never breaks
    the pipeline.
    """
    sharia = resolve_sharia_only(inp, sharia_only)
    signal = assess_income(inp, wellness)
    effective = effective_risk_profile(inp, wellness, signal)
    target_risk = _PROFILE_TO_FUND_RISK[effective]

    candidates = get_fund_list(sharia_only=sharia)
    if not candidates:  # halal filter emptied the set — fall back to full catalogue
        candidates = get_fund_list(sharia_only=False)
        sharia = False
    ranked = rank_funds(candidates, target_risk=target_risk, top_n=TOP_N)

    use_model = (
        (not force_heuristic)
        and bool(os.environ.get("OPENAI_API_KEY"))
        and AGENTS_SDK_AVAILABLE
    )
    justifications: Optional[list[str]] = None
    overall: Optional[str] = None
    source = "heuristic"

    if use_model:
        try:
            justifications, overall = _justify_with_model(
                inp, wellness, ranked, sharia_only=sharia, model=model or DEFAULT_MODEL
            )
            source = "model"
        except Exception:  # noqa: BLE001 - never let a model hiccup break the pipeline
            justifications, overall, source = None, None, "heuristic"

    recommendation = _build_recommendation(
        inp,
        wellness,
        ranked,
        effective=effective,
        signal=signal,
        sharia=sharia,
        justifications=justifications,
        overall_rationale=overall,
    )

    # Append a calendar-aware behavioural nudge to the overall rationale.
    # The nudge is selected from design/prompts/nudges.json based on the
    # persona's priority_gap and the current calendar context (flood season,
    # Lebaran, payday week, post-bonus).  Falls back silently to "" so a
    # missing or broken nudges.json never breaks the pipeline.
    try:
        from naik_agents.nudges import select_nudge
        nudge = select_nudge(wellness, inp)
        if nudge:
            recommendation = recommendation.model_copy(
                update={"rationale": f"{recommendation.rationale} {nudge}"}
            )
    except Exception:  # noqa: BLE001 — nudge is optional; never break the pipeline
        pass

    return WealthResult(recommendation=recommendation, source=source)


__all__ = [
    "SYSTEM_PROMPT",
    "IncomeSignal",
    "assess_income",
    "resolve_sharia_only",
    "effective_risk_profile",
    "score_fund",
    "rank_funds",
    "run_wealth",
    "WealthResult",
]
