"""Naik — Block 2 end-to-end integration test: run_naik(sari_input).

Runs the full four-agent pipeline on Sari's hand-crafted fixture without any
mocks or monkeypatching.  ``force_heuristic=True`` routes every agent to its
deterministic local path (no LLM key required), which is the real wiring — not
a stub — so every schema validation, CRRA weight computation, Tweedie GLM call,
fund ranking, and compliance rewrite actually executes.

Assertions (build-plan contract):
  1. All FinalResponse fields are populated (no required field is None/empty).
  2. WellnessVector: all seven dimension scores are valid; priority_gap is set.
  3. priority_gap == "risk_management"                ← explicit build-plan spec
  4. compliance.status is APPROVED or APPROVED_WITH_CONDITIONS ("approved")
  5. insurance.premium_idr < insurance.payout_per_event_idr ("premium < payout")
  6. All OJK invariants hold (is_general_guidance=True,
     requires_human_confirmation=True, at least one disclaimer).
  7. Halal constraint honoured: top fund is sharia-compliant (Sari's goal:
     "investasi syariah").
  8. Insurance trigger references Sari's kecamatan ("Penjaringan").
  9. FinalResponse round-trips through JSON serialisation (proves the full
     Pydantic schema is populated and consistent — no partial or detached objects).

Usage (from repo root, no OPENAI_API_KEY needed):
    python eval/test_e2e_sari.py

Results are written to eval/test_e2e_results.json regardless of pass/fail so
they can be picked up by the eval harness / demo dashboard.

Exit codes:
    0  — all assertions passed.
    1  — one or more assertions failed (details in the JSON artifact).
    2  — crash before the pipeline completed (unhandled exception).
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ── path setup (CWD-independent) ────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "api"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ── imports ──────────────────────────────────────────────────────────────────
from api.schemas import (  # noqa: E402
    ComplianceStatus,
    DiagnosticInput,
    FinalResponse,
    WellnessDimension,
)
from naik_agents.orchestrator import run_naik  # noqa: E402

# ── paths ────────────────────────────────────────────────────────────────────
_FIXTURE   = _ROOT / "eval" / "fixtures" / "sari.json"
_RESULTS   = _ROOT / "eval" / "test_e2e_results.json"

# Accepted compliance statuses (anything other than REJECTED / NEEDS_HUMAN_REVIEW
# counts as "approved" for the purpose of the build-plan gate).
_APPROVED_STATUSES = {ComplianceStatus.APPROVED, ComplianceStatus.APPROVED_WITH_CONDITIONS}


# ============================================================================
# Assertion framework (tiny, no external test library)
# ============================================================================

@dataclass
class _Check:
    """One named assertion and its outcome."""
    name: str
    passed: bool
    detail: str = ""
    group: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class _Suite:
    """Collects checks, tracks pass/fail, and formats output."""

    def __init__(self) -> None:
        self._checks: list[_Check] = []

    def check(
        self,
        name: str,
        condition: bool,
        detail: str = "",
        group: str = "",
    ) -> None:
        c = _Check(name=name, passed=condition, detail=detail, group=group)
        self._checks.append(c)
        mark = "PASS" if condition else "FAIL"
        suffix = f"  — {detail}" if detail else ""
        print(f"  [{mark}]  {name}{suffix}")

    @property
    def passed(self) -> int:
        return sum(1 for c in self._checks if c.passed)

    @property
    def failed(self) -> int:
        return sum(1 for c in self._checks if not c.passed)

    @property
    def total(self) -> int:
        return len(self._checks)

    @property
    def all_passed(self) -> bool:
        return self.failed == 0

    def failed_names(self) -> list[str]:
        return [c.name for c in self._checks if not c.passed]

    def as_list(self) -> list[dict]:
        return [c.as_dict() for c in self._checks]


# ============================================================================
# Fixture loader
# ============================================================================

def _load_sari() -> DiagnosticInput:
    """Load and validate Sari's DiagnosticInput from the fixture file."""
    if not _FIXTURE.exists():
        raise FileNotFoundError(
            f"Sari fixture not found at {_FIXTURE}. "
            "Restore eval/fixtures/sari.json from the repo."
        )
    with _FIXTURE.open(encoding="utf-8") as f:
        raw = json.load(f)
    # sari.json includes computed 'signed_amount_idr' fields; the schema's
    # _drop_computed_fields_on_input validator strips them cleanly.
    return DiagnosticInput.model_validate(raw)


# ============================================================================
# Assertion groups
# ============================================================================

def _assert_finalresponse_populated(s: _Suite, r: FinalResponse) -> None:
    """Group A — every required field of FinalResponse is non-None/non-empty."""
    g = "A: FinalResponse fields"
    s.check("request_id is a non-empty string",
            bool(r.request_id and r.request_id.strip()), f"got {r.request_id!r}", g)
    s.check("user_id == 'sari'",
            r.user_id == "sari", f"got {r.user_id!r}", g)
    s.check("wellness is not None",
            r.wellness is not None, "", g)
    s.check("wealth is not None (Sari triggers investment recommendation)",
            r.wealth is not None, "", g)
    s.check("insurance is not None (Sari has a flood-income gap)",
            r.insurance is not None, "", g)
    s.check("compliance is not None",
            r.compliance is not None, "", g)
    s.check("narrative is a non-empty string",
            bool(r.narrative and r.narrative.strip()), f"len={len(r.narrative)}", g)
    s.check("next_step is set",
            r.next_step is not None, f"got {r.next_step}", g)
    s.check("disclaimers list is non-empty",
            bool(r.disclaimers), f"got {len(r.disclaimers)} entries", g)


def _assert_wellness_vector(s: _Suite, r: FinalResponse) -> None:
    """Group B — WellnessVector integrity and the priority-gap assertion."""
    if r.wellness is None:
        s.check("WellnessVector present (skip sub-checks)", False, "wellness is None", "B: Wellness")
        return
    g = "B: WellnessVector"
    w = r.wellness

    # All seven scores must be in [0, 100].
    dims = [
        ("diversification", w.diversification),
        ("liquidity", w.liquidity),
        ("growth", w.growth),
        ("risk_management", w.risk_management),
        ("tax_efficiency", w.tax_efficiency),
        ("emergency_fund", w.emergency_fund),
        ("behavioural_resilience", w.behavioural_resilience),
    ]
    all_valid = all(0.0 <= v <= 100.0 for _, v in dims)
    dim_detail = ", ".join(f"{n}={v}" for n, v in dims)
    s.check("all seven dimension scores in [0, 100]", all_valid, dim_detail, g)

    s.check("overall_score in [0, 100]",
            0.0 <= w.overall_score <= 100.0, f"got {w.overall_score}", g)

    # ── THE BUILD-PLAN ASSERTION ──────────────────────────────────────────────
    s.check(
        "priority_gap == 'risk_management'   ← BUILD-PLAN SPEC",
        w.priority_gap is WellnessDimension.RISK_MANAGEMENT,
        f"got '{w.priority_gap.value}'  (scores: rm={w.risk_management}, "
        f"ef={w.emergency_fund}, liq={w.liquidity})",
        g,
    )

    # The schema enforces this, but asserting it here makes the failure visible.
    lowest = min(v for _, v in dims)
    s.check(
        "priority_gap is genuinely the lowest-scoring dimension",
        abs(w.risk_management - lowest) < 1e-6 or w.risk_management == lowest,
        f"risk_management={w.risk_management}, floor={lowest}",
        g,
    )


def _assert_wealth_recommendation(s: _Suite, r: FinalResponse) -> None:
    """Group C — WealthRecommendation fields and the halal constraint."""
    if r.wealth is None:
        s.check("WealthRecommendation present (skip sub-checks)",
                False, "wealth is None", "C: Wealth")
        return
    g = "C: WealthRecommendation"
    w = r.wealth

    s.check("1–3 fund picks",
            1 <= len(w.picks) <= 3, f"got {len(w.picks)} picks", g)
    s.check("recommended_monthly_contribution_idr >= 0",
            w.recommended_monthly_contribution_idr >= 0,
            f"Rp {w.recommended_monthly_contribution_idr:,}", g)
    s.check("rationale is non-empty",
            bool(w.rationale and w.rationale.strip()),
            f"len={len(w.rationale)}", g)

    all_ojk = all(p.is_ojk_licensed for p in w.picks)
    s.check("all picks are OJK-licensed",
            all_ojk,
            ", ".join(p.fund_name for p in w.picks),
            g)

    # Sari has "investasi syariah" as a financial goal → top fund MUST be sharia.
    top = w.picks[0] if w.picks else None
    s.check(
        "top fund is sharia-compliant (Sari is a halal investor)",
        top is not None and top.is_sharia is True,
        f"fund='{top.fund_name if top else 'NONE'}' is_sharia={top.is_sharia if top else '?'}",
        g,
    )


def _assert_insurance_quote(s: _Suite, r: FinalResponse) -> None:
    """Group D — InsuranceQuote fields, the premium<payout guardrail, and kecamatan."""
    if r.insurance is None:
        s.check("InsuranceQuote present (skip sub-checks)",
                False, "insurance is None", "D: Insurance")
        return
    g = "D: InsuranceQuote"
    q = r.insurance

    s.check("quote_id is non-empty",
            bool(q.quote_id), f"got {q.quote_id!r}", g)
    s.check("premium_idr > 0",
            q.premium_idr > 0, f"Rp {q.premium_idr:,}", g)
    s.check("payout_per_event_idr > 0",
            q.payout_per_event_idr > 0, f"Rp {q.payout_per_event_idr:,}", g)

    # ── THE BUILD-PLAN ASSERTION ──────────────────────────────────────────────
    s.check(
        "premium_idr < payout_per_event_idr   ← BUILD-PLAN SPEC",
        q.premium_idr < q.payout_per_event_idr,
        f"premium=Rp {q.premium_idr:,}  payout=Rp {q.payout_per_event_idr:,}  "
        f"ratio={q.premium_idr / q.payout_per_event_idr:.3f}",
        g,
    )

    s.check(
        "trigger kecamatan == 'Penjaringan'",
        q.trigger.kecamatan == "Penjaringan",
        f"got '{q.trigger.kecamatan}'",
        g,
    )
    s.check(
        "trigger metric == 'rainfall_mm' (BMKG parametric)",
        q.trigger.metric.value == "rainfall_mm",
        f"got '{q.trigger.metric.value}'",
        g,
    )
    s.check("estimated_daily_earnings_idr > 0",
            q.estimated_daily_earnings_idr > 0,
            f"Rp {q.estimated_daily_earnings_idr:,}", g)

    # Cross-field: payout = daily_earnings × payout_multiple (within rounding).
    expected_payout = round(q.estimated_daily_earnings_idr * q.payout_multiple)
    payout_ok = abs(q.payout_per_event_idr - expected_payout) <= 1
    s.check(
        "payout_per_event_idr = daily_earnings × payout_multiple (±1 Rp rounding)",
        payout_ok,
        f"{q.estimated_daily_earnings_idr:,} × {q.payout_multiple} = "
        f"{expected_payout:,}, got {q.payout_per_event_idr:,}",
        g,
    )


def _assert_compliance(s: _Suite, r: FinalResponse) -> None:
    """Group E — ComplianceVerdict: approved, OJK invariants, Rule 4."""
    if r.compliance is None:
        s.check("ComplianceVerdict present (skip sub-checks)",
                False, "compliance is None", "E: Compliance")
        return
    g = "E: ComplianceVerdict"
    c = r.compliance

    # ── THE BUILD-PLAN ASSERTION ──────────────────────────────────────────────
    s.check(
        "compliance.status is APPROVED or APPROVED_WITH_CONDITIONS   ← BUILD-PLAN SPEC",
        c.status in _APPROVED_STATUSES,
        f"got '{c.status.value}'",
        g,
    )
    # OJK schema invariants (enforced by the schema, verified here explicitly).
    s.check("is_general_guidance is True (OJK framing)",
            c.is_general_guidance is True, "", g)
    s.check("requires_human_confirmation is True (Rule 4)",
            c.requires_human_confirmation is True, "", g)
    s.check("at least one disclaimer present",
            len(c.disclaimers) >= 1,
            f"got {len(c.disclaimers)} disclaimers", g)
    s.check("rationale is non-empty",
            bool(c.rationale and c.rationale.strip()),
            f"len={len(c.rationale)}", g)


def _assert_schema_round_trip(s: _Suite, r: FinalResponse) -> None:
    """Group F — FinalResponse serialises to JSON and round-trips cleanly.

    This is the most thorough "all fields populated" proof: if any required
    field is absent, missing, or of the wrong type, either model_dump_json()
    raises or model_validate() raises on the re-parse. A silent partial object
    cannot survive this test.
    """
    g = "F: Schema round-trip"
    try:
        raw_json = r.model_dump_json()
        parsed   = json.loads(raw_json)
        FinalResponse.model_validate(parsed)
        s.check("FinalResponse serialises and re-validates through JSON", True,
                f"JSON bytes={len(raw_json)}", g)
    except Exception as exc:
        s.check("FinalResponse serialises and re-validates through JSON", False,
                f"{type(exc).__name__}: {exc}", g)


def _assert_pipeline_narrative(s: _Suite, r: FinalResponse) -> None:
    """Group G — narrative coherence: the output reads like a financial advisor."""
    g = "G: Narrative coherence"

    # Narrative must mention the priority gap explicitly.
    kw_gap = "perlindungan"  # the Bahasa phrase for risk_management
    s.check(
        f"narrative mentions the priority gap ('{kw_gap}')",
        kw_gap in r.narrative.lower(),
        f"narrative[:100] = {r.narrative[:100]!r}",
        g,
    )

    # next_step must be a transactional action (not just review) since Sari
    # needs BOTH wealth and insurance.
    transactional = {"confirm_both", "confirm_investment", "confirm_insurance"}
    s.check(
        "next_step is a transactional action (confirm_both / confirm_investment / confirm_insurance)",
        r.next_step.value in transactional,
        f"got '{r.next_step.value}'",
        g,
    )


# ============================================================================
# Results writer
# ============================================================================

def _write_results(
    suite: _Suite,
    response: Optional[FinalResponse],
    crashed: bool,
    crash_tb: str = "",
) -> None:
    """Write the full results dict to eval/test_e2e_results.json."""

    def _safe(val: Any) -> Any:
        """Make a value JSON-serialisable (enums → .value, etc.)."""
        if hasattr(val, "value"):   # enum
            return val.value
        if hasattr(val, "model_dump"):
            return val.model_dump(mode="json")
        return val

    snapshot: dict[str, Any] = {}
    if response is not None:
        w = response.wellness
        ins = response.insurance
        snapshot = {
            "request_id":            response.request_id,
            "next_step":             _safe(response.next_step),
            "priority_gap":          _safe(w.priority_gap) if w else None,
            "rm_score":              w.risk_management if w else None,
            "overall_score":         w.overall_score if w else None,
            "wealth_picks":          [
                {"fund_name": p.fund_name, "is_sharia": p.is_sharia,
                 "match_score": p.match_score}
                for p in response.wealth.picks
            ] if response.wealth else [],
            "insurance_premium_idr": ins.premium_idr if ins else None,
            "insurance_payout_idr":  ins.payout_per_event_idr if ins else None,
            "trigger_kecamatan":     ins.trigger.kecamatan if ins else None,
            "compliance_status":     _safe(response.compliance.status) if response.compliance else None,
            "narrative_preview":     response.narrative[:120] if response.narrative else None,
        }

    results = {
        "test":       "test_e2e_sari",
        "fixture":    str(_FIXTURE),
        "mode":       "force_heuristic (no OpenAI key required)",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "passed":     suite.passed,
        "failed":     suite.failed,
        "total":      suite.total,
        "all_passed": suite.all_passed,
        "crashed":    crashed,
        "crash_traceback": crash_tb,
        "failed_assertions": suite.failed_names(),
        "assertions": suite.as_list(),
        "pipeline_snapshot": snapshot,
    }

    _RESULTS.write_text(json.dumps(results, indent=2, ensure_ascii=False))


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    """Run all assertions and return an exit code."""
    print("=" * 68)
    print("  Naik Block 2 — E2E integration test: run_naik(sari_input)")
    print("  Mode: force_heuristic=True  (no API key required, no mocks)")
    print("=" * 68)

    # ── Load fixture ─────────────────────────────────────────────────────────
    print(f"\nFixture: {_FIXTURE}")
    try:
        sari = _load_sari()
    except Exception as exc:
        print(f"\n[CRASH] Could not load fixture: {exc}")
        traceback.print_exc()
        s = _Suite()
        _write_results(s, None, crashed=True, crash_tb=traceback.format_exc())
        return 2

    n_tx   = len(sari.transactions)
    n_inc  = sum(1 for t in sari.transactions if t.direction.value == "credit"
                 and t.category and t.category.value == "income")
    n_food = sum(1 for t in sari.transactions if t.direction.value == "debit"
                 and t.category and t.category.value == "food_beverage")
    print(f"  {n_tx} transactions | {n_inc} income inflows | {n_food} food_beverage (GoFood)")
    print(f"  kecamatan={sari.kecamatan}, gig_worker={sari.is_gig_worker}, "
          f"income=Rp {sari.monthly_income_idr:,}/month\n")

    # ── Run the pipeline ──────────────────────────────────────────────────────
    print("Running run_naik(sari, force_heuristic=True)  [no mocks, no API key] …")
    response: Optional[FinalResponse] = None
    suite = _Suite()
    crash_tb = ""

    try:
        response = run_naik(sari, force_heuristic=True)
        print("  Pipeline completed.\n")
    except Exception as exc:
        crash_tb = traceback.format_exc()
        print(f"\n[CRASH] run_naik raised an exception:\n{crash_tb}")
        _write_results(suite, None, crashed=True, crash_tb=crash_tb)
        return 2

    # ── Assertions ────────────────────────────────────────────────────────────
    print("─" * 68)
    print("  A: FinalResponse fields populated")
    print("─" * 68)
    _assert_finalresponse_populated(suite, response)

    print("\n" + "─" * 68)
    print("  B: WellnessVector  (the priority-gap assertion)")
    print("─" * 68)
    _assert_wellness_vector(suite, response)

    print("\n" + "─" * 68)
    print("  C: WealthRecommendation")
    print("─" * 68)
    _assert_wealth_recommendation(suite, response)

    print("\n" + "─" * 68)
    print("  D: InsuranceQuote  (the premium < payout assertion)")
    print("─" * 68)
    _assert_insurance_quote(suite, response)

    print("\n" + "─" * 68)
    print("  E: ComplianceVerdict  (the 'compliance approved' assertion)")
    print("─" * 68)
    _assert_compliance(suite, response)

    print("\n" + "─" * 68)
    print("  F: Schema round-trip")
    print("─" * 68)
    _assert_schema_round_trip(suite, response)

    print("\n" + "─" * 68)
    print("  G: Narrative coherence")
    print("─" * 68)
    _assert_pipeline_narrative(suite, response)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 68)
    print(f"  TOTAL: {suite.passed} passed, {suite.failed} failed  "
          f"out of {suite.total} assertions")
    if suite.failed:
        print("\n  FAILED assertions:")
        for name in suite.failed_names():
            print(f"    ✗ {name}")
    else:
        print("  All assertions PASSED ✓")
    print("=" * 68)

    # ── Pipeline snapshot ─────────────────────────────────────────────────────
    print("\n── Pipeline output snapshot ──────────────────────────────────────────")
    if response is not None:
        w   = response.wellness
        ins = response.insurance
        cmp = response.compliance
        print(f"  next_step       : {response.next_step.value}")
        print(f"  priority_gap    : {w.priority_gap.value if w else '—'}  "
              f"(score {w.risk_management if w else '—'})")
        print(f"  overall_score   : {w.overall_score if w else '—'}")
        if response.wealth:
            print(f"  wealth picks    : {len(response.wealth.picks)}")
            for i, p in enumerate(response.wealth.picks, 1):
                print(f"    {i}. {p.fund_name:<44} sharia={p.is_sharia}  "
                      f"score={p.match_score}")
        if ins:
            print(f"  trigger         : {ins.trigger.metric.value} ≥ "
                  f"{ins.trigger.threshold} {ins.trigger.unit} "
                  f"at {ins.trigger.kecamatan}")
            print(f"  payout/event    : Rp {ins.payout_per_event_idr:,}  "
                  f"({ins.payout_multiple:.0f}× daily earnings)")
            print(f"  premium/month   : Rp {ins.premium_idr:,}  "
                  f"(ratio {ins.premium_idr / ins.payout_per_event_idr:.3f})")
        if cmp:
            print(f"  compliance      : {cmp.status.value}")
            print(f"  disclaimers     : {len(cmp.disclaimers)}")
        print(f"  narrative       : {response.narrative[:100]}…")
    print()

    _write_results(suite, response, crashed=False, crash_tb="")
    print(f"Results written → {_RESULTS}")

    return 0 if suite.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
