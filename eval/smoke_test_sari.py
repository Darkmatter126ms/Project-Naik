"""Block 5 — Sari smoke test.

Loads eval/fixtures/sari.json, runs the full offline pipeline (force_heuristic=True
so the test runs without an API key), and asserts the six properties the build plan
requires.

Run from the repo root:
    python eval/smoke_test_sari.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure repo root + api package are on sys.path regardless of CWD.
_ROOT = Path(__file__).resolve().parent.parent
for p in (_ROOT, _ROOT / "api"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from api.schemas import DiagnosticInput  # noqa: E402
from naik_agents.diagnostic import run_diagnostic  # noqa: E402
from naik_agents.insurance import run_insurance  # noqa: E402
from naik_agents.orchestrator import run_naik  # noqa: E402
from naik_agents.wealth import resolve_sharia_only  # noqa: E402

_FIXTURE = _ROOT / "eval" / "fixtures" / "sari.json"

WEEKLY_PREMIUM_THRESHOLD = 50_000   # Rp — the hard cap the build plan requires
RISK_MANAGEMENT_THRESHOLD = 45      # score out of 100; Sari should be well below


def _load_sari() -> DiagnosticInput:
    with open(_FIXTURE, encoding="utf-8") as f:
        return DiagnosticInput.model_validate(json.load(f))


def main() -> int:
    ok = fail = 0

    def check(label: str, condition: bool, detail: str = "") -> None:
        nonlocal ok, fail
        mark = "PASS" if condition else "FAIL"
        if condition:
            ok += 1
        else:
            fail += 1
        suffix = f"  — {detail}" if detail else ""
        print(f"  {mark}  {label}{suffix}")

    print(f"Loading fixture: {_FIXTURE}")
    sari = _load_sari()

    n_tx    = len(sari.transactions)
    n_food  = sum(1 for t in sari.transactions
                  if t.direction.value == "debit" and
                  (t.category and t.category.value == "food_beverage"))
    n_inc   = sum(1 for t in sari.transactions
                  if t.direction.value == "credit" and
                  (t.category and t.category.value == "income"))
    print(f"  {n_tx} transactions: {n_inc} income, {n_food} food_beverage (GoFood)")

    # Verify the halal signal resolves correctly before running the heavy pipeline.
    sharia_flag = resolve_sharia_only(sari, None)
    print(f"  resolve_sharia_only → {sharia_flag}")
    if not sharia_flag:
        print("  ABORT: sari.json has no halal signal — top fund will not be sharia.")
        return 1

    print("\nRunning run_naik(sari, force_heuristic=True) …")
    result = run_naik(sari, force_heuristic=True)
    print("  done.\n")

    # ── 1. risk_management score is low ───────────────────────────────────────
    rm_score = result.wellness.risk_management
    check(
        "risk_management score is low",
        rm_score <= RISK_MANAGEMENT_THRESHOLD,
        f"score={rm_score} (threshold ≤ {RISK_MANAGEMENT_THRESHOLD})",
    )

    # ── 2. priority_gap is 'risk_management' ──────────────────────────────────
    pg = result.wellness.priority_gap.value
    check(
        "priority_gap == 'risk_management'",
        pg == "risk_management",
        f"got '{pg}'",
    )

    # ── 3. top fund is sharia-compliant ───────────────────────────────────────
    top = result.wealth.picks[0] if result.wealth and result.wealth.picks else None
    check(
        "top fund is sharia-compliant",
        top is not None and top.is_sharia is True,
        f"fund='{top.fund_name if top else 'NONE'}' is_sharia={top.is_sharia if top else '?'}",
    )

    # ── 4. insurance trigger references Penjaringan ───────────────────────────
    trig_kec = result.insurance.trigger.kecamatan if result.insurance else "NONE"
    check(
        "insurance trigger kecamatan == 'Penjaringan'",
        trig_kec == "Penjaringan",
        f"kecamatan='{trig_kec}'",
    )

    # ── 5. weekly premium < Rp 50k ────────────────────────────────────────────
    # FinalResponse.insurance is an InsuranceQuote (monthly).
    # Run insurance directly to get the weekly figure from InsuranceResult.
    diag_result   = run_diagnostic(sari, force_heuristic=True)
    ins_result    = run_insurance(diag_result.vector, sari, force_heuristic=True)
    weekly_prem   = ins_result.weekly_premium_idr
    monthly_prem  = result.insurance.premium_idr if result.insurance else 0
    check(
        f"weekly_premium_idr < Rp {WEEKLY_PREMIUM_THRESHOLD:,}",
        weekly_prem < WEEKLY_PREMIUM_THRESHOLD,
        f"weekly=Rp {weekly_prem:,}  (monthly=Rp {monthly_prem:,})",
    )

    # ── 6. requires_human_confirmation is True ────────────────────────────────
    hcr = result.compliance.requires_human_confirmation
    check(
        "requires_human_confirmation is True",
        hcr is True,
        f"got {hcr}",
    )

    # ── Summary printout ──────────────────────────────────────────────────────
    print()
    print("── pipeline output ──────────────────────────────────────────────────")
    print(f"  next_step:      {result.next_step.value}")
    print(f"  priority_gap:   {pg}  (score {rm_score})")
    print(f"  wealth picks:   {len(result.wealth.picks) if result.wealth else 0}")
    if result.wealth:
        for i, p in enumerate(result.wealth.picks, 1):
            print(f"    {i}. {p.fund_name:<42} sharia={p.is_sharia}")
    print(f"  trigger:        {result.insurance.trigger.metric.value} ≥ "
          f"{result.insurance.trigger.threshold} {result.insurance.trigger.unit} "
          f"at {trig_kec}")
    print(f"  payout/event:   Rp {result.insurance.payout_per_event_idr:,} "
          f"({result.insurance.payout_multiple:.0f} days income)")
    print(f"  premium:        Rp {weekly_prem:,}/week  (Rp {monthly_prem:,}/month)")
    print(f"  compliance:     {result.compliance.status.value}")
    print(f"  narrative:      {result.narrative[:80]}…")
    print()
    print(f"RESULT: {ok} passed, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
