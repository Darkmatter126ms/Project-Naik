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

DEFAULT_MODEL = os.environ.get("NAIK_INSURANCE_MODEL", "gpt-4o-mini")


# --------------------------------------------------------------------------- #
# OpenAI client timeout (shared safety net)                                    #
# --------------------------------------------------------------------------- #

_client_timeout_set = False


def _ensure_client_timeout() -> None:
    """Configure the agents SDK's OpenAI client with a hard HTTP timeout.

    The OpenAI SDK defaults to a 600-second timeout. With gunicorn's
    --timeout 120 on Render, a slow model call would kill the worker (→ 502 with
    no CORS headers) long before the SDK gives up. Setting a 15-second client
    timeout + a single retry makes Runner.run_sync fail fast, so the model-path
    try/except can fall back to the heuristic and the request always returns.

    Idempotent: only the first call configures the client.
    """
    global _client_timeout_set
    if _client_timeout_set:
        return
    if not os.environ.get("OPENAI_API_KEY"):
        return
    try:
        from openai import AsyncOpenAI
        from agents import set_default_openai_client

        set_default_openai_client(
            AsyncOpenAI(timeout=8.0, max_retries=1)
        )
        _client_timeout_set = True
    except Exception:  # noqa: BLE001 - never let client config break the pipeline
        pass


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

    # ── Zero-income guard ───────────────────────────────────────────────────
    # When monthly_income_idr = 0 AND transactions are empty, infer_weekly_income_idr
    # returns 0. This collapses payout_per_event to 0, and the InsuranceQuote
    # validator ("premium_idr must be strictly less than payout_per_event_idr")
    # raises ValidationError. asyncio.gather(return_exceptions=True) catches it
    # silently and sets quote = None — the frontend then shows "—" with no error.
    # Fix: floor to a minimum micro-cover (Rp 50k/day = bottom of gig distribution)
    # so the quote is always schema-valid. The Bahasa narrative notes it's estimated.
    _MIN_DAILY_IDR = 50_000
    if daily_earnings <= 0:
        daily_earnings = _MIN_DAILY_IDR
        payout_per_event = daily_earnings * payout_multiple

    # The schema has no WEEKLY cadence; bill monthly. Cap strictly below the
    # single-event payout to honour the InsuranceQuote guardrail (premium <
    # payout) — for realistic personas the monthly premium is a small fraction
    # of the payout and the cap never binds.
    monthly_premium = round(weekly_premium * _WEEKS_PER_MONTH)
    monthly_premium = max(0, min(monthly_premium, payout_per_event - 1))

    # Second edge: if GLM predicted zero loss (flood_risk near zero),
    # weekly_premium is 0 and monthly_premium is 0. Floor to 1 so the validator
    # ("premium < payout") holds. This only applies at the income floor above.
    if monthly_premium <= 0 and payout_per_event > 0:
        monthly_premium = 1

    # Expected annual loss for *actuarial transparency*.
    if loss_ratio is not None:
        expected_annual_loss = round(weekly_premium * float(loss_ratio) * _WEEKS_PER_YEAR)
    else:  # pragma: no cover
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

    # Hard 15-second ceiling on the model call.  Runner.run_sync has no built-in
    # timeout; without this, a slow or hung OpenAI call keeps the thread alive
    # until gunicorn's --timeout kills the worker with a 502.
    # TimeoutError propagates to the outer except block → heuristic fallback.
    # Hard 15-second ceiling on the model call. Runner.run_sync has no built-in
    # timeout; the OpenAI SDK default is 600 s, which would let gunicorn's
    # --timeout 120 kill the worker (→ 502, no CORS headers) long before the
    # call returns. We do NOT use `with ThreadPoolExecutor` here: its __exit__
    # calls shutdown(wait=True), which blocks on the hung thread and defeats the
    # timeout entirely. Instead we shut down with wait=False, abandoning the
    # (rare) hung thread so control returns within 15 s. The OpenAI client is
    # also configured with its own timeout (see _ensure_client_timeout).
    import concurrent.futures as _cf
    _ensure_client_timeout()
    _ex = _cf.ThreadPoolExecutor(max_workers=1)
    try:
        result = _ex.submit(Runner.run_sync, agent, instruction).result(timeout=10)
    finally:
        _ex.shutdown(wait=False)
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

    ``quote`` is ``None`` when insurance is deliberately not recommended (e.g.
    user already has adequate parametric coverage, or financial health is
    excellent with low flood risk). The orchestrator handles this identically
    to an agent exception, so ``FinalResponse.insurance`` will be ``None``.

    ``bahasa_description`` carries either the normal product narrative or the
    personalised reason why insurance was skipped — the orchestrator folds it
    into ``FinalResponse.narrative`` either way.
    ``weekly_premium_idr`` is kept for the narrative since the quote bills monthly.
    ``skip_reason`` (non-empty when quote is None) names the decision branch for
    logging and UI.
    """

    quote: Optional["InsuranceQuote"]
    bahasa_description: str
    source: str  # "model", "heuristic", or "skipped"
    weekly_premium_idr: int
    skip_reason: Optional[str] = None  # e.g. "low_risk", "already_insured"


# --------------------------------------------------------------------------- #
# Insurance recommendation gate                                               #
# --------------------------------------------------------------------------- #

# Keywords that indicate the user specifically has PARAMETRIC or INCOME
# protection already. Life / health insurance (BPJS, asuransi jiwa) is a
# different product and does NOT disqualify — NAIK Income Shield covers
# earnings lost when a flood prevents working, which life/health policies do
# NOT cover. We only skip when the user already has equivalent parametric or
# income-protection coverage.
_ALREADY_INSURED_ID = [
    "asuransi penghasilan", "perlindungan penghasilan", "asuransi banjir",
    "asuransi parametrik", "proteksi penghasilan", "sudah terlindungi penghasilan",
    "terlindungi dari banjir", "asuransi cuaca", "asuransi indeks",
]
_ALREADY_INSURED_EN = [
    "income insurance", "income protection", "flood insurance",
    "parametric insurance", "weather insurance", "index insurance",
    "already covered", "already insured",
]


def _has_parametric_coverage(transcript: str) -> bool:
    """Return True only if the transcript signals existing *income-protection*
    or parametric coverage.  Generic life / health mentions do NOT qualify."""
    t = transcript.lower()
    return any(kw in t for kw in _ALREADY_INSURED_ID + _ALREADY_INSURED_EN)


def _should_recommend_insurance(
    wellness: WellnessVector,
    inp: DiagnosticInput,
) -> tuple[bool, str | None]:
    """Decide whether to produce an InsuranceQuote for this user.

    Returns ``(recommend, skip_reason)`` where ``skip_reason`` is a short key
    ("low_risk", "already_insured") used for logging.  When ``recommend`` is
    False the caller should still produce a human-readable Bahasa explanation
    that goes into the FinalResponse narrative.

    Decision rules (evaluated in priority order):
    1. Gig / informal workers ALWAYS get a recommendation — they have no
       employer safety net and are the core product wedge.
    2. Critical risk gap (risk_management < 40) always warrants a quote.
    3. If the transcript explicitly mentions existing parametric / income
       insurance, skip — the user is already protected against this specific
       risk.
    4. If risk_management is healthy (≥ 65) AND the kecamatan historically
       triggers fewer than 4% of weeks (< 2 events/year), the expected value
       of the cover is low enough that it becomes optional for this profile.
    5. Excellent all-round financial health (risk_management ≥ 75,
       overall ≥ 70) with low flood incidence — skip, but note it is optional.
    6. Default: recommend.
    """
    # Rule 1 — gig workers always need income protection
    if inp.is_gig_worker:
        return True, None

    # Rule 2 — critical risk gap
    if wellness.risk_management < 40:
        return True, None

    transcript = inp.voice_transcript or ""

    # Rule 3 — already has equivalent parametric / income coverage
    if _has_parametric_coverage(transcript):
        return False, "already_insured"

    # Rules 4 & 5 need the historical trigger frequency for this kecamatan
    freq = trigger_frequency(inp.kecamatan)
    # freq = fraction of historical weeks in which the OR-trigger fires
    LOW_FLOOD_THRESHOLD = 0.04  # < ~2 events per year

    # Rule 4 — healthy risk score + low flood history
    if wellness.risk_management >= 65 and freq < LOW_FLOOD_THRESHOLD:
        return False, "low_risk"

    # Rule 5 — excellent overall health + low flood history
    if (
        wellness.risk_management >= 75
        and wellness.overall_score >= 70
        and freq < LOW_FLOOD_THRESHOLD
    ):
        return False, "low_risk_excellent"

    # Rule 6 — default: recommend
    return True, None


# Bahasa explanations for each skip reason (woven into FinalResponse.narrative)
def _skip_description_id(skip_reason: str, kecamatan: str, risk_score: float) -> str:
    if skip_reason == "already_insured":
        return (
            "Anda menyebutkan sudah memiliki perlindungan penghasilan atau asuransi "
            "parametrik yang sesuai, jadi kami tidak merekomendasikan produk tambahan "
            "saat ini. Tinjau kembali jika polis Anda berubah atau penghasilan Anda "
            "menjadi lebih tidak menentu."
        )
    # low_risk / low_risk_excellent
    return (
        f"Berdasarkan skor manajemen risiko Anda ({risk_score:.0f}/100) dan histori "
        f"cuaca di {kecamatan} — pemicu hujan lebat secara historis jarang terjadi di "
        f"wilayah ini — perlindungan penghasilan parametrik bersifat opsional untuk "
        f"profil Anda saat ini. Kami tetap merekomendasikan meninjau kembali jika "
        f"penghasilan Anda berubah menjadi lebih tidak tetap atau Anda pindah ke "
        f"wilayah dengan risiko banjir lebih tinggi."
    )


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
    import logging as _log
    _logger = _log.getLogger("naik.insurance")

    # ── Recommendation gate ───────────────────────────────────────────────
    # Check before pricing — avoids unnecessary GLM calls and returns a clear
    # Bahasa explanation when insurance is genuinely not needed.
    recommend, skip_reason = _should_recommend_insurance(wellness, inp)
    if not recommend:
        _logger.info(
            "insurance skipped for user=%s reason=%s risk_mgmt=%.1f",
            inp.user_id, skip_reason, wellness.risk_management,
        )
        return InsuranceResult(
            quote=None,
            bahasa_description=_skip_description_id(
                skip_reason or "low_risk",
                inp.kecamatan,
                wellness.risk_management,
            ),
            source="skipped",
            weekly_premium_idr=0,
            skip_reason=skip_reason,
        )

    # Wrap the deterministic pricing phase so unexpected errors surface in
    # Render logs rather than being silently swallowed by the gather.
    try:
        weekly_income = infer_weekly_income_idr(inp)
        priced = price_income_shock_cover(
            inp.kecamatan,
            weekly_income,
            gig_worker=inp.is_gig_worker,
            household_size=inp.household_size,
        )
        quote, weekly_premium = _build_quote(inp, priced, coverage_term_days=coverage_term_days)
        freq = trigger_frequency(inp.kecamatan)
    except Exception as _pricing_exc:  # noqa: BLE001
        _logger.error(
            "insurance PRICING failed for user=%s kecamatan=%s income=%s: %s: %s",
            inp.user_id, inp.kecamatan, inp.monthly_income_idr,
            type(_pricing_exc).__name__, _pricing_exc,
        )
        raise  # propagates to asyncio.gather(return_exceptions=True)

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
        # When income was zero (custom onboard user), add a note so the
        # Bahasa copy doesn't claim a specific daily earnings figure.
        if inp.monthly_income_idr == 0:
            description = (
                "Catatan: penghasilan Anda belum dilaporkan, sehingga kutipan ini "
                "menggunakan estimasi minimum (Rp 50.000/hari) sebagai dasar. "
                + description
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
