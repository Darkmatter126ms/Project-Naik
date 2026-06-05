"""Naik insurance agent.

Prices a parametric income-protection micro-cover and emits a validated
:class:`InsuranceQuote`. It consumes the diagnostic agent's
:class:`WellnessVector` and the user's :class:`DiagnosticInput`, and calls the
``price_income_shock_cover`` tool (which loads the Tweedie GLM), plus
``check_trigger_frequency`` / ``get_bmkg_history`` for the BMKG-backed trigger.

The product wedge — stated explicitly to the model and woven into the Bahasa
copy — is *complementarity*, not competition:

    MoneeInsure's SiProPer already covers physical damage to insured *devices*
    from typhoon and flood. Naik Income Shield covers something SiProPer does
    NOT: the daily *earnings a user loses* when a flood keeps her off the road.
    Different gap, same customer — the products sit side by side.

The trigger is objective and parametric: a BMKG reading at the user's kecamatan
crossing a threshold (rainfall >= 150 mm/24h OR wind >= 60 km/h) pays out
automatically — no loss adjustment, no claim form. The payout sizes to a
multiple of daily earnings inferred from Shopee transaction velocity.

Two execution paths, same output contract (mirrors :mod:`naik_agents.wealth`):

* **Heuristic path** (default; used when no ``OPENAI_API_KEY`` is set — offline
  dev, CI, flaky-wifi demo): infers weekly income from transaction velocity,
  prices the cover via ``price_income_shock_cover``, reads the historical
  trigger frequency, and writes the Bahasa description from templates. Fully
  reproducible.
* **Model path** (when a key is present): runs a genuine tool-calling loop so the
  model invokes ``price_income_shock_cover`` / ``check_trigger_frequency``, THEN
  we assemble the quote deterministically from the tool output and let the model
  author the plain-Bahasa description (trigger + payout + SiProPer framing).

As in the wealth agent, every number is computed deterministically in Python so
the quote is auditable and reproducible; the model only ever adds the
natural-language layer, and a model hiccup falls back to templated Bahasa and
never breaks the pipeline.

Note on the schema: :class:`InsuranceQuote` is pure structured data and carries
no free-text field, so the plain-Bahasa description rides on
:class:`InsuranceResult` and is surfaced by the orchestrator in
``FinalResponse.narrative``.
"""

from __future__ import annotations

import os
import statistics
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel

try:  # deployed import style
    from api.schemas import (
        DiagnosticInput,
        InsuranceQuote,
        ParametricTrigger,
        PremiumFrequency,
        TransactionCategory,
        TransactionDirection,
        TriggerMetric,
        WellnessVector,
    )
    from naik_agents.tools import (
        AGENTS_SDK_AVAILABLE,
        INSURANCE_TOOLS,
        check_trigger_frequency,
        get_bmkg_history,
        price_income_shock_cover,
    )
except ImportError:  # pragma: no cover - script/direct execution fallback
    import sys

    _HERE = os.path.dirname(__file__)
    sys.path.insert(0, os.path.join(_HERE, ".."))
    sys.path.insert(0, os.path.join(_HERE, "..", "api"))
    from schemas import (  # type: ignore
        DiagnosticInput,
        InsuranceQuote,
        ParametricTrigger,
        PremiumFrequency,
        TransactionCategory,
        TransactionDirection,
        TriggerMetric,
        WellnessVector,
    )
    from tools import (  # type: ignore
        AGENTS_SDK_AVAILABLE,
        INSURANCE_TOOLS,
        check_trigger_frequency,
        get_bmkg_history,
        price_income_shock_cover,
    )

DEFAULT_MODEL = os.environ.get("NAIK_INSURANCE_MODEL", "gpt-5.5")

# --------------------------------------------------------------------------- #
# Product constants                                                           #
# --------------------------------------------------------------------------- #

# Parametric trigger thresholds. These match the BMKG fixture's calibration and
# the build plan. The product fires on EITHER index (rainfall OR wind); the
# structured ParametricTrigger schema holds a single metric, so we surface
# rainfall (the dominant flood driver) there and describe the full OR condition
# in the Bahasa copy and the historical-frequency stat.
RAINFALL_TRIGGER_MM = 150.0
WIND_TRIGGER_KMH = 60.0
TRIGGER_WINDOW_HOURS = 24

# Cover shape. A rainy-season quarter, billed monthly to match gig-worker
# cashflow; a flood-prone quarter can plausibly trigger more than once.
COVERAGE_TERM_DAYS = 90
MAX_PAYOUTS_PER_TERM = 3
WORKING_DAYS_PER_WEEK = 6
_WEEKS_PER_MONTH = 52.0 / 12.0  # 4.333…
_WEEKS_PER_YEAR = 52.0

PRODUCT_NAME = "Naik Income Shield"

# --------------------------------------------------------------------------- #
# System prompt (model path)                                                  #
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """\
You are Naik's insurance agent for the Indonesian market. You quote a parametric
income-protection micro-cover for gig and informal workers and explain it in
warm, plain Bahasa Indonesia.

The product — "Naik Income Shield":
- Pays automatically when an objective BMKG weather index at the user's
  kecamatan crosses a threshold (rainfall >= 150 mm in 24h OR wind >= 60 km/h).
  No claim form, no loss adjustment — the payout is parametric.
- Pays a multiple of the user's daily earnings (inferred from Shopee
  transaction velocity) per triggering event, to replace income lost while a
  flood keeps them from working.

CRITICAL FRAMING — complementarity, not competition:
MoneeInsure's SiProPer already covers physical damage to insured DEVICES from
typhoon and flood. This product covers something SiProPer does NOT: the income a
user loses when a flood prevents her from working. Always frame Naik Income
Shield as COMPLEMENTARY to SiProPer — it fills a gap SiProPer leaves open, it
does not replace or compete with it.

Rules:
- This is general guidance, not individualised financial advice.
- Be concrete and honest: name the kecamatan, the threshold, how often it has
  historically fired, the weekly premium, and the payout in days of income.
- Never promise the trigger will or won't fire; describe historical frequency.
- Write for someone with limited financial jargon. One tight, warm paragraph.
"""

# --------------------------------------------------------------------------- #
# Income-velocity inference (the Shopee wedge)                                #
# --------------------------------------------------------------------------- #


# Minimum span of observed income events before a *weekly* rate is measurable.
# Income clustered into a window shorter than this can't tell "paid daily" from
# "paid in one lump" — the cadence is unobservable, so we defer to self-report.
_MIN_INCOME_SPAN_DAYS = 14


def infer_weekly_income_idr(inp: DiagnosticInput) -> int:
    """Infer weekly income from Shopee transaction velocity, anchored to income.

    The build plan sizes the payout to "daily earnings inferred from Shopee
    transaction velocity". We estimate the weekly rate from the cadence of
    income inflows: each income event covers one inter-arrival interval, so
    weekly = total_income / (n_events × median_gap_days) × 7. For regular pay
    this is exact (it does not suffer the partial-last-period bias of a naive
    span-based rate); the median gap keeps it robust to irregular gig pay.

    A finite transaction window cannot always support a weekly-rate estimate, so
    velocity is trusted only when BOTH hold, and otherwise we defer to the
    self-reported income — the reliable external anchor:

    * **Observation span** — income events must span at least two weeks. Events
      clustered into a few days are genuinely ambiguous about weekly income
      (consistent with "paid daily" *and* "paid one lump"); the cadence is
      unobservable, so extrapolating would be guessing.
    * **Plausibility band** — even over a long span, a windfall can inflate the
      rate, so the estimate must land within 0.5×–2× of the reported weekly
      income to be trusted.

    This is signal fusion, not a fallback hack: self-report fixes the income
    *level*; velocity refines it (and detects cadence) when the data can bear it.
    """
    anchor_weekly = max(0, round(inp.monthly_income_idr / _WEEKS_PER_MONTH))

    incomes = sorted(
        (t.timestamp, t.amount_idr)
        for t in inp.transactions
        if t.direction is TransactionDirection.CREDIT
        and t.category is TransactionCategory.INCOME
    )
    if len(incomes) >= 2:
        span_days = (incomes[-1][0] - incomes[0][0]).days
        gaps = [
            (b[0] - a[0]).days
            for a, b in zip(incomes, incomes[1:])
            if (b[0] - a[0]).days > 0
        ]
        if gaps and span_days >= _MIN_INCOME_SPAN_DAYS:
            median_gap = statistics.median(gaps)
            total = sum(amount for _, amount in incomes)
            period_days = len(incomes) * median_gap
            if period_days > 0:
                velocity_weekly = round(total / period_days * 7.0)
                # Secondary sanity bound: reject outlier-inflated rates.
                if anchor_weekly == 0 or 0.5 * anchor_weekly <= velocity_weekly <= 2.0 * anchor_weekly:
                    return max(0, velocity_weekly)
    return anchor_weekly


# --------------------------------------------------------------------------- #
# Trigger frequency                                                           #
# --------------------------------------------------------------------------- #


def trigger_frequency(kecamatan: str) -> float:
    """Historical fraction of weeks the OR trigger would have fired (BMKG fixture)."""
    return check_trigger_frequency(kecamatan, RAINFALL_TRIGGER_MM, WIND_TRIGGER_KMH)


# --------------------------------------------------------------------------- #
# Bahasa templates (heuristic path)                                           #
# --------------------------------------------------------------------------- #


def _weeks_per_year(freq: float) -> int:
    """Historical trigger frequency as a whole number of weeks per year."""
    return int(round(freq * _WEEKS_PER_YEAR))


def _trigger_description_id(kecamatan: str, freq: float) -> str:
    weeks = _weeks_per_year(freq)
    if weeks > 0:
        history = (
            f"secara historis terjadi rata-rata sekitar {weeks} minggu per tahun, "
            f"terutama di musim hujan (November–Maret)"
        )
    else:
        history = "secara historis ambang ini jarang terlampaui di wilayah Anda"
    return (
        f"Perlindungan aktif otomatis saat curah hujan di {kecamatan} mencapai "
        f"{int(RAINFALL_TRIGGER_MM)} mm dalam 24 jam atau kecepatan angin mencapai "
        f"{int(WIND_TRIGGER_KMH)} km/jam (data BMKG) — {history}. Tidak perlu "
        f"mengisi formulir klaim: dana cair otomatis begitu ambang tercapai."
    )


def _payout_description_id(payout_multiple: int, payout_per_event_idr: int) -> str:
    return (
        f"Setiap kejadian membayar sekitar {payout_multiple} hari penghasilan "
        f"(≈ Rp {payout_per_event_idr:,}) untuk menutup pemasukan yang hilang "
        f"selama Anda tidak bisa bekerja."
    )


def _complementary_note_id() -> str:
    return (
        f"{PRODUCT_NAME} melengkapi SiProPer dari MoneeInsure, bukan "
        f"menggantikannya: SiProPer menanggung kerusakan perangkat akibat banjir "
        f"dan topan, sedangkan {PRODUCT_NAME} menanggung penghasilan harian yang "
        f"hilang saat banjir membuat Anda tidak bisa bekerja — risiko yang belum "
        f"dilindungi SiProPer."
    )


def _premium_description_id(
    weekly_premium_idr: int, monthly_premium_idr: int, payout_per_event_idr: int
) -> str:
    ratio = round(payout_per_event_idr / weekly_premium_idr) if weekly_premium_idr > 0 else 0
    return (
        f"Preminya sekitar Rp {weekly_premium_idr:,} per minggu "
        f"(≈ Rp {monthly_premium_idr:,} per bulan) — sekitar {ratio}× lebih kecil dari "
        f"satu kali manfaat yang dibayarkan."
    )


def _bahasa_description_id(
    *,
    kecamatan: str,
    freq: float,
    payout_multiple: int,
    payout_per_event_idr: int,
    weekly_premium_idr: int,
    monthly_premium_idr: int,
) -> str:
    """The full plain-Bahasa description (heuristic path), one coherent block."""
    return " ".join(
        [
            _trigger_description_id(kecamatan, freq),
            _payout_description_id(payout_multiple, payout_per_event_idr),
            _premium_description_id(weekly_premium_idr, monthly_premium_idr, payout_per_event_idr),
            _complementary_note_id(),
        ]
    )


# --------------------------------------------------------------------------- #
# Quote assembly                                                              #
# --------------------------------------------------------------------------- #


def _build_quote(
    inp: DiagnosticInput,
    priced: dict,
    *,
    coverage_term_days: int,
) -> tuple[InsuranceQuote, int]:
    """Assemble a validated InsuranceQuote from the pricing-tool output.

    Returns the quote and the weekly premium (carried separately for the
    "< Rp 50k/week" narrative, since the schema bills monthly).
    """
    weekly_premium = int(priced["weekly_premium_idr"])
    payout_per_event = int(priced["payout_per_event_idr"])
    payout_multiple = int(priced["payout_multiplier"])
    daily_earnings = int(priced["estimated_daily_earnings_idr"])
    loss_ratio = priced.get("loss_ratio_estimate")

    # The schema has no WEEKLY cadence; bill monthly. Cap strictly below the
    # single-event payout to honour the InsuranceQuote guardrail (premium <
    # payout) — for realistic personas the monthly premium is a small fraction
    # of the payout and the cap never binds.
    monthly_premium = round(weekly_premium * _WEEKS_PER_MONTH)
    monthly_premium = max(0, min(monthly_premium, payout_per_event - 1))

    # Expected annual loss for *actuarial transparency*: the GLM's expected
    # weekly loss is on the synthetic training scale and not credible as rupiah,
    # so we surface the expected annual loss the cover actually prices against
    # (premium × loss_ratio, annualised) — consistent with the calibrated
    # premium and the loss_ratio shown.
    if loss_ratio is not None:
        expected_annual_loss = round(weekly_premium * float(loss_ratio) * _WEEKS_PER_YEAR)
    else:  # pragma: no cover - loss_ratio is populated for any positive premium
        expected_annual_loss = int(round(priced.get("expected_annual_loss_idr", 0)))

    trigger = ParametricTrigger(
        metric=TriggerMetric.RAINFALL_MM,
        threshold=RAINFALL_TRIGGER_MM,
        unit="mm/24h",
        kecamatan=inp.kecamatan,
        observation_window_hours=TRIGGER_WINDOW_HOURS,
        data_source="BMKG",
    )

    quote = InsuranceQuote(
        quote_id=f"naik-shield-{inp.user_id}",
        user_id=inp.user_id,
        product_name=PRODUCT_NAME,
        trigger=trigger,
        estimated_daily_earnings_idr=daily_earnings,
        payout_multiple=float(payout_multiple),
        payout_per_event_idr=payout_per_event,
        max_payouts_per_term=MAX_PAYOUTS_PER_TERM,
        coverage_term_days=coverage_term_days,
        premium_idr=monthly_premium,
        premium_frequency=PremiumFrequency.MONTHLY,
        expected_annual_loss_idr=expected_annual_loss,
        loss_ratio_estimate=loss_ratio,
    )
    return quote, weekly_premium


# --------------------------------------------------------------------------- #
# Model path                                                                  #
# --------------------------------------------------------------------------- #

class _InsuranceDescription(BaseModel):
    """Structured output the insurance agent returns: one Bahasa paragraph.

    The SDK enforces this shape via the agent's ``output_type``. Every number in
    the quote is computed deterministically in Python; the model only writes the
    trigger / payout / premium / SiProPer-complementary prose around them.
    """

    bahasa_description: str


def _context_block(inp: DiagnosticInput, quote: InsuranceQuote, weekly_premium_idr: int, freq: float) -> str:
    """Compact, deterministic fact sheet handed to the model for prose only."""
    return (
        f"User: kecamatan {inp.kecamatan}, gig worker: "
        f"{'yes' if inp.is_gig_worker else 'no'}, household {inp.household_size}.\n"
        f"Trigger: rainfall >= {int(RAINFALL_TRIGGER_MM)} mm/24h OR wind >= "
        f"{int(WIND_TRIGGER_KMH)} km/h at {inp.kecamatan} (BMKG); historically "
        f"fired ~{_weeks_per_year(freq)} weeks/year.\n"
        f"Payout: {int(quote.payout_multiple)} days of income "
        f"(Rp {quote.payout_per_event_idr:,}) per event, up to "
        f"{quote.max_payouts_per_term} events over {quote.coverage_term_days} days.\n"
        f"Premium: ~Rp {weekly_premium_idr:,}/week (Rp {quote.premium_idr:,}/month).\n"
        f"Daily earnings (from transaction velocity): "
        f"Rp {quote.estimated_daily_earnings_idr:,}."
    )


def _describe_with_model(
    inp: DiagnosticInput,
    quote: InsuranceQuote,
    weekly_premium_idr: int,
    freq: float,
    *,
    weekly_income_idr: int,
    model: str,
) -> str:
    """Author the Bahasa description via the OpenAI Agents SDK.

    Builds an :class:`Agent` carrying the pricing/frequency tools (so the model
    can exercise the Tweedie GLM, faithful to the plan's "calls
    price_income_shock_cover") and a structured ``output_type``. Every number in
    the quote is already computed deterministically; the agent only writes the
    Bahasa paragraph. Raises on any SDK/parse error so the caller can fall back.
    """
    from agents import Agent, Runner  # lazy: offline/no-SDK runs never reach here

    context = _context_block(inp, quote, weekly_premium_idr, freq)
    instruction = (
        "You may call price_income_shock_cover and check_trigger_frequency for "
        f"kecamatan {inp.kecamatan} (weekly income Rp {weekly_income_idr:,}, "
        f"gig_worker={inp.is_gig_worker}, household_size={inp.household_size}) to "
        "verify the figures. Then, using these confirmed facts (do not change any "
        "number), write the bahasa_description — trigger, historical frequency, "
        "payout in days of income, weekly premium, and the SiProPer-complementary "
        "framing.\n" + context
    )

    agent = Agent(
        name="Naik Insurance",
        instructions=SYSTEM_PROMPT,
        model=model,
        tools=INSURANCE_TOOLS,
        output_type=_InsuranceDescription,
    )
    result = Runner.run_sync(agent, instruction)
    description = str(result.final_output.bahasa_description).strip()
    if not description:
        raise ValueError("model returned an empty bahasa_description")
    return description


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #


@dataclass
class InsuranceResult:
    """Wraps the quote with its plain-Bahasa description and provenance.

    ``bahasa_description`` carries the user-facing copy (InsuranceQuote has no
    free-text field); the orchestrator folds it into FinalResponse.narrative.
    ``weekly_premium_idr`` is kept for the "< Rp 50k/week" narrative since the
    quote itself bills monthly.
    """

    quote: InsuranceQuote
    bahasa_description: str
    source: str  # "model" or "heuristic"
    weekly_premium_idr: int


def run_insurance(
    wellness: WellnessVector,
    inp: DiagnosticInput,
    *,
    model: Optional[str] = None,
    force_heuristic: bool = False,
    coverage_term_days: int = COVERAGE_TERM_DAYS,
) -> InsuranceResult:
    """Price the income-shock cover and return a validated :class:`InsuranceQuote`.

    Args:
        wellness: the diagnostic agent's output (accepted for a uniform agent
            signature and future protection-priority tilting; the quote is
            driven by the GLM, the kecamatan trigger, and transaction velocity).
        inp: the user's intake — kecamatan keys the trigger and flood risk;
            transactions feed the daily-earnings velocity; gig flag and household
            size feed the GLM.
        model: override the model name for the model path.
        force_heuristic: skip the model path even if a key is present (CI/tests).
        coverage_term_days: cover length; defaults to a rainy-season quarter.

    The pricing and the quote are deterministic in every path; the model, when
    available, only authors the Bahasa description. A model error falls back to
    templated Bahasa and never breaks the pipeline.
    """
    weekly_income = infer_weekly_income_idr(inp)
    priced = price_income_shock_cover(
        inp.kecamatan,
        weekly_income,
        gig_worker=inp.is_gig_worker,
        household_size=inp.household_size,
    )
    quote, weekly_premium = _build_quote(inp, priced, coverage_term_days=coverage_term_days)
    freq = trigger_frequency(inp.kecamatan)

    use_model = (
        (not force_heuristic)
        and bool(os.environ.get("OPENAI_API_KEY"))
        and AGENTS_SDK_AVAILABLE
    )
    description: Optional[str] = None
    source = "heuristic"

    if use_model:
        try:
            description = _describe_with_model(
                inp,
                quote,
                weekly_premium,
                freq,
                weekly_income_idr=weekly_income,
                model=model or DEFAULT_MODEL,
            )
            source = "model"
        except Exception:  # noqa: BLE001 - never let a model hiccup break the pipeline
            description, source = None, "heuristic"

    if description is None:
        description = _bahasa_description_id(
            kecamatan=inp.kecamatan,
            freq=freq,
            payout_multiple=int(quote.payout_multiple),
            payout_per_event_idr=quote.payout_per_event_idr,
            weekly_premium_idr=weekly_premium,
            monthly_premium_idr=quote.premium_idr,
        )

    return InsuranceResult(
        quote=quote,
        bahasa_description=description,
        source=source,
        weekly_premium_idr=weekly_premium,
    )


__all__ = [
    "SYSTEM_PROMPT",
    "PRODUCT_NAME",
    "RAINFALL_TRIGGER_MM",
    "WIND_TRIGGER_KMH",
    "COVERAGE_TERM_DAYS",
    "infer_weekly_income_idr",
    "trigger_frequency",
    "run_insurance",
    "InsuranceResult",
]
