"""eval/generate_bmkg.py — Sher Min Block 2.

Generates eval/fixtures/bmkg_history.json:
  52 weeks of weekly-max rainfall (mm) and wind speed (km/h) for each of the
  30 kecamatan in the persona generator's DISTRICT list.

Design
------
* Time axis: ISO weeks 2025-W01 to 2025-W52 (6 Jan 2025 – 4 Jan 2026).
* Rainfall: Gamma distribution. Shape/scale parameters vary by district flood
  risk and by season. Jakarta rainy season (Nov–Mar ≈ weeks 44–52 + 1–12)
  is reflected as elevated wet-season parameters across all three cities.
* Wind speed: Weibull distribution, scale correlated with rainfall intensity.
* Exceedance constraint (build plan): high-risk districts (flood_risk ≥ 0.65)
  must have exactly 6–8 weeks/year exceeding 150 mm OR 60 km/h. After the
  probabilistic draw, the generator enforces the constraint deterministically
  by nudging borderline values — no rejection-sampling loop needed.
* Reproducible: seed 2026.
* The kecamatan names match generate_personas.DISTRICTS exactly so the
  insurance agent can look up trigger data by district name.

Thresholds used:
  rainfall_mm   150 mm  (24h-equivalent weekly max)
  wind_speed_kmh 60 km/h

Run from repo root:
    python eval/generate_bmkg.py
    python eval/generate_bmkg.py --out eval/fixtures/bmkg_history.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.generate_personas import DISTRICTS  # noqa: E402

# ── Constants ────────────────────────────────────────────────────────────── #
RAINFALL_THRESHOLD = 150.0   # mm — triggers insurance payout
WIND_THRESHOLD = 60.0        # km/h — triggers insurance payout
N_WEEKS = 52
SEED = 2026

# Build-plan constraint: high-risk (flood_risk ≥ 0.65) → 6–8 exceedance weeks
HIGH_RISK_CUTOFF = 0.65
EXCEEDANCE_MIN = 6
EXCEEDANCE_MAX = 8


# ── Week label helpers ────────────────────────────────────────────────────── #

def iso_week_labels(year: int = 2025) -> list[str]:
    """Return ISO week labels 'YYYY-Www' for all 52 weeks of the given year."""
    labels = []
    # ISO week 1 starts on the Monday containing Jan 4
    # Walk by week until we have 52 labels
    d = date(year, 1, 4)  # always in week 1
    d -= timedelta(days=d.weekday())  # back to Monday of week 1
    for _ in range(N_WEEKS):
        iso = d.isocalendar()
        labels.append(f"{iso.year}-W{iso.week:02d}")
        d += timedelta(weeks=1)
    return labels


def week_number_to_month(week: int) -> int:
    """Approximate calendar month for a given ISO week (1-indexed)."""
    # week 1 ≈ Jan; week 52 ≈ late Dec
    return min(12, max(1, round(week * 12 / 52)))


# ── Seasonal rainfall model ───────────────────────────────────────────────── #
# Jakarta/coastal Indonesia: Nov–Mar rainy season, Apr–Oct drier.
# Weeks 44–52 → Nov–Dec (late wet), weeks 1–12 → Jan–Mar (peak wet).
# Weeks 13–43 → Apr–Oct (dry).

def is_wet_season(week: int, city: str) -> bool:
    """True if this week falls in the city's main rainy season."""
    if city in ("Jakarta", "Surabaya"):
        # Nov–Mar: weeks 44–52 and 1–12
        return week <= 12 or week >= 44
    else:  # Medan has a longer rainy season (two peaks), simplified to Oct–Apr
        return week <= 16 or week >= 40


class SeasonParams(NamedTuple):
    """Gamma distribution parameters for weekly max rainfall (mm)."""
    shape: float   # k — controls variance
    scale: float   # θ — controls mean (mean = k*θ)


def rainfall_params(flood_risk: float, wet: bool, city: str) -> SeasonParams:
    """Return Gamma(shape, scale) params calibrated to produce realistic exceedances.

    Dry season: low mean (~15-40mm), low variance.
    Wet season: higher mean, heavy right tail — flood-risk scales both.

    Calibration target: high-risk (flood_risk ≥ 0.65), wet season ≈ 12-15%
    of weeks exceeding 150mm. That gives ~2-3 exceedances in the 20 wet-season
    weeks, plus ~1-2 from the dry season, totalling 3-5 "natural" exceedances.
    We then enforce the 6-8 constraint by nudging a few borderline weeks above
    the threshold (see enforce_exceedances).
    """
    base_scale = 8.0 + 22.0 * flood_risk  # 8-30mm scale base
    if wet:
        shape = 1.8 + 1.2 * flood_risk    # 1.8–3.0
        scale = base_scale * 2.5           # wet multiplier
    else:
        shape = 1.4
        scale = base_scale * 0.7
    return SeasonParams(shape=shape, scale=scale)


def wind_params(rainfall_mm: float, flood_risk: float) -> tuple[float, float]:
    """Weibull (k, λ) for weekly max wind speed (km/h).

    Wind is correlated with rainfall: heavy rain weeks have higher wind.
    Weibull shape k=2.0 (Rayleigh) is standard for wind modelling.
    """
    k = 2.0
    # base scale 15-35 km/h; elevated on high-rainfall weeks
    rain_factor = min(2.5, 1.0 + rainfall_mm / 200.0)
    lam = (15.0 + 20.0 * flood_risk) * rain_factor
    return k, lam


# ── Exceedance enforcement ────────────────────────────────────────────────── #

def enforce_exceedances(
    rainfall: np.ndarray,
    wind: np.ndarray,
    flood_risk: float,
    weeks: np.ndarray,  # week numbers 1..52
    wet_mask: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Enforce the 6-8 exceedance constraint for high-risk districts.

    An exceedance week is one where rainfall > 150mm OR wind > 60km/h.
    Strategy: count current exceedances; if outside [6,8], nudge the
    nearest-to-threshold dry/wet weeks up or down — never fabricate an
    out-of-season event.
    """
    if flood_risk < HIGH_RISK_CUTOFF:
        # Low/medium risk: just ensure ≤5 exceedances (no payout trigger)
        rain_ex = np.where(rainfall > RAINFALL_THRESHOLD)[0]
        wind_ex = np.where(wind > WIND_THRESHOLD)[0]
        all_ex = np.unique(np.concatenate([rain_ex, wind_ex]))
        excess = len(all_ex) - 5
        if excess > 0:
            # Reduce the smallest exceedances back below threshold
            for idx in all_ex[:excess]:
                rainfall[idx] = min(rainfall[idx], RAINFALL_THRESHOLD * 0.85)
                wind[idx] = min(wind[idx], WIND_THRESHOLD * 0.85)
        return rainfall, wind

    # High-risk: enforce [EXCEEDANCE_MIN, EXCEEDANCE_MAX]
    def count_ex():
        r_ex = np.where(rainfall > RAINFALL_THRESHOLD)[0]
        w_ex = np.where(wind > WIND_THRESHOLD)[0]
        return np.unique(np.concatenate([r_ex, w_ex]))

    ex_idx = count_ex()
    current = len(ex_idx)

    # Too few: nudge wet-season weeks closest to threshold above it
    if current < EXCEEDANCE_MIN:
        need = EXCEEDANCE_MIN - current
        non_ex = np.setdiff1d(np.arange(N_WEEKS), ex_idx)
        # Prefer wet-season weeks for nudging up — more realistic
        wet_non_ex = non_ex[wet_mask[non_ex]]
        if len(wet_non_ex) == 0:
            wet_non_ex = non_ex
        # Sort by closeness to threshold (descending rainfall) — smallest nudge
        order = np.argsort(rainfall[wet_non_ex])[::-1]
        candidates = wet_non_ex[order][:need]
        for idx in candidates:
            # Push rainfall just above threshold with a small random margin
            rainfall[idx] = RAINFALL_THRESHOLD + rng.uniform(2.0, 20.0)

    # Too many: pull the weakest exceedances back below threshold
    elif current > EXCEEDANCE_MAX:
        excess = current - EXCEEDANCE_MAX
        # Sort exceedances by rainfall ascending — remove the weakest first
        ex_idx_sorted = ex_idx[np.argsort(rainfall[ex_idx])]
        for idx in ex_idx_sorted[:excess]:
            rainfall[idx] = RAINFALL_THRESHOLD * rng.uniform(0.70, 0.92)
            wind[idx] = min(wind[idx], WIND_THRESHOLD * rng.uniform(0.70, 0.92))

    return rainfall, wind


# ── Per-district generator ────────────────────────────────────────────────── #

def generate_district_history(
    name: str,
    city: str,
    flood_risk: float,
    week_labels: list[str],
    rng: np.random.Generator,
) -> dict:
    """Generate 52 weeks of rainfall + wind for one district."""
    weeks = np.arange(1, N_WEEKS + 1)
    wet_mask = np.array([is_wet_season(w, city) for w in weeks])

    rainfall = np.zeros(N_WEEKS)
    wind = np.zeros(N_WEEKS)

    for i, w in enumerate(weeks):
        params = rainfall_params(flood_risk, bool(wet_mask[i]), city)
        r = rng.gamma(shape=params.shape, scale=params.scale)
        rainfall[i] = round(float(np.clip(r, 0.0, 380.0)), 1)

        k, lam = wind_params(rainfall[i], flood_risk)
        wnd = rng.weibull(k) * lam
        wind[i] = round(float(np.clip(wnd, 5.0, 110.0)), 1)

    # Enforce the exceedance constraint
    rainfall, wind = enforce_exceedances(rainfall, wind, flood_risk, weeks, wet_mask, rng)

    # Final round
    rainfall = np.round(rainfall, 1)
    wind = np.round(wind, 1)

    # Count exceedances for the metadata block
    rain_ex_weeks = [week_labels[i] for i in range(N_WEEKS)
                     if rainfall[i] > RAINFALL_THRESHOLD]
    wind_ex_weeks = [week_labels[i] for i in range(N_WEEKS)
                     if wind[i] > WIND_THRESHOLD]
    all_ex = sorted(set(rain_ex_weeks) | set(wind_ex_weeks))

    records = [
        {
            "week": week_labels[i],
            "rainfall_mm": float(rainfall[i]),
            "wind_speed_kmh": float(wind[i]),
            "wet_season": bool(wet_mask[i]),
            "exceeds_rainfall_threshold": bool(rainfall[i] > RAINFALL_THRESHOLD),
            "exceeds_wind_threshold": bool(wind[i] > WIND_THRESHOLD),
        }
        for i in range(N_WEEKS)
    ]

    return {
        "kecamatan": name,
        "city": city,
        "flood_risk_score": flood_risk,
        "rainfall_threshold_mm": RAINFALL_THRESHOLD,
        "wind_threshold_kmh": WIND_THRESHOLD,
        "exceedance_weeks": all_ex,
        "exceedance_count": len(all_ex),
        "weeks": records,
    }


# ── Main builder ─────────────────────────────────────────────────────────── #

def build_bmkg_history(seed: int = SEED) -> dict:
    """Build the full BMKG fixture for all 30 districts."""
    rng = np.random.default_rng(seed)
    week_labels = iso_week_labels(2025)
    assert len(week_labels) == 52

    districts_out = []
    for name, city, flood_risk in DISTRICTS:
        district = generate_district_history(name, city, flood_risk, week_labels, rng)
        districts_out.append(district)

    return {
        "_meta": {
            "description": (
                "Weekly maximum rainfall (mm) and wind speed (km/h) for 30 Indonesian "
                "kecamatan. Synthetic fixture anchored to BMKG climatological norms: "
                "Jakarta/Surabaya rainy season Nov–Mar (weeks 44–52, 1–12); Medan "
                "longer wet season. High-risk districts (flood_risk ≥ 0.65) have "
                "6–8 exceedance weeks/year (>150mm or >60km/h) per the build plan. "
                "Used by the insurance agent to evaluate parametric trigger precision."
            ),
            "seed": seed,
            "year": 2025,
            "n_weeks": N_WEEKS,
            "n_districts": len(DISTRICTS),
            "rainfall_threshold_mm": RAINFALL_THRESHOLD,
            "wind_threshold_kmh": WIND_THRESHOLD,
            "exceedance_constraint": f"{EXCEEDANCE_MIN}–{EXCEEDANCE_MAX} weeks for flood_risk ≥ {HIGH_RISK_CUTOFF}",
            "data_source_label": "BMKG",
        },
        "districts": districts_out,
    }


# ── CLI & summary ─────────────────────────────────────────────────────────── #

def print_summary(data: dict) -> None:
    districts = data["districts"]
    print("\n" + "═" * 68)
    print(f" BMKG FIXTURE SUMMARY  ({data['_meta']['n_districts']} districts, "
          f"{data['_meta']['n_weeks']} weeks)")
    print("═" * 68)
    print(f"\n{'District':22s} {'City':10s} {'Risk':5s} {'Ex.':4s}  {'Ex. weeks (sample)'}")
    print("-" * 68)
    for d in districts:
        ex = d["exceedance_count"]
        sample = ", ".join(d["exceedance_weeks"][:3])
        if len(d["exceedance_weeks"]) > 3:
            sample += f" (+{len(d['exceedance_weeks'])-3})"
        flag = " ✓" if ex <= EXCEEDANCE_MAX else " ✗" if d["flood_risk_score"] >= HIGH_RISK_CUTOFF else ""
        print(f"  {d['kecamatan']:20s} {d['city']:10s} {d['flood_risk_score']:.2f}  "
              f"{ex:3d}{flag}  {sample}")

    # Validation summary
    high_risk = [d for d in districts if d["flood_risk_score"] >= HIGH_RISK_CUTOFF]
    low_risk  = [d for d in districts if d["flood_risk_score"] <  HIGH_RISK_CUTOFF]
    in_range  = sum(1 for d in high_risk if EXCEEDANCE_MIN <= d["exceedance_count"] <= EXCEEDANCE_MAX)
    low_ok    = sum(1 for d in low_risk  if d["exceedance_count"] <= 5)
    print(f"\nHigh-risk in [{EXCEEDANCE_MIN},{EXCEEDANCE_MAX}]: {in_range}/{len(high_risk)}")
    print(f"Low/medium  ≤5 exceedances: {low_ok}/{len(low_risk)}")
    print("═" * 68 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate BMKG weather fixture")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--out", type=str, default="eval/fixtures/bmkg_history.json",
        help="Output path (default: eval/fixtures/bmkg_history.json)"
    )
    parser.add_argument("--no-write", action="store_true",
                        help="Print summary only, do not write file")
    args = parser.parse_args()

    print(f"Generating BMKG fixture (seed={args.seed}) …")
    data = build_bmkg_history(seed=args.seed)
    print_summary(data)

    if not args.no_write:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        size_kb = out_path.stat().st_size // 1024
        print(f"Written {args.out} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
