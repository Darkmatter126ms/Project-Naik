"""Naik agent tools — the (stubbed, for the timebox) external calls the agents make.

This module is the single home for the four tool functions the agents invoke. It
is written for the OpenAI Agents SDK runtime: every tool is a plain, pure-Python
function (no LLM dependency) AND is exposed as an Agents-SDK ``@function_tool`` in
the ``AGENT_TOOLS`` list, so the same logic serves two callers without drifting:

    * the AGENTS (model path) get ``AGENT_TOOLS`` and let the SDK invoke them;
    * the deterministic heuristic paths, the eval harness, and unit tests import
      and call the plain functions directly.

Why both? A ``@function_tool``-decorated function becomes a ``FunctionTool``
object that is *not directly callable* (calling it raises "FunctionTool object is
not callable"). If we decorated the four functions in place, Allen's wealth/
insurance heuristic paths — which call them as ordinary Python — would break. So
the plain functions are canonical and the SDK wrappers are thin shims over them.

The four tools (build-plan contract):
    get_fund_list(sharia_only)                              -> list[dict]
    price_income_shock_cover(kecamatan, weekly_income_idr)  -> dict
    get_bmkg_history(kecamatan)                             -> list[dict]
    check_trigger_frequency(kecamatan, rain_mm, wind_kmh)   -> float

Data sources (all static fixtures for the timebox — no live feeds):
    eval/fixtures/funds.json          40 OJK-licensed reksa dana (Bibit/Bareksa public)
    eval/fixtures/bmkg_history.json   52 weekly weather obs/district + flood_risk_score
    agents/pricing/income_shock_glm.joblib   the Tweedie GLM pricing kernel

The Agents SDK import is OPTIONAL: with the SDK absent (offline dev, CI, no key),
the module still imports and every plain function still works; ``AGENT_TOOLS`` is
simply empty and ``AGENTS_SDK_AVAILABLE`` is False.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Optional

# joblib is imported at module level to avoid the "partially initialized module"
# race condition on Render: when the prewarm thread and the first /orchestrate
# request both call _load_pricing_bundle simultaneously, a local `import joblib`
# inside the function can see a half-initialized module. Module-level import is
# protected by Python's import lock and is always safe.
try:
    import joblib as _joblib
    _JOBLIB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _joblib = None  # type: ignore[assignment]
    _JOBLIB_AVAILABLE = False

_glm_load_lock = threading.Lock()

# --------------------------------------------------------------------------- #
# Fixture / model locations (resolved relative to this file, CWD-independent)  #
# --------------------------------------------------------------------------- #

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_FUNDS_PATH = _REPO_ROOT / "eval" / "fixtures" / "funds.json"
_DEFAULT_BMKG_PATH = _REPO_ROOT / "eval" / "fixtures" / "bmkg_history.json"
_DEFAULT_MODEL_PATH = _REPO_ROOT / "naik_agents" / "pricing" / "income_shock_glm.joblib"


def _funds_path() -> Path:
    return Path(os.environ.get("NAIK_FUNDS_PATH") or _DEFAULT_FUNDS_PATH)


def _bmkg_path() -> Path:
    return Path(os.environ.get("NAIK_BMKG_PATH") or _DEFAULT_BMKG_PATH)


def _model_path() -> Path:
    return Path(os.environ.get("NAIK_PRICING_MODEL_PATH") or _DEFAULT_MODEL_PATH)


def _slugify(name: str) -> str:
    """Deterministic, human-readable id from a fund name ('INSIGHT-MONEY-SYARIAH')."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", name.strip()).strip("-").upper()
    return cleaned or "FUND"


# --------------------------------------------------------------------------- #
# Tool 1: get_fund_list (wealth agent)                                        #
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=4)
def _load_catalogue(path_str: str) -> tuple[dict, ...]:
    """Load and normalise the fund catalogue once per distinct path (cached)."""
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(
            f"Fund catalogue not found at {path}. Set NAIK_FUNDS_PATH or restore "
            f"eval/fixtures/funds.json."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    records = raw["funds"] if isinstance(raw, dict) and "funds" in raw else raw
    if not isinstance(records, list):
        raise ValueError("funds.json must be a list of funds or an object with a 'funds' list.")

    normalised: list[dict] = []
    seen_ids: set[str] = set()
    for rec in records:
        if rec.get("is_ojk_licensed", True) is not True:  # never surface unlicensed funds
            continue
        out = dict(rec)
        fund_id = out.get("fund_id") or _slugify(str(out.get("fund_name", "")))
        base, n = fund_id, 2
        while fund_id in seen_ids:
            fund_id, n = f"{base}-{n}", n + 1
        seen_ids.add(fund_id)
        out["fund_id"] = fund_id
        normalised.append(out)
    return tuple(normalised)


def get_fund_list(sharia_only: bool = False) -> list[dict]:
    """Return the OJK-licensed reksa dana catalogue, optionally sharia-only.

    Args:
        sharia_only: when True, return only syariah-compliant funds. The wealth
            agent passes True for a halal-investing persona, so a non-sharia fund
            can never reach such a user.

    Returns:
        A list of fund dicts (fresh shallow copies, safe to enrich); each carries
        the catalogue fields plus a stable ``fund_id``.
    """
    catalogue = _load_catalogue(str(_funds_path()))
    return [dict(rec) for rec in catalogue if (rec.get("is_sharia", False) if sharia_only else True)]


# --------------------------------------------------------------------------- #
# BMKG history loader + district flood-risk lookup                            #
# --------------------------------------------------------------------------- #

#: Fallback flood-risk for a kecamatan absent from the fixture (Jakarta median).
_DEFAULT_FLOOD_RISK = 0.40


@lru_cache(maxsize=2)
def _load_bmkg(path_str: str) -> dict:
    """Load the BMKG weather fixture once (cached). Returns the parsed object."""
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(
            f"BMKG history not found at {path}. Run eval/generate_bmkg.py or "
            f"set NAIK_BMKG_PATH."
        )
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=2)
def _districts_by_name(path_str: str) -> dict:
    """Build kecamatan-name → district-block dict (cached).

    Sher Min's fixture stores districts as a list (each with a "kecamatan"
    key), not a dict. We convert once on first use.
    """
    raw = _load_bmkg(path_str)
    return {blk["kecamatan"]: blk for blk in raw.get("districts", [])}


def _districts() -> dict:
    return _districts_by_name(str(_bmkg_path()))


def _district_flood_risk(kecamatan: str) -> float:
    """Flood-risk score in [0, 1] for a kecamatan; median fallback if unknown."""
    blk = _districts().get(kecamatan)
    if blk is None:
        return _DEFAULT_FLOOD_RISK
    return float(blk.get("flood_risk_score", _DEFAULT_FLOOD_RISK))


# --------------------------------------------------------------------------- #
# Tool 2: get_bmkg_history (insurance agent)                                  #
# --------------------------------------------------------------------------- #


def get_bmkg_history(kecamatan: str) -> list[dict]:
    """Return the weekly weather observation history for a kecamatan.

    Each entry has ``week``, ``rainfall_mm``, ``wind_speed_kmh``,
    ``wet_season``, and boolean exceedance flags. An unknown kecamatan returns an empty list (the
    insurance agent then prices off the flood-risk fallback rather than crashing).

    Args:
        kecamatan: the district whose observations to return.
    """
    blk = _districts().get(kecamatan)
    if blk is None:
        return []
    return [dict(w) for w in blk.get("weeks", [])]


# --------------------------------------------------------------------------- #
# Tool 3: check_trigger_frequency (insurance agent)                           #
# --------------------------------------------------------------------------- #


def check_trigger_frequency(
    kecamatan: str,
    rainfall_threshold_mm: float,
    wind_threshold_kmh: float,
) -> float:
    """Fraction of historical weeks in which the parametric trigger would fire.

    The trigger fires when EITHER the weekly 24-hour-max rainfall reaches
    ``rainfall_threshold_mm`` OR the max wind speed reaches ``wind_threshold_kmh``
    (parametric covers commonly use an OR of indices). The insurance agent uses
    this to describe the trigger in plain Bahasa ("secara historis aktif sekitar
    X% minggu").

    Args:
        kecamatan: district to evaluate.
        rainfall_threshold_mm: rainfall trigger (mm in 24h).
        wind_threshold_kmh: wind-speed trigger (km/h).

    Returns:
        A float in [0, 1]; 0.0 when no history exists for the district.
    """
    weeks = get_bmkg_history(kecamatan)
    if not weeks:
        return 0.0
    fired = sum(
        1
        for w in weeks
        if w.get("rainfall_mm", 0.0) >= rainfall_threshold_mm
        or w.get("wind_speed_kmh", 0.0) >= wind_threshold_kmh
    )
    return round(fired / len(weeks), 4)


# --------------------------------------------------------------------------- #
# Tool 4: price_income_shock_cover (insurance agent) — the Tweedie GLM kernel  #
# --------------------------------------------------------------------------- #
#
# The GLM predicts the *full* expected weekly income loss on the (synthetic)
# training scale — a risk-ranking signal, not a chargeable amount. The parametric
# micro-cover indemnifies only a small capped benefit, so we price that benefit
# at a target loss ratio, scaling the GLM output by a single documented
# calibration constant. The GLM still drives all the rating differentiation
# (gig status, household size, income, flood risk — Gini ≈ 0.46 on holdout).

#: Maps the synthetic-scale GLM weekly loss to the realised expected weekly
#: payout of the capped micro-benefit. A coverage-intensity / exposure constant;
#: replace with a value fitted to real claims once available.
_PREMIUM_CALIBRATION = 0.009
#: Target loss ratio (expected payouts / premium) used to gross the pure premium.
_TARGET_LOSS_RATIO = 0.60
#: Working days per week used to convert weekly income to a daily-earnings unit.
_WORKING_DAYS_PER_WEEK = 6
#: Approximate parametric trigger events per year, by flood risk (for annualising).
_MIN_PAYOUT_MULTIPLE, _MAX_PAYOUT_MULTIPLE = 2, 5


@lru_cache(maxsize=2)
def _load_pricing_bundle(path_str: str) -> dict:
    """Load the joblib pricing bundle once (cached).

    Returns the dict bundle: ``{"model", "feature_names", "var_power", "link",
    "gini_holdout", ...}``. Thread-safe: the lock prevents the race condition
    where two threads simultaneously trigger the first load and one sees a
    partially-initialized joblib module.
    """
    if not _JOBLIB_AVAILABLE or _joblib is None:
        raise ImportError(
            "joblib is not installed. Run: pip install joblib scikit-learn"
        )
    with _glm_load_lock:
        path = Path(path_str)
        if not path.exists():
            raise FileNotFoundError(
                f"Pricing model not found at {path}. Set NAIK_PRICING_MODEL_PATH or "
                f"restore agents/pricing/income_shock_glm.joblib."
            )
        return _joblib.load(path)


def _income_decile_from_monthly(monthly_income_idr: float) -> int:
    """Invert the training relation monthly = 2.2M * 1.20^(decile-1) -> decile in [1,10]."""
    if monthly_income_idr <= 0:
        return 1
    decile = 1.0 + math.log(monthly_income_idr / 2_200_000.0) / math.log(1.20)
    return int(min(10, max(1, round(decile))))


def _predict_weekly_loss(
    *, monthly_income_idr: float, flood_risk: float, gig_worker: bool, household_size: int
) -> float:
    """Run the GLM to predict expected weekly income loss (IDR) for a profile.

    Builds the feature row in the bundle's declared ``feature_names`` order, so
    feature ordering can never silently drift from training.
    """
    bundle = _load_pricing_bundle(str(_model_path()))
    model, feature_names = bundle["model"], bundle["feature_names"]
    row = {
        "income_decile": _income_decile_from_monthly(monthly_income_idr),
        "flood_risk_score": float(flood_risk),
        "gig_worker": int(bool(gig_worker)),
        "household_size": int(household_size),
    }
    import pandas as pd  # local: pricing path only. A named DataFrame in the

    # bundle's feature order matches how the model was trained (no feature-name
    # warning, no chance of silent column-order drift).
    x = pd.DataFrame([row])[feature_names]
    return float(model.predict(x)[0])


def _payout_multiple_for(flood_risk: float) -> int:
    """Days of daily-earnings paid per triggering event, capped to a micro range."""
    raw = round(2 + 2.5 * flood_risk)
    return int(min(_MAX_PAYOUT_MULTIPLE, max(_MIN_PAYOUT_MULTIPLE, raw)))


def price_income_shock_cover(
    kecamatan: str,
    weekly_income_idr: float,
    *,
    gig_worker: bool = True,
    household_size: int = 1,
) -> dict:
    """Price the parametric income-shock micro-cover for a user.

    Loads the Tweedie GLM, predicts the user's expected weekly income loss, and
    converts it into an affordable capped micro-cover priced at a target loss
    ratio. The two required keys (``weekly_premium_idr``, ``payout_multiplier``)
    match the build-plan contract; the extra keys give the insurance agent
    everything it needs to assemble a valid ``InsuranceQuote`` without recomputing.

    Args:
        kecamatan: district — keys the flood-risk score and the trigger.
        weekly_income_idr: the user's weekly income (the agent derives this from
            Shopee transaction velocity); monthly is inferred as weekly × 4.33.
        gig_worker: gig/informal income raises modelled loss (default True — the
            target user is a gig worker; the agent passes the persona's real flag).
        household_size: people dependent on the income (default 1).

    Returns:
        dict with: weekly_premium_idr (int), payout_multiplier (int, days of
        income/event), estimated_daily_earnings_idr, payout_per_event_idr,
        expected_weekly_loss_idr, expected_annual_loss_idr, loss_ratio_estimate,
        flood_risk_score, model_gini_holdout. ``weekly_premium_idr`` is always
        strictly less than ``payout_per_event_idr`` (the InsuranceQuote guardrail).
    """
    flood_risk = _district_flood_risk(kecamatan)
    monthly_income = max(0.0, float(weekly_income_idr)) * 4.33

    expected_weekly_loss = _predict_weekly_loss(
        monthly_income_idr=monthly_income,
        flood_risk=flood_risk,
        gig_worker=gig_worker,
        household_size=household_size,
    )

    daily_earnings = round(max(0.0, float(weekly_income_idr)) / _WORKING_DAYS_PER_WEEK)
    payout_multiple = _payout_multiple_for(flood_risk)
    payout_per_event = daily_earnings * payout_multiple

    expected_weekly_payout = expected_weekly_loss * _PREMIUM_CALIBRATION
    weekly_premium = round(expected_weekly_payout / _TARGET_LOSS_RATIO)

    # Defensive guardrail: the InsuranceQuote schema requires premium < payout.
    if payout_per_event > 0:
        weekly_premium = min(weekly_premium, payout_per_event - 1)
    weekly_premium = max(0, weekly_premium)

    loss_ratio = round(expected_weekly_payout / weekly_premium, 3) if weekly_premium > 0 else None
    bundle = _load_pricing_bundle(str(_model_path()))

    return {
        "weekly_premium_idr": int(weekly_premium),
        "payout_multiplier": int(payout_multiple),
        "estimated_daily_earnings_idr": int(daily_earnings),
        "payout_per_event_idr": int(payout_per_event),
        "expected_weekly_loss_idr": int(round(expected_weekly_loss)),
        "expected_annual_loss_idr": int(round(expected_weekly_loss * 52)),
        "loss_ratio_estimate": loss_ratio,
        "flood_risk_score": round(flood_risk, 3),
        "model_gini_holdout": round(float(bundle.get("gini_holdout", 0.0)), 4),
    }


# --------------------------------------------------------------------------- #
# Legacy Chat Completions tool-calling helpers (Block 1 wealth model path)    #
# --------------------------------------------------------------------------- #
# Kept so the Block-1 wealth agent keeps importing cleanly. Superseded by the
# Agents SDK AGENT_TOOLS below once the wealth model path moves onto the SDK.

GET_FUND_LIST_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_fund_list",
        "description": (
            "Return the catalogue of OJK-licensed Indonesian reksa dana the user "
            "can invest in. Call with sharia_only=true for halal investors."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "sharia_only": {
                    "type": "boolean",
                    "description": "If true, return only syariah-compliant funds.",
                    "default": False,
                }
            },
            "required": [],
        },
    },
}


def dispatch_tool(name: str, arguments: Optional[dict] = None) -> object:
    """Execute a tool by name with parsed args (Chat Completions tool loop)."""
    arguments = arguments or {}
    if name == "get_fund_list":
        return get_fund_list(sharia_only=bool(arguments.get("sharia_only", False)))
    if name == "get_bmkg_history":
        return get_bmkg_history(str(arguments["kecamatan"]))
    if name == "check_trigger_frequency":
        return check_trigger_frequency(
            str(arguments["kecamatan"]),
            float(arguments["rainfall_threshold_mm"]),
            float(arguments["wind_threshold_kmh"]),
        )
    if name == "price_income_shock_cover":
        return price_income_shock_cover(
            str(arguments["kecamatan"]),
            float(arguments["weekly_income_idr"]),
            gig_worker=bool(arguments.get("gig_worker", True)),
            household_size=int(arguments.get("household_size", 1)),
        )
    raise ValueError(f"Unknown tool: {name!r}")


# --------------------------------------------------------------------------- #
# Agents SDK function-tool wrappers (the going-forward runtime)               #
# --------------------------------------------------------------------------- #
# Optional import: with the SDK absent, the plain functions above still work and
# AGENT_TOOLS is empty. The wrappers are thin shims so the SDK and the direct
# callers share one implementation.

try:  # pragma: no cover - exercised only when openai-agents is installed
    from agents import function_tool

    AGENTS_SDK_AVAILABLE = True
except Exception:  # noqa: BLE001 - SDK not installed / import failure -> offline mode
    function_tool = None  # type: ignore[assignment]
    AGENTS_SDK_AVAILABLE = False


if AGENTS_SDK_AVAILABLE:

    @function_tool
    def get_fund_list_tool(sharia_only: bool = False) -> list[dict]:
        """Return the catalogue of OJK-licensed reksa dana the user can invest in.

        Set sharia_only=true to return only syariah-compliant (halal) funds.
        """
        return get_fund_list(sharia_only=sharia_only)

    @function_tool
    def get_bmkg_history_tool(kecamatan: str) -> list[dict]:
        """Return the weekly BMKG weather history (rainfall, wind) for a kecamatan."""
        return get_bmkg_history(kecamatan=kecamatan)

    @function_tool
    def check_trigger_frequency_tool(
        kecamatan: str, rainfall_threshold_mm: float, wind_threshold_kmh: float
    ) -> float:
        """Fraction of historical weeks (0–1) in which the rainfall OR wind trigger fires."""
        return check_trigger_frequency(
            kecamatan=kecamatan,
            rainfall_threshold_mm=rainfall_threshold_mm,
            wind_threshold_kmh=wind_threshold_kmh,
        )

    @function_tool
    def price_income_shock_cover_tool(
        kecamatan: str,
        weekly_income_idr: float,
        gig_worker: bool = True,
        household_size: int = 1,
    ) -> dict:
        """Price the parametric income-shock micro-cover (Tweedie GLM).

        Returns weekly_premium_idr and payout_multiplier (days of daily earnings
        paid per triggering event), plus payout/expected-loss detail.
        """
        return price_income_shock_cover(
            kecamatan=kecamatan,
            weekly_income_idr=weekly_income_idr,
            gig_worker=gig_worker,
            household_size=household_size,
        )

    #: All four tools as Agents-SDK FunctionTools. Pass to Agent(tools=...).
    AGENT_TOOLS = [
        get_fund_list_tool,
        get_bmkg_history_tool,
        check_trigger_frequency_tool,
        price_income_shock_cover_tool,
    ]
    #: The wealth agent only needs the fund-list tool.
    WEALTH_TOOLS = [get_fund_list_tool]
    #: The insurance agent needs the three weather/pricing tools.
    INSURANCE_TOOLS = [
        get_bmkg_history_tool,
        check_trigger_frequency_tool,
        price_income_shock_cover_tool,
    ]
else:
    AGENT_TOOLS = []  # type: ignore[var-annotated]
    WEALTH_TOOLS = []  # type: ignore[var-annotated]
    INSURANCE_TOOLS = []  # type: ignore[var-annotated]


__all__ = [
    # plain (canonical) tool functions
    "get_fund_list",
    "price_income_shock_cover",
    "get_bmkg_history",
    "check_trigger_frequency",
    # district helper
    "_district_flood_risk",
    # Agents SDK runtime
    "AGENTS_SDK_AVAILABLE",
    "AGENT_TOOLS",
    "WEALTH_TOOLS",
    "INSURANCE_TOOLS",
    # legacy Chat Completions helpers (Block 1)
    "GET_FUND_LIST_TOOL_SCHEMA",
    "dispatch_tool",
]
