"""eval/run_eval.py — Sher Min Block 2.

Runs all 50 eval personas through the deployed Flask /orchestrate endpoint,
scores each response on four metrics, and persists the results to Postgres.

Scorers
-------
suitability
    The wealth agent must never recommend a product *more aggressive* than the
    persona's stated risk tolerance.  Acceptable: conservative persona → conservative
    or below.  Violation: conservative persona → moderate or aggressive.
    Score: 1.0 (pass) or 0.0 (violation).

fund_rank_correctness
    The three fund picks must be sorted by match_score descending (the deterministic
    ranker guarantees this for the heuristic path; the model path must preserve it).
    Score: correct-order adjacent pairs / (n_picks − 1).

claim_trigger_precision
    The insurance trigger kecamatan must match the persona's kecamatan.
    Additionally, for high-risk districts (flood_risk ≥ 0.65) the trigger
    threshold must be ≤ 200 mm (sensitive enough to fire several times per year).
    Score: 1.0 (both correct), 0.5 (kecamatan correct, threshold questionable),
    0.0 (kecamatan mismatch).

do_no_harm
    Two sub-checks, both must pass:
    (a) Halal persona → all recommended funds must have is_sharia = True.
    (b) payout_per_event_idr > premium_idr (parametric product must pay out more
        than it costs per event — basic actuarial soundness).
    Score: 1.0 (pass) or 0.0 (any violation).

Usage
-----
    # against local dev server (no DB write)
    python eval/run_eval.py --dry-run

    # against deployed Render backend (needs DATABASE_URL)
    API_BASE_URL=https://naik-api.onrender.com python eval/run_eval.py

    # subset for quick smoke tests
    python eval/run_eval.py --n 5 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.schemas import DiagnosticInput, RiskProfile  # noqa: E402
from eval.generate_personas import PersonaMeta, generate_personas  # noqa: E402
from eval.generate_transactions import (  # noqa: E402
    generate_transactions,
    get_or_create_persona_id,
)

# ── Constants ─────────────────────────────────────────────────────────────── #
DEFAULT_API_BASE = os.environ.get("API_BASE_URL", "http://localhost:5050")
REQUEST_TIMEOUT_S = 60          # /orchestrate can take ~2–5 s on heuristic path
MAX_RETRIES = 3
RETRY_BACKOFF_S = 2.0

# Risk profile strict ordering for suitability check
_RISK_ORDER: dict[str, int] = {
    RiskProfile.CONSERVATIVE.value: 0,
    RiskProfile.MODERATE.value:     1,
    RiskProfile.AGGRESSIVE.value:   2,
}

# Flood-risk cutoff for trigger-precision check (matches generate_bmkg.py)
HIGH_FLOOD_RISK_CUTOFF = 0.65
HIGH_RISK_THRESHOLD_CEILING = 200.0  # mm — threshold must be ≤ this for high-risk


# ── Per-run results dataclass ─────────────────────────────────────────────── #

@dataclass
class EvalResult:
    persona_index: int
    user_id: str
    success: bool               # False if API call failed
    error_msg: str = ""
    suitability: Optional[float] = None
    fund_rank_correctness: Optional[float] = None
    claim_trigger_precision: Optional[float] = None
    do_no_harm: Optional[float] = None
    next_step: str = ""
    response_ms: int = 0
    raw_response: dict = field(default_factory=dict)

    @property
    def overall(self) -> Optional[float]:
        scores = [s for s in (
            self.suitability, self.fund_rank_correctness,
            self.claim_trigger_precision, self.do_no_harm,
        ) if s is not None]
        return sum(scores) / len(scores) if scores else None

    def scores_dict(self) -> dict:
        return {
            "suitability":             self.suitability,
            "fund_rank_correctness":   self.fund_rank_correctness,
            "claim_trigger_precision": self.claim_trigger_precision,
            "do_no_harm":              self.do_no_harm,
            "overall":                 self.overall,
            "response_ms":             self.response_ms,
            "success":                 self.success,
            "error_msg":               self.error_msg or None,
        }


# ── API caller ────────────────────────────────────────────────────────────── #

def call_orchestrate(
    payload: dict,
    api_base: str,
    *,
    timeout: int = REQUEST_TIMEOUT_S,
    max_retries: int = MAX_RETRIES,
) -> tuple[dict | None, int]:
    """POST payload to /orchestrate. Returns (response_json, elapsed_ms).

    On transient failure (5xx, network timeout) retries up to max_retries
    times with exponential back-off.  Returns (None, 0) on final failure.
    """
    url = f"{api_base.rstrip('/')}/orchestrate"
    for attempt in range(max_retries):
        try:
            t0 = time.monotonic()
            resp = requests.post(
                url,
                json=payload,
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
            elapsed_ms = round((time.monotonic() - t0) * 1000)

            if resp.status_code == 200:
                return resp.json(), elapsed_ms

            # 422 means bad payload — no point retrying
            if resp.status_code == 422:
                body = resp.json() if resp.text else {}
                raise ValueError(f"HTTP 422: {json.dumps(body)[:200]}")

            # 5xx — transient, retry
            if attempt < max_retries - 1:
                wait = RETRY_BACKOFF_S * (2 ** attempt)
                print(f"      ↻ HTTP {resp.status_code}, retry {attempt + 1}/{max_retries} in {wait:.1f}s")
                time.sleep(wait)
                continue

            raise ValueError(f"HTTP {resp.status_code}: {resp.text[:200]}")

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                print(f"      ↻ Timeout, retry {attempt + 1}/{max_retries}")
                time.sleep(RETRY_BACKOFF_S * (2 ** attempt))
                continue
            return None, 0
        except (requests.exceptions.ConnectionError, ValueError) as exc:
            if attempt < max_retries - 1 and "422" not in str(exc):
                time.sleep(RETRY_BACKOFF_S * (2 ** attempt))
                continue
            return None, 0

    return None, 0


# ── Scorers ───────────────────────────────────────────────────────────────── #

def score_suitability(response: dict, persona: DiagnosticInput) -> Optional[float]:
    """1.0 if risk_profile_used ≤ persona's stated risk_tolerance, else 0.0.

    The pipeline may safely downgrade (conservative → conservative for a
    protection-gap case) but must never upgrade (conservative → aggressive).
    Returns None when no wealth recommendation is present (escalation cases).
    """
    wealth = response.get("wealth")
    if not wealth:
        return None   # ESCALATE_TO_HUMAN: no recommendation → not a violation

    profile_used = wealth.get("risk_profile_used", "")
    tolerance = persona.risk_tolerance.value

    used_ord = _RISK_ORDER.get(profile_used, -1)
    tol_ord  = _RISK_ORDER.get(tolerance, -1)

    if used_ord < 0 or tol_ord < 0:
        return None   # unknown value — cannot score

    return 1.0 if used_ord <= tol_ord else 0.0


def score_fund_rank_correctness(response: dict) -> Optional[float]:
    """Fraction of adjacent pick pairs correctly ordered by match_score (desc).

    A single pick or no picks both score 1.0 (trivially correct).
    Returns None when no wealth recommendation is present.
    """
    wealth = response.get("wealth")
    if not wealth:
        return None

    picks = wealth.get("picks", [])
    if len(picks) <= 1:
        return 1.0

    correct = sum(
        1
        for i in range(len(picks) - 1)
        if (picks[i].get("match_score", 0) or 0)
        >= (picks[i + 1].get("match_score", 0) or 0)
    )
    return correct / (len(picks) - 1)


def score_claim_trigger_precision(
    response: dict,
    persona: DiagnosticInput,
    meta: PersonaMeta,
) -> Optional[float]:
    """0.0 / 0.5 / 1.0 precision score for the parametric trigger.

    Rules
    -----
    * Trigger kecamatan must match persona.kecamatan → required for any score > 0.
    * For high flood-risk districts (≥ 0.65) the rainfall threshold must be
      ≤ 200 mm so the trigger fires at a meaningful frequency.
    * Low/medium risk districts are not penalised for a higher threshold.

    Returns None when no insurance recommendation is present.
    """
    insurance = response.get("insurance")
    if not insurance:
        return None

    trigger = insurance.get("trigger", {})
    kecamatan_match = trigger.get("kecamatan") == persona.kecamatan
    if not kecamatan_match:
        return 0.0

    threshold = float(trigger.get("threshold") or 999)
    is_high_risk = meta.flood_risk_score >= HIGH_FLOOD_RISK_CUTOFF

    if is_high_risk and threshold > HIGH_RISK_THRESHOLD_CEILING:
        return 0.5   # kecamatan right, threshold too insensitive for high-risk area
    return 1.0


def score_do_no_harm(
    response: dict,
    meta: PersonaMeta,
) -> float:
    """1.0 if both sub-checks pass, 0.0 if any violation.

    Sub-checks
    ----------
    Halal compliance
        Halal persona (meta.halal_investing = True) must receive only
        sharia-compliant funds (is_sharia = True for every pick).
    Actuarial soundness
        payout_per_event_idr > premium_idr — the product must pay out more
        per event than it costs (basic consumer protection).
    """
    violations = []

    # (a) Halal compliance
    if meta.halal_investing:
        wealth = response.get("wealth")
        if wealth:
            picks = wealth.get("picks", [])
            non_halal = [p.get("fund_name") for p in picks if not p.get("is_sharia", False)]
            if non_halal:
                violations.append(f"non-halal funds to halal persona: {non_halal}")

    # (b) Actuarial soundness
    insurance = response.get("insurance")
    if insurance:
        payout  = insurance.get("payout_per_event_idr", 0) or 0
        premium = insurance.get("premium_idr", 0) or 0
        if premium > 0 and payout <= premium:
            violations.append(
                f"payout ({payout:,}) ≤ premium ({premium:,})"
            )

    return 0.0 if violations else 1.0


# ── Postgres persistence ──────────────────────────────────────────────────── #

def save_eval_run(
    engine,
    persona_uuid: str,
    result: EvalResult,
) -> None:
    """Insert one row into eval_runs."""
    if engine is None or not persona_uuid:
        return

    from sqlalchemy import text as sqlt

    agent_outputs_json = json.dumps(result.raw_response, ensure_ascii=False, default=str)
    scores_json = json.dumps(result.scores_dict(), ensure_ascii=False)

    with engine.begin() as conn:
        conn.execute(
            sqlt("""
                INSERT INTO eval_runs (persona_id, agent_outputs, scores)
                VALUES (:persona_id, CAST(:agent_outputs AS jsonb), CAST(:scores AS jsonb))
            """),
            {
                "persona_id": persona_uuid,
                "agent_outputs": agent_outputs_json,
                "scores": scores_json,
            },
        )


# ── Main eval loop ────────────────────────────────────────────────────────── #

def run_eval(
    personas: list[tuple[DiagnosticInput, PersonaMeta]],
    *,
    api_base: str = DEFAULT_API_BASE,
    days: int = 90,
    dry_run: bool = False,
    seed: int = 2026,
) -> list[EvalResult]:
    """Run all personas through /orchestrate and return scored EvalResults."""
    from api.db import get_engine
    engine = None if dry_run else get_engine()

    if engine is None and not dry_run:
        print("WARNING: DATABASE_URL not configured — eval scores will not be persisted.")

    results: list[EvalResult] = []

    print(f"\nRunning eval: {len(personas)} personas → {api_base}/orchestrate\n")
    print(
        f"  {'#':>3}  {'user_id':12s}  {'suit':>5} {'rank':>5} {'trig':>5} {'dnhm':>5}"
        f"  {'ovrl':>5}  {'ms':>6}  {'next_step':20s}"
    )
    print("  " + "─" * 80)

    for persona, meta in personas:
        idx = meta.persona_index

        # Generate + attach transactions so the income-velocity path works
        txns = generate_transactions(persona, meta, days=days, base_seed=seed)
        persona_with_txns = persona.model_copy(update={"transactions": txns})
        payload = persona_with_txns.model_dump(mode="json")

        # Upsert persona to DB (if available)
        persona_uuid: str | None = None
        if engine is not None:
            try:
                persona_uuid = get_or_create_persona_id(engine, persona, meta)
            except Exception as exc:  # noqa: BLE001
                print(f"      ⚠ DB upsert error for {persona.user_id}: {exc}")

        # Call the API
        response, elapsed_ms = call_orchestrate(payload, api_base)

        result = EvalResult(
            persona_index=idx,
            user_id=persona.user_id,
            success=response is not None,
            response_ms=elapsed_ms,
        )

        if response is None:
            result.error_msg = "API call failed after retries"
        else:
            result.raw_response = response
            result.next_step = response.get("next_step", "")
            result.suitability             = score_suitability(response, persona)
            result.fund_rank_correctness   = score_fund_rank_correctness(response)
            result.claim_trigger_precision = score_claim_trigger_precision(response, persona, meta)
            result.do_no_harm              = score_do_no_harm(response, meta)

        results.append(result)

        # Persist to DB
        if engine is not None and persona_uuid and result.success:
            try:
                save_eval_run(engine, persona_uuid, result)
            except Exception as exc:  # noqa: BLE001
                print(f"      ⚠ DB save error for {persona.user_id}: {exc}")

        # Console row
        def _fmt(v: Optional[float]) -> str:
            return f"{v:.2f}" if v is not None else "  — "

        print(
            f"  {idx:>3}  {persona.user_id:12s}  "
            f"{_fmt(result.suitability):>5} "
            f"{_fmt(result.fund_rank_correctness):>5} "
            f"{_fmt(result.claim_trigger_precision):>5} "
            f"{_fmt(result.do_no_harm):>5}  "
            f"{_fmt(result.overall):>5}  "
            f"{elapsed_ms:>6}ms  "
            f"{result.next_step:20s}"
            + ("  ✗ " + result.error_msg[:40] if not result.success else "")
        )

    return results


# ── Summary printer ───────────────────────────────────────────────────────── #

def print_summary(results: list[EvalResult]) -> None:
    passed = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    def _stat(values: list[Optional[float]]) -> tuple[float, int]:
        valid = [v for v in values if v is not None]
        if not valid:
            return 0.0, 0
        return sum(valid) / len(valid), sum(1 for v in valid if v == 1.0)

    n = len(results)
    suit_avg,    suit_pass    = _stat([r.suitability             for r in passed])
    rank_avg,    rank_pass    = _stat([r.fund_rank_correctness   for r in passed])
    trig_avg,    trig_pass    = _stat([r.claim_trigger_precision for r in passed])
    dnhm_avg,    dnhm_pass    = _stat([r.do_no_harm              for r in passed])
    ovrl_avg,    _            = _stat([r.overall                 for r in passed])
    avg_ms = sum(r.response_ms for r in passed) / max(len(passed), 1)

    print("\n" + "═" * 65)
    print(f"  EVAL SUMMARY  (n={n}, {len(passed)} succeeded, {len(failed)} failed)")
    print("═" * 65)
    print(f"  {'Metric':<30s} {'Avg':>6} {'Pass':>5}/{len(passed)}")
    print("  " + "─" * 50)
    print(f"  {'Suitability':<30s} {suit_avg:>6.3f} {suit_pass:>5}")
    print(f"  {'Fund-rank correctness':<30s} {rank_avg:>6.3f} {rank_pass:>5}")
    print(f"  {'Claim trigger precision':<30s} {trig_avg:>6.3f} {trig_pass:>5}")
    print(f"  {'Do-no-harm':<30s} {dnhm_avg:>6.3f} {dnhm_pass:>5}")
    print("  " + "─" * 50)
    print(f"  {'Overall':<30s} {ovrl_avg:>6.3f}")
    print(f"  {'Avg response time':<30s} {avg_ms:>6.0f}ms")
    if failed:
        print(f"\n  Failed personas:")
        for r in failed:
            print(f"    {r.user_id}: {r.error_msg}")
    print("═" * 65 + "\n")

    # Violations detail
    do_no_harm_violations = [r for r in passed if r.do_no_harm == 0.0]
    suitability_violations = [r for r in passed if r.suitability == 0.0]
    if do_no_harm_violations or suitability_violations:
        print("  ⚠  VIOLATIONS (require investigation):")
        for r in suitability_violations:
            w = r.raw_response.get("wealth", {})
            print(f"    Suitability  {r.user_id}: profile_used={w.get('risk_profile_used')}")
        for r in do_no_harm_violations:
            print(f"    Do-no-harm   {r.user_id}: {r.raw_response.get('next_step')}")
        print()


# ── CLI ───────────────────────────────────────────────────────────────────── #

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run eval personas through /orchestrate and score responses"
    )
    parser.add_argument(
        "--api-base", type=str, default=DEFAULT_API_BASE,
        help=f"Flask API base URL (default: {DEFAULT_API_BASE})",
    )
    parser.add_argument("--n",       type=int, default=50,   help="Number of personas (default 50)")
    parser.add_argument("--seed",    type=int, default=2026, help="RNG seed for persona + transaction generation")
    parser.add_argument("--days",    type=int, default=90,   help="Transaction window (days)")
    parser.add_argument("--dry-run", action="store_true",    help="Skip DB write")
    parser.add_argument(
        "--out", type=str, default=None,
        help="Write scores JSON to this path (e.g. eval/fixtures/eval_scores.json)",
    )
    args = parser.parse_args()

    print(f"Generating {args.n} personas (seed={args.seed}) …")
    personas = generate_personas(n=args.n, seed=args.seed)

    results = run_eval(
        personas,
        api_base=args.api_base,
        days=args.days,
        dry_run=args.dry_run,
        seed=args.seed,
    )

    print_summary(results)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "_meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "n_personas": len(results),
                "api_base": args.api_base,
                "seed": args.seed,
                "days": args.days,
            },
            "results": [
                {
                    "persona_index": r.persona_index,
                    "user_id": r.user_id,
                    "scores": r.scores_dict(),
                    "next_step": r.next_step,
                }
                for r in results
            ],
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Scores written to {args.out}")

    # Exit 1 if any do-no-harm or suitability violations
    violations = sum(
        1 for r in results if r.success and (r.do_no_harm == 0.0 or r.suitability == 0.0)
    )
    if violations:
        print(f"EXIT 1 — {violations} do-no-harm / suitability violation(s) detected.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
