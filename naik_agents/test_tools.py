"""Tools test: the four pure-Python functions in agents/tools.py.

Exercises the offline path (no Agents SDK, no API key) — what runs in CI and at
the hackathon before the key is added. Checks the build-plan contract for each
tool plus the actuarial guardrails the InsuranceQuote schema depends on.

Run from the repo root:
    python agents/test_tools.py
"""

from __future__ import annotations

import os
import sys

if __name__ == "__main__":
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _ROOT = os.path.abspath(os.path.join(_HERE, ".."))
    for p in (_ROOT, os.path.join(_ROOT, "api")):
        if p not in sys.path:
            sys.path.insert(0, p)

    from naik_agents.tools import (  # noqa: E402
        AGENTS_SDK_AVAILABLE,
        check_trigger_frequency,
        get_bmkg_history,
        get_fund_list,
        price_income_shock_cover,
    )


def main() -> int:
    ok = fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok, fail
        mark = "PASS" if cond else "FAIL"
        if cond:
            ok += 1
        else:
            fail += 1
        print(f"  {mark}  {name}" + (f"  — {detail}" if detail else ""))

    print(f"Agents SDK available in this env: {AGENTS_SDK_AVAILABLE}\n")

    # --- get_fund_list ---------------------------------------------------------
    print("get_fund_list")
    full = get_fund_list()
    sharia = get_fund_list(sharia_only=True)
    check("returns the full catalogue", len(full) == 40, f"got {len(full)}")
    check("sharia_only filters", 0 < len(sharia) < len(full), f"{len(sharia)} sharia")
    check("every fund is sharia under the filter", all(f["is_sharia"] for f in sharia))
    check("every fund has a stable fund_id", all(f.get("fund_id") for f in full))
    check("every fund is OJK-licensed", all(f.get("is_ojk_licensed") for f in full))

    # --- get_bmkg_history ------------------------------------------------------
    print("\nget_bmkg_history")
    weeks = get_bmkg_history("Penjaringan")
    check("Penjaringan returns 52 weeks", len(weeks) == 52, f"got {len(weeks)}")
    check(
        "each week has the expected fields",
        all({"week", "rainfall_mm", "wind_speed_kmh"} <= set(w) for w in weeks),
    )
    check("unknown kecamatan returns empty list", get_bmkg_history("Atlantis") == [])

    # --- check_trigger_frequency ----------------------------------------------
    print("\ncheck_trigger_frequency")
    f_penj = check_trigger_frequency("Penjaringan", 150.0, 60.0)
    f_cila = check_trigger_frequency("Cilandak", 150.0, 60.0)
    print(f"  Penjaringan @150mm = {f_penj:.1%}, Cilandak @150mm = {f_cila:.1%}")
    check("frequency in [0,1]", 0.0 <= f_penj <= 1.0, f"{f_penj}")
    check("high-risk fires more often than low-risk", f_penj > f_cila, f"{f_penj} vs {f_cila}")
    check(
        "a higher threshold never fires more often",
        check_trigger_frequency("Penjaringan", 200.0, 60.0) <= f_penj,
    )
    check("unknown kecamatan -> 0.0", check_trigger_frequency("Atlantis", 100.0, 120.0) == 0.0)

    # --- price_income_shock_cover ---------------------------------------------
    print("\nprice_income_shock_cover (Sari: Penjaringan, ~Rp 1.385M/week, gig, hh2)")
    q = price_income_shock_cover("Penjaringan", 6_000_000 / 4.33, gig_worker=True, household_size=2)
    for k, v in q.items():
        print(f"  {k:30s} {v:,}" if isinstance(v, (int, float)) and v is not None else f"  {k:30s} {v}")
    required = {"weekly_premium_idr", "payout_multiplier"}
    check("returns the contract keys", required <= set(q), f"missing {required - set(q)}")
    check("premium under Rp 50k/week (affordable on 6M/month)", q["weekly_premium_idr"] < 50_000,
          f"Rp {q['weekly_premium_idr']:,}")
    check("premium strictly below single-event payout (schema guardrail)",
          q["weekly_premium_idr"] < q["payout_per_event_idr"],
          f"{q['weekly_premium_idr']:,} < {q['payout_per_event_idr']:,}")
    check("payout multiplier in the micro range [2,5]", 2 <= q["payout_multiplier"] <= 5,
          str(q["payout_multiplier"]))
    check("expected annual loss is positive", q["expected_annual_loss_idr"] > 0)
    check("references Penjaringan flood risk (~0.92)", q["flood_risk_score"] >= 0.88,
          str(q["flood_risk_score"]))

    # --- differentiation: the GLM actually prices risk -------------------------
    print("\nrisk differentiation (the GLM's job)")
    weekly = 6_000_000 / 4.33
    q_low_flood = price_income_shock_cover("Cilandak", weekly, gig_worker=True, household_size=2)
    q_salaried = price_income_shock_cover("Penjaringan", weekly, gig_worker=False, household_size=2)
    print(f"  Sari (gig, Penjaringan)      premium = Rp {q['weekly_premium_idr']:,}")
    print(f"  same income, low-flood        premium = Rp {q_low_flood['weekly_premium_idr']:,}")
    print(f"  same income, salaried         premium = Rp {q_salaried['weekly_premium_idr']:,}")
    check("higher flood risk -> higher premium",
          q["weekly_premium_idr"] > q_low_flood["weekly_premium_idr"])
    check("gig worker -> higher premium than salaried (same area/income)",
          q["weekly_premium_idr"] > q_salaried["weekly_premium_idr"])

    print(f"\nRESULT: {ok} passed, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
