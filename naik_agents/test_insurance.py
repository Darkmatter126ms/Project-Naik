"""Insurance agent test: run_insurance over Sari + a persona sweep.

Exercises the offline heuristic path (no key) and asserts the build-plan
contract: a valid InsuranceQuote, a BMKG-backed parametric trigger naming the
kecamatan, an affordable weekly premium, payout in days of income, and the
SiProPer-complementary framing in the Bahasa description.

Run from the repo root:
    python naik_agents/test_insurance.py
"""

from __future__ import annotations

import os
import sys

# Guard: only import agent modules when this file is run directly.
# When Python imports naik_agents as a package, test files inside it must NOT
# trigger agent imports — that causes a circular import on Render at startup.
if __name__ == "__main__":
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _ROOT = os.path.abspath(os.path.join(_HERE, ".."))
    for p in (_ROOT, os.path.join(_ROOT, "api")):
        if p not in sys.path:
            sys.path.insert(0, p)

    from api.schemas import InsuranceQuote, TriggerMetric  # noqa: E402
    from naik_agents.diagnostic import run_diagnostic  # noqa: E402
    from naik_agents.insurance import (  # noqa: E402
        PRODUCT_NAME,
        infer_weekly_income_idr,
        run_insurance,
    )
    from naik_agents.personas import make_sari, persona_suite  # noqa: E402


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

    # --- Sari: the headline persona -------------------------------------------
    print("run_insurance — Sari (Penjaringan, gig ojek, hh2, ~Rp6M/month)")
    sari = make_sari()
    wellness = run_diagnostic(sari).vector
    res = run_insurance(wellness, sari, force_heuristic=True)
    q = res.quote

    print(f"  source                       {res.source}")
    print(f"  weekly_premium_idr           Rp {res.weekly_premium_idr:,}")
    print(f"  premium_idr ({q.premium_frequency.value:7s})      Rp {q.premium_idr:,}")
    print(f"  estimated_daily_earnings_idr Rp {q.estimated_daily_earnings_idr:,}")
    print(f"  payout_multiple              {q.payout_multiple} days")
    print(f"  payout_per_event_idr         Rp {q.payout_per_event_idr:,}")
    print(f"  max_payouts_per_term         {q.max_payouts_per_term}")
    print(f"  coverage_term_days           {q.coverage_term_days}")
    print(f"  expected_annual_loss_idr     Rp {q.expected_annual_loss_idr:,}")
    print(f"  loss_ratio_estimate          {q.loss_ratio_estimate}")
    print(f"  trigger                      {q.trigger.metric.value} >= "
          f"{q.trigger.threshold} {q.trigger.unit} @ {q.trigger.kecamatan}")
    print(f"  bahasa: {res.bahasa_description}")

    check("returns a valid InsuranceQuote", isinstance(q, InsuranceQuote))
    check("quote is for Sari", q.user_id == "sari")
    check("trigger names Sari's kecamatan", q.trigger.kecamatan == "Penjaringan")
    check("trigger is a BMKG rainfall metric", q.trigger.metric is TriggerMetric.RAINFALL_MM
          and q.trigger.data_source == "BMKG")
    check("weekly premium under Rp 50k (affordable on 6M/month)",
          res.weekly_premium_idr < 50_000, f"Rp {res.weekly_premium_idr:,}")
    check("premium strictly below single-event payout (schema guardrail)",
          q.premium_idr < q.payout_per_event_idr,
          f"{q.premium_idr:,} < {q.payout_per_event_idr:,}")
    check("payout sized in days of income (multiple in [2,5])",
          2 <= q.payout_multiple <= 5, str(q.payout_multiple))
    check("payout per event = daily earnings × multiple",
          q.payout_per_event_idr == int(q.estimated_daily_earnings_idr * q.payout_multiple),
          f"{q.payout_per_event_idr:,} vs {int(q.estimated_daily_earnings_idr*q.payout_multiple):,}")
    check("loss ratio in [0,1]", q.loss_ratio_estimate is None or 0.0 <= q.loss_ratio_estimate <= 1.0)
    check("expected annual loss is credible (< 5× annual income)",
          q.expected_annual_loss_idr < 5 * sari.monthly_income_idr * 12,
          f"Rp {q.expected_annual_loss_idr:,}")

    # Bahasa content checks
    desc = res.bahasa_description.lower()
    check("Bahasa names the kecamatan", "penjaringan" in desc)
    check("Bahasa describes the rainfall trigger", "mm" in desc and "bmkg" in desc)
    check("Bahasa frames SiProPer as complementary",
          "siproper" in desc and ("melengkapi" in desc or "bukan menggantikan" in desc))
    check("Bahasa states the weekly premium", "minggu" in desc)

    # --- daily-earnings velocity inference ------------------------------------
    print("\ntransaction-velocity income inference")
    wk = infer_weekly_income_idr(sari)
    print(f"  Sari inferred weekly income  Rp {wk:,} (≈ Rp {round(wk*52/12):,}/month)")
    check("velocity infers a sane weekly income (Rp 1.0M–1.8M)", 1_000_000 <= wk <= 1_800_000,
          f"Rp {wk:,}")

    # --- persona sweep: every persona is handled, quotes are valid -----------
    # Some personas legitimately SKIP insurance (low flood risk + healthy
    # risk_management, or already insured) — that is correct behaviour, not a
    # failure. We separate the two: validate every quote that exists, and assert
    # that skips carry a reason + explanation.
    print("\npersona sweep (all heuristic)")
    results = []
    for inp, _gap in persona_suite():
        w = run_diagnostic(inp).vector
        r = run_insurance(w, inp, force_heuristic=True)
        results.append((inp, r))
        if r.quote is not None:
            print(f"  {inp.user_id:10s} {inp.kecamatan:14s} gig={str(inp.is_gig_worker):5s} "
                  f"QUOTE  premium Rp {r.weekly_premium_idr:>7,}/wk  "
                  f"payout Rp {r.quote.payout_per_event_idr:>10,}  {r.quote.payout_multiple:.0f}d")
        else:
            print(f"  {inp.user_id:10s} {inp.kecamatan:14s} gig={str(inp.is_gig_worker):5s} "
                  f"SKIP   reason={r.skip_reason}")

    quoted = [(inp, r) for inp, r in results if r.quote is not None]
    skipped = [(inp, r) for inp, r in results if r.quote is None]

    check("at least one persona yields a quote", len(quoted) > 0)
    check("every produced quote has premium < payout",
          all(r.quote.premium_idr < r.quote.payout_per_event_idr for _, r in quoted))
    check("every produced quote is complementary to SiProPer",
          all("siproper" in r.bahasa_description.lower() for _, r in quoted))
    check("every skip carries a reason and a Bahasa explanation",
          all(r.skip_reason and r.bahasa_description.strip() for _, r in skipped),
          f"{len(skipped)} skipped")
    check("gig workers are never skipped (core wedge)",
          all(r.quote is not None for inp, r in results if inp.is_gig_worker))

    # Flood differentiation: Sari (Penjaringan 0.92) pays more than a low-flood
    # persona of similar income/gig status, if present and quoted.
    sari_prem = next((r.weekly_premium_idr for inp, r in quoted if inp.user_id == "sari"), None)
    low_flood = [r.weekly_premium_idr for inp, r in quoted if inp.kecamatan in ("Cilandak", "Menteng")]
    if sari_prem is not None and low_flood:
        check("Sari's flood-exposed premium exceeds a low-flood persona's",
              sari_prem > min(low_flood), f"Sari {sari_prem:,} vs low-flood {min(low_flood):,}")

    print(f"\nRESULT: {ok} passed, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
