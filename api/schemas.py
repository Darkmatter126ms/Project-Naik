"""Naik — canonical data contracts (SOURCE OF TRUTH).

Every agent (diagnostic, wealth, insurance, compliance) and every surface (Flask
API, Next.js web, Streamlit, the eval harness) imports its types from this
module. The eight top-level models below are the contract between subsystems:

    Transaction            -> one anonymised Shopee ledger entry
    DiagnosticInput        -> everything the diagnostic agent ingests
    WellnessVector         -> the diagnostic agent's seven-dimension output
    FundPick               -> one OJK-licensed reksa dana candidate
    WealthRecommendation   -> the wealth agent's ranked output
    InsuranceQuote         -> the insurance agent's parametric micro-cover
    ComplianceVerdict      -> the compliance agent's gate decision
    FinalResponse          -> the assembled, user-facing payload

The seven-dimension wellness model is ported from the Wealth-Wellness-Hub
project (diversification, liquidity, growth, risk_management, tax_efficiency,
emergency_fund) and extended here with `behavioural_resilience`. The domain is
re-pointed from Singapore (CPF/SRS/SGD) to Indonesia (OJK/reksa dana/IDR).

DESIGN RULES (do not break without telling the team):
  * Field names here are frozen. Renaming a field is an API break for four
    agents and three frontends at once.
  * Money is whole-rupiah ``int`` (the rupiah has no practical sub-unit), never
    float, to avoid accumulation error on large balances.
  * Wellness scores are floats in [0, 100].
  * ``extra="forbid"`` everywhere: a typo'd field name fails loudly at the
    boundary instead of silently vanishing.
  * Validators encode guardrails the product cannot ship without: priority_gap
    must match the true minimum dimension; funds must be OJK-licensed; a
    premium may never exceed the single-event payout it buys.

Pydantic v2 only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

__all__ = [
    # enums / value types
    "TransactionDirection",
    "TransactionCategory",
    "RiskProfile",
    "WellnessDimension",
    "FundType",
    "FundRiskLevel",
    "PremiumFrequency",
    "TriggerMetric",
    "ComplianceStatus",
    "NextStep",
    "ParametricTrigger",
    # the eight core contracts
    "Transaction",
    "DiagnosticInput",
    "WellnessVector",
    "FundPick",
    "WealthRecommendation",
    "InsuranceQuote",
    "ComplianceVerdict",
    "FinalResponse",
]

SCHEMA_VERSION = "1.0.0"

# --------------------------------------------------------------------------- #
# Reusable constrained scalar types                                           #
# --------------------------------------------------------------------------- #

#: A wellness score, bounded to the 0–100 range used across the radar UI.
Score = Annotated[float, Field(ge=0.0, le=100.0)]

#: A non-negative amount in whole Indonesian rupiah (balances, payouts, premia).
RupiahAmount = Annotated[int, Field(ge=0, description="Whole Indonesian rupiah, >= 0.")]

#: A probability / ratio in [0, 1].
UnitInterval = Annotated[float, Field(ge=0.0, le=1.0)]


def _utc_now() -> datetime:
    """Timezone-aware UTC timestamp factory (naive datetimes are a known foot-gun)."""
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enumerations                                                                #
# --------------------------------------------------------------------------- #


class TransactionDirection(str, Enum):
    """Money flow relative to the user."""

    DEBIT = "debit"  # money out  (a purchase / payment)
    CREDIT = "credit"  # money in   (income / refund / payout)


class TransactionCategory(str, Enum):
    """Coarse spend/income taxonomy derived from anonymised Shopee data.

    Kept deliberately small; ``OTHER`` is the catch-all so unseen merchant
    categories never break ingestion.
    """

    FOOD_BEVERAGE = "food_beverage"
    GROCERIES = "groceries"
    TRANSPORT = "transport"
    UTILITIES_BILLS = "utilities_bills"
    SHOPPING = "shopping"
    ENTERTAINMENT = "entertainment"
    HEALTH = "health"
    EDUCATION = "education"
    INVESTMENT = "investment"
    INSURANCE = "insurance"
    LOAN_REPAYMENT = "loan_repayment"  # e.g. SPayLater instalments
    INCOME = "income"
    TRANSFER = "transfer"
    OTHER = "other"


class RiskProfile(str, Enum):
    """Self-declared risk tolerance, mirroring Bibit's three-tier profile.

    The diagnostic agent maps this to a CRRA relative-risk-aversion coefficient
    (gamma) when computing utility weights (see /naik_agents/diagnostic.py).
    """

    CONSERVATIVE = "conservative"  # Konservatif
    MODERATE = "moderate"  # Moderat
    AGGRESSIVE = "aggressive"  # Agresif


class WellnessDimension(str, Enum):
    """The seven wellness dimensions.

    Each value equals the corresponding ``WellnessVector`` field name exactly,
    so ``priority_gap.value`` is always a valid attribute name on the vector.
    """

    DIVERSIFICATION = "diversification"
    LIQUIDITY = "liquidity"
    GROWTH = "growth"
    RISK_MANAGEMENT = "risk_management"
    TAX_EFFICIENCY = "tax_efficiency"
    EMERGENCY_FUND = "emergency_fund"
    BEHAVIOURAL_RESILIENCE = "behavioural_resilience"


class FundType(str, Enum):
    """Indonesian reksa dana (mutual fund) categories."""

    MONEY_MARKET = "pasar_uang"  # Reksa Dana Pasar Uang
    FIXED_INCOME = "pendapatan_tetap"  # Reksa Dana Pendapatan Tetap
    BALANCED = "campuran"  # Reksa Dana Campuran
    EQUITY = "saham"  # Reksa Dana Saham
    INDEX = "indeks"  # Reksa Dana Indeks


class FundRiskLevel(str, Enum):
    """Fund-level risk tier, alignable with the user's RiskProfile."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PremiumFrequency(str, Enum):
    """Billing cadence for an insurance premium."""

    MONTHLY = "monthly"
    ANNUAL = "annual"
    PER_TERM = "per_term"  # single up-front premium for the whole coverage term


class TriggerMetric(str, Enum):
    """Observable BMKG quantity that fires a parametric payout."""

    RAINFALL_MM = "rainfall_mm"
    WIND_SPEED_KMH = "wind_speed_kmh"


class ComplianceStatus(str, Enum):
    """Outcome of the compliance gate."""

    APPROVED = "approved"
    APPROVED_WITH_CONDITIONS = "approved_with_conditions"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    REJECTED = "rejected"


class NextStep(str, Enum):
    """The single action surfaced to the user after the pipeline runs."""

    CONFIRM_INVESTMENT = "confirm_investment"
    CONFIRM_INSURANCE = "confirm_insurance"
    CONFIRM_BOTH = "confirm_both"
    REVIEW_ONLY = "review_only"  # informational; nothing to transact
    ESCALATE_TO_HUMAN = "escalate_to_human"


# Canonical ordering of the seven dimensions. Used for deterministic tie-breaks
# when several dimensions share the minimum score.
DIMENSION_ORDER: tuple[WellnessDimension, ...] = (
    WellnessDimension.DIVERSIFICATION,
    WellnessDimension.LIQUIDITY,
    WellnessDimension.GROWTH,
    WellnessDimension.RISK_MANAGEMENT,
    WellnessDimension.TAX_EFFICIENCY,
    WellnessDimension.EMERGENCY_FUND,
    WellnessDimension.BEHAVIOURAL_RESILIENCE,
)

# Float tolerance for "is this the minimum?" comparisons.
_SCORE_EPS = 1e-6


class _Base(BaseModel):
    """Shared config for every Naik model.

    * ``extra="forbid"`` — unknown fields raise, catching typos at the boundary.
    * ``validate_assignment=True`` — mutation after construction is re-validated.
    * ``str_strip_whitespace=True`` — trims accidental whitespace in IDs/text.
    * ``use_enum_values=False`` — keep rich Enum members in-process; JSON dumps
      still serialise to the string value.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        use_enum_values=False,
    )

    @model_validator(mode="before")
    @classmethod
    def _drop_computed_fields_on_input(cls, data: object) -> object:
        """Let serialised output round-trip back in under ``extra="forbid"``.

        Computed fields (e.g. ``overall_score``, ``signed_amount_idr``) are
        emitted by ``model_dump``/``model_dump_json`` but are not constructor
        inputs. Without this, a dump-then-load cycle — exactly what happens when
        a payload is persisted to Postgres JSONB and reloaded — would trip the
        ``extra_forbidden`` guard. We strip only the keys that are genuinely
        computed fields of this model; any other unknown key still raises.
        """
        computed = getattr(cls, "model_computed_fields", None)
        if isinstance(data, dict) and computed:
            present = computed.keys() & data.keys()
            if present:
                data = {k: v for k, v in data.items() if k not in present}
        return data


# --------------------------------------------------------------------------- #
# 1. Transaction                                                              #
# --------------------------------------------------------------------------- #


class Transaction(_Base):
    """One anonymised Shopee ledger entry.

    The transaction stream is the behavioural substrate for the whole pipeline:
    the diagnostic agent reads it for spend/save patterns, and the insurance
    agent infers daily-earnings velocity (and thus payout sizing) from the
    ``CREDIT`` / ``INCOME`` rows.
    """

    transaction_id: str = Field(..., description="Opaque, anonymised entry id.")
    timestamp: datetime = Field(..., description="When the transaction occurred (tz-aware preferred).")
    amount_idr: Annotated[int, Field(gt=0)] = Field(
        ..., description="Absolute value in whole rupiah; sign is carried by `direction`."
    )
    direction: TransactionDirection = Field(..., description="DEBIT = money out, CREDIT = money in.")
    category: TransactionCategory = Field(
        TransactionCategory.OTHER, description="Coarse spend/income category."
    )
    description: Optional[str] = Field(None, description="Optional free-text memo (anonymised).")
    merchant: Optional[str] = Field(None, description="Optional anonymised merchant label.")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def signed_amount_idr(self) -> int:
        """Signed amount: positive for CREDIT, negative for DEBIT.

        Convenience for cash-flow aggregation so callers don't re-derive the sign.
        """
        return self.amount_idr if self.direction is TransactionDirection.CREDIT else -self.amount_idr


# --------------------------------------------------------------------------- #
# 2. DiagnosticInput                                                          #
# --------------------------------------------------------------------------- #


class DiagnosticInput(_Base):
    """Everything the diagnostic agent ingests for one user.

    Combines the structured profile, the anonymised transaction history, and the
    90-second Bahasa Indonesia voice transcript from the Realtime API intake. At
    least one behavioural signal (a non-empty transcript OR at least one
    transaction) must be present — scoring a user from nothing is a do-no-harm
    violation, so it fails fast here.
    """

    user_id: str = Field(..., description="Stable pseudonymous user identifier.")
    locale: str = Field("id-ID", description="BCP-47 locale; defaults to Indonesian.")

    age: int = Field(..., ge=17, le=100, description="User age in years (17+ per OJK).")
    monthly_income_idr: RupiahAmount = Field(..., description="Self-reported gross monthly income.")
    kecamatan: str = Field(..., description="District (kecamatan) — keys flood risk and the parametric trigger.")
    city: Optional[str] = Field(None, description="City / kota, e.g. 'Jakarta'.")

    risk_tolerance: RiskProfile = Field(..., description="Self-declared risk profile; maps to CRRA gamma.")
    household_size: int = Field(1, ge=1, description="People dependent on this income, incl. the user.")
    is_gig_worker: bool = Field(
        False, description="True for gig/informal income; raises modelled income volatility."
    )
    investment_horizon_years: Optional[float] = Field(
        None, ge=0.0, description="Goal horizon in years, if known; feeds fund ranking."
    )
    existing_holdings_idr: Optional[int] = Field(
        None, ge=0, description="Current invested balance (e.g. the one ghosted Bibit fund)."
    )

    financial_goals: list[str] = Field(
        default_factory=list,
        description="Free-text goals in Bahasa, e.g. ['dana darurat', 'beli rumah'].",
    )
    voice_transcript: str = Field(
        "", description="Bahasa Indonesia transcript from the Realtime API voice intake."
    )
    transactions: list[Transaction] = Field(
        default_factory=list, description="Anonymised Shopee transaction history."
    )

    @model_validator(mode="after")
    def _require_a_signal(self) -> "DiagnosticInput":
        """Refuse to diagnose with no behavioural signal at all."""
        if not self.voice_transcript.strip() and not self.transactions:
            raise ValueError(
                "DiagnosticInput needs at least one signal: a non-empty "
                "voice_transcript or at least one transaction."
            )
        return self


# --------------------------------------------------------------------------- #
# 3. WellnessVector                                                           #
# --------------------------------------------------------------------------- #


class WellnessVector(_Base):
    """The diagnostic agent's seven-dimension financial-wellness output.

    Each dimension is a float in [0, 100] (higher is healthier). ``priority_gap``
    names the single weakest dimension — the gap Naik steers the user to close
    first. An ``@model_validator`` guarantees ``priority_gap`` actually IS the
    minimum-scoring dimension, so downstream agents can trust it blindly.

    Prefer :meth:`from_scores` to construct: it computes ``priority_gap`` for you
    with a deterministic tie-break (canonical dimension order).
    """

    diversification: Score = Field(..., description="Spread across asset types / fund categories.")
    liquidity: Score = Field(..., description="Share of readily-accessible cash.")
    growth: Score = Field(..., description="Exposure to return-seeking (equity-like) assets.")
    risk_management: Score = Field(..., description="Coverage against downside / protection adequacy.")
    tax_efficiency: Score = Field(..., description="Use of tax-advantaged vehicles where available.")
    emergency_fund: Score = Field(..., description="Months of expenses held in reserve.")
    behavioural_resilience: Score = Field(
        ..., description="Consistency / discipline of saving & investing behaviour."
    )

    priority_gap: WellnessDimension = Field(
        ..., description="The lowest-scoring dimension — the first gap to close."
    )
    rationale: Optional[str] = Field(
        None, description="Short Bahasa explanation of the priority gap (agent-authored)."
    )

    def _scores_by_dimension(self) -> dict[WellnessDimension, float]:
        """Map each dimension enum to its current score."""
        return {dim: getattr(self, dim.value) for dim in DIMENSION_ORDER}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def overall_score(self) -> float:
        """Unweighted mean of the seven dimensions, rounded to 1 dp (UI headline)."""
        scores = self._scores_by_dimension().values()
        return round(sum(scores) / len(DIMENSION_ORDER), 1)

    @classmethod
    def _argmin_dimension(cls, scores: dict[WellnessDimension, float]) -> WellnessDimension:
        """Lowest-scoring dimension; ties broken by canonical DIMENSION_ORDER."""
        lowest = min(scores.values())
        for dim in DIMENSION_ORDER:  # deterministic order => stable tie-break
            if abs(scores[dim] - lowest) <= _SCORE_EPS:
                return dim
        return DIMENSION_ORDER[0]  # unreachable; satisfies the type checker

    @classmethod
    def from_scores(
        cls,
        *,
        diversification: float,
        liquidity: float,
        growth: float,
        risk_management: float,
        tax_efficiency: float,
        emergency_fund: float,
        behavioural_resilience: float,
        rationale: Optional[str] = None,
    ) -> "WellnessVector":
        """Build a vector and derive ``priority_gap`` from the scores.

        This is the preferred constructor: the diagnostic agent emits seven
        numbers and lets the schema name the gap, eliminating any chance of the
        label disagreeing with the data.
        """
        scores = {
            WellnessDimension.DIVERSIFICATION: diversification,
            WellnessDimension.LIQUIDITY: liquidity,
            WellnessDimension.GROWTH: growth,
            WellnessDimension.RISK_MANAGEMENT: risk_management,
            WellnessDimension.TAX_EFFICIENCY: tax_efficiency,
            WellnessDimension.EMERGENCY_FUND: emergency_fund,
            WellnessDimension.BEHAVIOURAL_RESILIENCE: behavioural_resilience,
        }
        return cls(
            diversification=diversification,
            liquidity=liquidity,
            growth=growth,
            risk_management=risk_management,
            tax_efficiency=tax_efficiency,
            emergency_fund=emergency_fund,
            behavioural_resilience=behavioural_resilience,
            priority_gap=cls._argmin_dimension(scores),
            rationale=rationale,
        )

    @model_validator(mode="after")
    def _priority_gap_is_the_minimum(self) -> "WellnessVector":
        """Guarantee the declared priority_gap is genuinely the weakest dimension."""
        scores = self._scores_by_dimension()
        lowest = min(scores.values())
        if scores[self.priority_gap] - lowest > _SCORE_EPS:
            true_gap = self._argmin_dimension(scores)
            raise ValueError(
                f"priority_gap={self.priority_gap.value!r} scores "
                f"{scores[self.priority_gap]:.4f}, but the minimum is "
                f"{lowest:.4f} at {true_gap.value!r}. priority_gap must name a "
                f"lowest-scoring dimension."
            )
        return self


# --------------------------------------------------------------------------- #
# 4. FundPick                                                                 #
# --------------------------------------------------------------------------- #


class FundPick(_Base):
    """One OJK-licensed reksa dana candidate scored against the user.

    Sourced from the (stubbed, for the timebox) Bibit fund-list tool. The
    ``is_ojk_licensed`` invariant is a hard guardrail: Naik must never surface an
    unlicensed fund, so construction fails if it is ever False.
    """

    fund_id: str = Field(..., description="Stable fund identifier from the fund-list tool.")
    fund_name: str = Field(..., description="Display name of the fund.")
    fund_type: FundType = Field(..., description="Reksa dana category.")
    manager: str = Field(..., description="Manajer Investasi (fund manager) name.")
    risk_level: FundRiskLevel = Field(..., description="Fund-level risk tier.")

    expense_ratio_pct: float = Field(
        ..., ge=0.0, le=10.0, description="Annual management fee, percent of AUM."
    )
    return_1y_pct: Optional[float] = Field(
        None, description="Trailing 1-year return, percent (may be negative)."
    )
    return_3y_annualised_pct: Optional[float] = Field(
        None, description="Trailing 3-year annualised return, percent (may be negative)."
    )
    aum_idr: Optional[int] = Field(None, ge=0, description="Assets under management, rupiah.")
    min_investment_idr: RupiahAmount = Field(..., description="Minimum initial investment, rupiah.")

    is_ojk_licensed: bool = Field(True, description="Must be True — Naik surfaces licensed funds only.")
    is_sharia: bool = Field(False, description="True for syariah-compliant funds.")

    match_score: Score = Field(..., description="How well this fund fits the user (0–100).")
    rationale: Optional[str] = Field(None, description="Bahasa explanation of the fit (agent-authored).")

    @field_validator("is_ojk_licensed")
    @classmethod
    def _must_be_licensed(cls, value: bool) -> bool:
        """Hard refusal: never represent an unlicensed fund as a pick."""
        if value is not True:
            raise ValueError("FundPick.is_ojk_licensed must be True; unlicensed funds are not allowed.")
        return value


# --------------------------------------------------------------------------- #
# 5. WealthRecommendation                                                     #
# --------------------------------------------------------------------------- #


class WealthRecommendation(_Base):
    """The wealth agent's ranked output for one user.

    ``picks`` is ordered best-first. The optional ``allocation_pct`` lets the
    agent propose how to split a contribution across the picks; when present it
    must align one-to-one with ``picks`` and sum to ~100%.
    """

    user_id: str = Field(..., description="User this recommendation is for.")
    generated_at: datetime = Field(default_factory=_utc_now, description="Generation timestamp (UTC).")

    risk_profile_used: RiskProfile = Field(..., description="Risk profile the ranking assumed.")
    investment_horizon_years: float = Field(..., ge=0.0, description="Horizon the ranking optimised for.")
    recommended_monthly_contribution_idr: RupiahAmount = Field(
        ..., description="Suggested monthly top-up, rupiah."
    )
    target_amount_idr: Optional[int] = Field(None, ge=0, description="Goal target amount, if any.")

    picks: list[FundPick] = Field(..., min_length=1, description="Ranked fund picks, best-first.")
    allocation_pct: Optional[list[Annotated[float, Field(ge=0.0, le=100.0)]]] = Field(
        None, description="Optional split across picks (parallel to `picks`), summing to ~100."
    )
    rationale: str = Field(..., description="Bahasa summary of the recommendation.")

    @model_validator(mode="after")
    def _validate_allocation(self) -> "WealthRecommendation":
        """If an allocation is given, it must align with picks and sum to ~100%."""
        if self.allocation_pct is None:
            return self
        if len(self.allocation_pct) != len(self.picks):
            raise ValueError(
                f"allocation_pct has {len(self.allocation_pct)} entries but there "
                f"are {len(self.picks)} picks; they must align one-to-one."
            )
        total = sum(self.allocation_pct)
        if abs(total - 100.0) > 0.5:  # half-a-point tolerance for rounding
            raise ValueError(f"allocation_pct must sum to ~100 (got {total:.2f}).")
        return self


# --------------------------------------------------------------------------- #
# 6. InsuranceQuote (+ ParametricTrigger)                                     #
# --------------------------------------------------------------------------- #


class ParametricTrigger(_Base):
    """The objective, observable condition that fires a parametric payout.

    Parametric cover pays on a measured index crossing a threshold — no loss
    adjustment, no claim form. For Naik that index is a BMKG weather reading at
    the user's kecamatan.
    """

    metric: TriggerMetric = Field(..., description="Observed quantity (rainfall or wind speed).")
    threshold: float = Field(..., gt=0.0, description="Value at/above which the cover pays.")
    unit: str = Field(..., description="Human-readable unit, e.g. 'mm/24h' or 'km/h'.")
    kecamatan: str = Field(..., description="District whose reading is monitored.")
    observation_window_hours: int = Field(24, ge=1, description="Window over which the metric is measured.")
    data_source: str = Field("BMKG", description="Source of the weather observation.")


class InsuranceQuote(_Base):
    """The insurance agent's parametric income-protection micro-cover.

    Fills the gap MoneeInsure's SiProPer leaves open: SiProPer covers flood
    damage to insured *devices*, but not the user's *lost daily earnings* when a
    flood keeps her off the road. Payout sizes to a configurable multiple of the
    daily earnings inferred from Shopee transaction velocity; the premium is
    priced by the Tweedie GLM (see /naik_agents/pricing).

    Guardrail: a premium may never exceed the single-event payout it buys.
    """

    quote_id: str = Field(..., description="Stable quote identifier.")
    user_id: str = Field(..., description="User this quote is for.")
    generated_at: datetime = Field(default_factory=_utc_now, description="Generation timestamp (UTC).")
    product_name: str = Field("Naik Income Shield", description="Product display name.")

    trigger: ParametricTrigger = Field(..., description="The parametric trigger condition.")

    estimated_daily_earnings_idr: RupiahAmount = Field(
        ..., description="Daily earnings inferred from transaction velocity."
    )
    payout_multiple: float = Field(..., gt=0.0, description="Payout = daily earnings × this multiple.")
    payout_per_event_idr: RupiahAmount = Field(..., description="Rupiah paid per triggering event.")
    max_payouts_per_term: int = Field(1, ge=1, description="Cap on payouts within the coverage term.")

    coverage_term_days: int = Field(..., ge=1, description="Length of cover, days.")
    premium_idr: RupiahAmount = Field(..., description="Premium for the term/cadence below.")
    premium_frequency: PremiumFrequency = Field(..., description="Billing cadence for the premium.")

    expected_annual_loss_idr: RupiahAmount = Field(
        ..., description="GLM mean predicted annual income loss (actuarial transparency)."
    )
    loss_ratio_estimate: Optional[UnitInterval] = Field(
        None, description="Expected-loss / expected-premium, if computed."
    )

    @model_validator(mode="after")
    def _premium_below_payout(self) -> "InsuranceQuote":
        """A single event must pay strictly more than its premium costs."""
        if self.premium_idr >= self.payout_per_event_idr:
            raise ValueError(
                f"premium_idr ({self.premium_idr}) must be strictly less than "
                f"payout_per_event_idr ({self.payout_per_event_idr}); a policy that "
                f"costs more than it can pay is mis-sold."
            )
        return self


# --------------------------------------------------------------------------- #
# 7. ComplianceVerdict                                                        #
# --------------------------------------------------------------------------- #


class ComplianceVerdict(_Base):
    """The compliance agent's gate decision over the upstream outputs.

    Every Naik output is framed as *general guidance* under OJK rules, not
    individualised advice, and any transaction is routed to a human-confirmed
    step. ``is_general_guidance`` is therefore an enforced invariant, and at
    least one disclaimer must always be present.
    """

    verdict_id: str = Field(..., description="Stable verdict identifier.")
    status: ComplianceStatus = Field(..., description="Gate outcome.")
    is_general_guidance: bool = Field(
        True, description="Must be True — outputs are general guidance, not personalised advice."
    )
    requires_human_confirmation: bool = Field(
        True, description="Whether a human-confirmed step gates any transaction."
    )
    reviewed: list[str] = Field(
        default_factory=list,
        description="Which outputs were reviewed, e.g. ['wellness', 'wealth', 'insurance'].",
    )
    flags: list[str] = Field(
        default_factory=list,
        description="Raised concerns, e.g. ['affordability_concern', 'risk_mismatch'].",
    )
    disclaimers: list[str] = Field(
        ..., min_length=1, description="Bahasa disclaimers to surface (at least one required)."
    )
    rationale: str = Field(..., description="Bahasa explanation of the verdict.")

    @field_validator("is_general_guidance")
    @classmethod
    def _must_be_general_guidance(cls, value: bool) -> bool:
        """Hard invariant: Naik never represents output as personalised advice."""
        if value is not True:
            raise ValueError("ComplianceVerdict.is_general_guidance must be True under OJK framing.")
        return value


# --------------------------------------------------------------------------- #
# 8. FinalResponse                                                            #
# --------------------------------------------------------------------------- #


class FinalResponse(_Base):
    """The assembled, user-facing payload returned by the pipeline.

    Bundles the diagnostic vector, the optional wealth and insurance outputs, the
    compliance verdict, a Bahasa narrative, and the single ``next_step`` to show
    the user. Cross-field validators ensure the action and the attached artefacts
    agree (you cannot ask the user to confirm an investment that isn't attached).
    """

    request_id: str = Field(..., description="Correlation id for this pipeline run.")
    user_id: str = Field(..., description="User this response is for.")
    generated_at: datetime = Field(default_factory=_utc_now, description="Assembly timestamp (UTC).")
    language: str = Field("id", description="Language of the user-facing text (Bahasa Indonesia).")

    wellness: WellnessVector = Field(..., description="Diagnostic output (always present).")
    wealth: Optional[WealthRecommendation] = Field(None, description="Wealth recommendation, if any.")
    insurance: Optional[InsuranceQuote] = Field(None, description="Insurance quote, if any.")
    insurance_skip_reason: Optional[str] = Field(
        None,
        description=(
            "When `insurance` is None, distinguishes a deliberate skip "
            "(e.g. 'low_risk', 'already_insured') from an agent failure (None). "
            "The frontend uses this to show an informative 'optional cover' card "
            "instead of an error state. The human-readable explanation is in "
            "`narrative`."
        ),
    )
    compliance: ComplianceVerdict = Field(..., description="Compliance gate decision (always present).")

    narrative: str = Field(..., description="User-facing Bahasa summary of the guidance.")
    next_step: NextStep = Field(..., description="The single action surfaced to the user.")
    disclaimers: list[str] = Field(
        ..., min_length=1, description="Disclaimers surfaced to the user (at least one)."
    )

    @model_validator(mode="after")
    def _action_matches_attachments(self) -> "FinalResponse":
        """The next_step must be backed by the artefacts it references."""
        needs_wealth = self.next_step in (NextStep.CONFIRM_INVESTMENT, NextStep.CONFIRM_BOTH)
        needs_insurance = self.next_step in (NextStep.CONFIRM_INSURANCE, NextStep.CONFIRM_BOTH)
        if needs_wealth and self.wealth is None:
            raise ValueError(f"next_step={self.next_step.value!r} requires a `wealth` recommendation.")
        if needs_insurance and self.insurance is None:
            raise ValueError(f"next_step={self.next_step.value!r} requires an `insurance` quote.")
        return self


# ── Issuance schemas ──────────────────────────────────────────────────────────


class PersonaIdentity(_Base):
    """Minimal identity fields the frontend forwards from DiagnosticInput.

    The results page reads these from ``sessionStorage('naik_persona_input')``
    and bundles them with the ``InsuranceQuote`` into an ``IssuanceRequest``.
    The backend uses them to fill the applicant section of the admin form —
    fields that are not carried on the InsuranceQuote itself.
    """

    user_id: str = Field(..., description="Stable pseudonymous identifier (e.g. 'sari').")
    applicant_name: Optional[str] = Field(
        None,
        description="Display name; defaults to user_id.title() if omitted.",
    )
    age: int = Field(..., ge=17, le=100)
    monthly_income_idr: RupiahAmount
    kecamatan: str
    is_gig_worker: bool = False
    risk_tolerance: RiskProfile = RiskProfile.MODERATE
    household_size: int = Field(1, ge=1)


class IssuanceRequest(_Base):
    """Request body for ``POST /issue``.

    The frontend sends the ``InsuranceQuote`` it already has (from
    ``/orchestrate``) plus the persona identity fields it stored in
    ``sessionStorage('naik_persona_input')``.  The backend issues the policy
    via the Playwright driver without re-running the full pipeline.
    """

    quote: InsuranceQuote
    persona: PersonaIdentity


class IssuanceResponse(_Base):
    """Response from ``POST /issue``.

    ``form_data`` is the exact dict of field-id → value that was filled into
    the admin form — the frontend uses it to animate the same fill in the
    iframe so judges see the form populating in real time.  ``issuance`` is the
    result record written by the Playwright driver (polis_id, status, etc.).
    """

    form_data: dict[str, str] = Field(
        ..., description="Exact field values filled into the MoneeInsure admin form."
    )
    issuance: dict[str, Any] = Field(
        ..., description="Issuance result from the Playwright driver."
    )
