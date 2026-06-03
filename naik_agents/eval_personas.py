"""Persona-suite evaluation for the offline heuristic scorer.

Runs the deterministic heuristic across the full persona suite, prints a score
table (all seven dimensions per persona), and checks that each persona's derived
``priority_gap`` matches the human-expected weakest dimension. Also runs focused
negation checks ("sudah punya asuransi" vs "tidak punya asuransi").

Run from the repo root:
    python agents/eval_personas.py
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
for p in (_ROOT, os.path.join(_ROOT, "api")):
    if p not in sys.path:
        sys.path.insert(0, p)

from naik_agents.diagnostic import _score_heuristic, run_diagnostic  # noqa: E402
from naik_agents.personas import persona_suite, _persona  # noqa: E402
from api.schemas import (  # noqa: E402
    RiskProfile, Transaction, TransactionCategory, TransactionDirection,
)

DIMS = [
    "diversification", "liquidity", "growth", "risk_management",
    "tax_efficiency", "emergency_fund", "behavioural_resilience",
]
SHORT = {
    "diversification": "divers", "liquidity": "liquid", "growth": "growth",
    "risk_management": "riskmgt", "tax_efficiency": "tax", "emergency_fund": "emerg",
    "behavioural_resilience": "behav",
}


def main() -> int:
    suite = persona_suite()
    ok = fail = 0

    # ---- score table ----
    header = f"{'persona':16s} " + " ".join(f"{SHORT[d]:>7s}" for d in DIMS) + "  -> priority_gap"
    print(header)
    print("-" * len(header))
    rows = []
    for inp, expected in suite:
        res = run_diagnostic(inp, force_heuristic=True)
        v = res.vector
        scores = {d: getattr(v, d) for d in DIMS}
        gap = v.priority_gap.value
        rows.append((inp.user_id, scores, gap, expected))
        cells = " ".join(f"{scores[d]:7.1f}" for d in DIMS)
        if expected is None:
            flag = ""
        elif isinstance(expected, set):
            flag = "" if gap in expected else f"  [exp one of {sorted(expected)}]"
        else:
            flag = "" if gap == expected else f"  [exp {expected}]"
        print(f"{inp.user_id:16s} {cells}  -> {gap}{flag}")

    # ---- assertions ----
    print("\nChecks:")

    def check(name, cond, detail=""):
        nonlocal ok, fail
        mark = "PASS" if cond else "FAIL"
        ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
        print(f"  {mark}  {name}" + (f"  — {detail}" if detail else ""))

    for uid, scores, gap, expected in rows:
        if expected is None:
            lowest = min(scores.values())
            check(f"{uid}: balanced persona has no collapse (min >= 30)",
                  lowest >= 30.0, f"min={lowest:.1f} ({gap})")
        elif isinstance(expected, set):
            check(f"{uid}: priority_gap in {sorted(expected)}", gap in expected,
                  f"got {gap}")
        else:
            check(f"{uid}: priority_gap == {expected}", gap == expected,
                  f"got {gap}")

    # ---- focused negation / polarity tests ----
    print("\nNegation & polarity:")
    D = TransactionDirection.DEBIT
    C = TransactionDirection.CREDIT
    Cat = TransactionCategory

    def mini(transcript):
        txns = [Transaction(transaction_id=f"n{i}", timestamp=__import__("datetime").datetime(
            2026, 1, i + 1, tzinfo=__import__("datetime").timezone.utc),
            amount_idr=a, direction=d, category=c)
            for i, (a, d, c) in enumerate([
                (4_000_000, C, Cat.INCOME), (1_000_000, D, Cat.FOOD_BEVERAGE)])]
        return _persona("t", 30, 8_000_000, "Tebet", RiskProfile.MODERATE, 1, False,
                        transcript, txns)

    rm_neg = _score_heuristic(mini("saya tidak punya asuransi sama sekali"))["risk_management"]
    rm_pos = _score_heuristic(mini("saya sudah punya asuransi lengkap"))["risk_management"]
    check("'tidak punya asuransi' scores LOWER than 'sudah punya asuransi'",
          rm_neg < rm_pos, f"neg={rm_neg:.1f} vs pos={rm_pos:.1f}")
    check("'tidak punya asuransi' reads as weak (< 50)", rm_neg < 50.0, f"{rm_neg:.1f}")
    check("'sudah punya asuransi' reads as strong (> 55)", rm_pos > 55.0, f"{rm_pos:.1f}")

    gr_neg = _score_heuristic(mini("saya belum pernah investasi"))["growth"]
    gr_pos = _score_heuristic(mini("saya rutin investasi di reksa dana saham"))["growth"]
    check("'belum pernah investasi' scores LOWER on growth than active investing",
          gr_neg < gr_pos, f"neg={gr_neg:.1f} vs pos={gr_pos:.1f}")

    # no-transcript path: transactions only must still produce a valid vector
    tx_only = _persona("txonly", 30, 8_000_000, "Tebet", RiskProfile.MODERATE, 1, False, "",
                       [Transaction(transaction_id="x1", timestamp=__import__("datetime").datetime(
                           2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
                           amount_idr=4_000_000, direction=C, category=Cat.INCOME),
                        Transaction(transaction_id="x2", timestamp=__import__("datetime").datetime(
                           2026, 1, 2, tzinfo=__import__("datetime").timezone.utc),
                           amount_idr=1_000_000, direction=D, category=Cat.INVESTMENT)])
    v_txonly = run_diagnostic(tx_only, force_heuristic=True).vector
    check("transactions-only input yields a valid vector",
          0 <= v_txonly.overall_score <= 100, f"overall={v_txonly.overall_score}")

    total_expected = sum(1 for _, e in suite if e is not None)
    matched = sum(
        1 for uid, s, g, e in rows
        if e is not None and (g in e if isinstance(e, set) else g == e)
    )
    print(f"\nPriority-gap match: {matched}/{total_expected} personas")
    print(f"RESULT: {ok} passed, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
