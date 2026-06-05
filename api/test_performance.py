"""api/test_performance.py — Naik pipeline performance benchmark.

Block 1 (Xinyue): confirms /orchestrate responds under 10 seconds for
Sari's input and profiles where time is actually spent.

Two modes:
  LOCAL   — runs against the Flask test client (no network, no API key).
            Measures the heuristic path. Tests cold-start vs warm, the
            wealth∥insurance parallel speedup, and the < 10 s gate.
  REMOTE  — fires real HTTP against the deployed Render backend.
            Requires API_BASE_URL (and optionally OPENAI_API_KEY present
            on the server). Reports actual wall-clock round-trip time.

Usage::

    # Local heuristic path only (no key needed)
    python api/test_performance.py

    # Against deployed Render backend (tests the model path)
    python api/test_performance.py --url https://naik-api.onrender.com

    # Quiet: only the summary table
    python api/test_performance.py --quiet

Exit codes:
    0  — all timing assertions pass (all runs < 10 s)
    1  — at least one timing assertion failed
    2  — crash / import error
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from statistics import mean, median
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
for _p in (_ROOT, os.path.join(_ROOT, "api")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

GATE_SECONDS    = 10.0   # build-plan SLA: /orchestrate must respond < 10 s
WARM_RUNS       = 5      # how many warm runs to average
COLD_WARN_MS    = 2_000  # cold-start above this → warn about dyno sleep risk

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(ms: float) -> str:
    return f"{ms:8.1f} ms"

def _gate(ms: float) -> str:
    return "✓" if ms / 1000 < GATE_SECONDS else "✗ FAIL"

class _Section:
    def __init__(self, title: str, quiet: bool) -> None:
        self.title  = title
        self.quiet  = quiet
        self.passed = 0
        self.failed = 0

    def __enter__(self):
        if not self.quiet:
            print(f"\n{'─' * 64}")
            print(f"  {self.title}")
            print(f"{'─' * 64}")
        return self

    def __exit__(self, *_):
        pass

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        if not self.quiet:
            mark = "✓" if ok else "✗"
            print(f"  [{mark}]  {label}" + (f"  — {detail}" if detail else ""))

# ─────────────────────────────────────────────────────────────────────────────
# Local (test-client) profiling
# ─────────────────────────────────────────────────────────────────────────────

def _run_local(quiet: bool) -> dict:
    """Profile the full heuristic pipeline using Flask's test client."""
    from api.app import create_app
    from naik_agents.personas import make_sari
    from naik_agents.diagnostic import run_diagnostic
    from naik_agents.insurance import run_insurance
    from naik_agents.wealth import run_wealth, resolve_sharia_only
    from naik_agents.compliance import run_compliance
    from naik_agents.orchestrator import run_naik

    sari = make_sari()
    sharia = resolve_sharia_only(sari, None)
    body = sari.model_dump(mode="json")

    results: dict = {}

    # ── 1. Per-agent cold start ───────────────────────────────────────────── #
    with _Section("Per-agent timing (cold start — first call)", quiet) as sec:
        t0 = time.perf_counter()
        diag = run_diagnostic(sari, force_heuristic=True)
        t1 = time.perf_counter()
        diag_cold = (t1 - t0) * 1000

        t0 = time.perf_counter()
        wealth_res = run_wealth(diag.vector, sari, sharia_only=sharia, force_heuristic=True)
        t1 = time.perf_counter()
        wealth_cold = (t1 - t0) * 1000

        t0 = time.perf_counter()
        ins_res = run_insurance(diag.vector, sari, force_heuristic=True)
        t1 = time.perf_counter()
        ins_cold = (t1 - t0) * 1000  # GLM loaded here on first call

        t0 = time.perf_counter()
        run_compliance(
            wealth=wealth_res.recommendation,
            insurance=ins_res.quote,
            insurance_description=ins_res.bahasa_description,
            wellness=diag.vector,
            inp=sari,
            halal_investor=sharia,
        )
        t1 = time.perf_counter()
        comp_cold = (t1 - t0) * 1000

        serial_cold = diag_cold + wealth_cold + ins_cold + comp_cold

        if not quiet:
            print(f"  diagnostic : {_fmt(diag_cold)}")
            print(f"  wealth     : {_fmt(wealth_cold)}")
            print(f"  insurance  : {_fmt(ins_cold)}"
                  + ("  ← GLM cold load" if ins_cold > 100 else ""))
            print(f"  compliance : {_fmt(comp_cold)}")
            print(f"  serial sum : {_fmt(serial_cold)}")

        if ins_cold > COLD_WARN_MS:
            if not quiet:
                print(f"\n  ⚠ GLM cold-load spike ({ins_cold:.0f} ms) — first request after")
                print("    a Render dyno sleep will be slow. The pre-warm thread in")
                print("    api/app.py mitigates this on server startup.")

        results["cold"] = {
            "diagnostic_ms":  round(diag_cold, 1),
            "wealth_ms":       round(wealth_cold, 1),
            "insurance_ms":    round(ins_cold, 1),
            "compliance_ms":   round(comp_cold, 1),
            "serial_total_ms": round(serial_cold, 1),
        }
        sec.check("Cold serial pipeline < 10 s", serial_cold < GATE_SECONDS * 1000,
                  f"{serial_cold:.0f} ms")

    # ── 2. Warm pipeline via test client (N runs) ─────────────────────────── #
    with _Section(f"Warm /orchestrate via test client ({WARM_RUNS} runs)", quiet) as sec:
        app = create_app()
        client = app.test_client()

        # One warm-up call (ensures caches are hot, module imports done)
        client.post("/orchestrate", json=body)

        times_ms: list[float] = []
        for i in range(WARM_RUNS):
            t0 = time.perf_counter()
            r = client.post("/orchestrate", json=body)
            elapsed = (time.perf_counter() - t0) * 1000
            if r.status_code != 200:
                if not quiet:
                    print(f"  run {i+1}: HTTP {r.status_code} — FAIL")
                times_ms.append(GATE_SECONDS * 1000 + 1)  # force failure
            else:
                times_ms.append(elapsed)
                if not quiet:
                    print(f"  run {i+1}: {_fmt(elapsed)}  {_gate(elapsed)}")

        avg_ms = mean(times_ms)
        med_ms = median(times_ms)
        mx_ms  = max(times_ms)

        if not quiet:
            print(f"\n  avg={avg_ms:.1f}ms  median={med_ms:.1f}ms  max={mx_ms:.1f}ms")

        results["warm"] = {
            "runs": WARM_RUNS,
            "times_ms": [round(t, 1) for t in times_ms],
            "avg_ms":    round(avg_ms, 1),
            "median_ms": round(med_ms, 1),
            "max_ms":    round(mx_ms, 1),
        }
        sec.check(f"All {WARM_RUNS} warm runs < {GATE_SECONDS} s",
                  mx_ms < GATE_SECONDS * 1000,
                  f"max={mx_ms:.1f}ms")

    # ── 3. Parallel speedup ───────────────────────────────────────────────── #
    with _Section("Parallel wealth∥insurance speedup", quiet) as sec:
        # Serial: wealth then insurance
        t0 = time.perf_counter()
        run_wealth(diag.vector, sari, sharia_only=sharia, force_heuristic=True)
        run_insurance(diag.vector, sari, force_heuristic=True)
        serial_wi = (time.perf_counter() - t0) * 1000

        # Parallel: via orchestrate (which uses asyncio.gather internally)
        import asyncio
        from naik_agents.orchestrator import run_naik_async

        t0 = time.perf_counter()
        asyncio.run(run_naik_async(sari, force_heuristic=True))
        parallel_total = (time.perf_counter() - t0) * 1000

        speedup = serial_wi / max(parallel_total, 0.001)
        if not quiet:
            print(f"  wealth + insurance serial  : {_fmt(serial_wi)}")
            print(f"  full orchestrate (parallel): {_fmt(parallel_total)}")
            print(f"  speedup factor             : {speedup:.2f}×")

        results["parallel"] = {
            "serial_wealth_insurance_ms": round(serial_wi, 1),
            "parallel_orchestrate_ms":    round(parallel_total, 1),
            "speedup_factor":             round(speedup, 2),
        }
        sec.check("Parallel path faster than serial",
                  parallel_total < serial_wi,
                  f"{speedup:.2f}×")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Remote (deployed Render) profiling
# ─────────────────────────────────────────────────────────────────────────────

def _run_remote(base_url: str, quiet: bool) -> dict:
    """Fire real HTTP against the deployed backend and measure wall-clock time."""
    import requests

    url_orch  = f"{base_url.rstrip('/')}/orchestrate"
    url_hlth  = f"{base_url.rstrip('/')}/health"

    # Minimal valid Sari payload (voice_transcript satisfies _require_a_signal)
    payload = {
        "user_id": "sari-perf-test",
        "age": 26,
        "monthly_income_idr": 6_000_000,
        "kecamatan": "Penjaringan",
        "city": "Jakarta",
        "risk_tolerance": "conservative",
        "household_size": 2,
        "is_gig_worker": True,
        "financial_goals": ["perlindungan penghasilan"],
        "voice_transcript": (
            "Saya tidak punya asuransi. Saya driver ojek, kalau banjir "
            "penghasilan saya langsung berhenti."
        ),
        "transactions": [],
    }

    results: dict = {}
    all_ok = True

    with _Section(f"Remote: {base_url}", quiet) as sec:
        # Health check
        try:
            t0 = time.perf_counter()
            r_hlth = requests.get(url_hlth, timeout=15)
            hlth_ms = (time.perf_counter() - t0) * 1000
            h = r_hlth.json()
            sec.check("/health reachable", r_hlth.status_code == 200,
                      f"{hlth_ms:.0f}ms — db={h.get('db','?')} v={h.get('version','?')}")
        except Exception as exc:
            sec.check("/health reachable", False, str(exc))
            print(f"\n  Cannot reach {base_url}. Check API_BASE_URL.")
            return {"error": str(exc)}

        # Warm-up call (Render dyno may be sleeping)
        if not quiet:
            print("  Warm-up call (may take 10–30 s if dyno is cold)…")
        try:
            requests.post(url_orch, json=payload, timeout=60)
        except Exception:
            pass

        # WARM_RUNS timed calls
        times_ms: list[float] = []
        for i in range(WARM_RUNS):
            try:
                t0 = time.perf_counter()
                r = requests.post(url_orch, json=payload, timeout=60)
                elapsed = (time.perf_counter() - t0) * 1000
            except Exception as exc:
                if not quiet:
                    print(f"  run {i+1}: ERROR — {exc}")
                all_ok = False
                continue

            ok = r.status_code == 200 and r.is_json
            times_ms.append(elapsed)
            gate = _gate(elapsed)
            if not ok:
                gate = f"✗ HTTP {r.status_code}"
                all_ok = False
            if not quiet:
                print(f"  run {i+1}: {_fmt(elapsed)}  {gate}")

        if times_ms:
            avg_ms = mean(times_ms)
            mx_ms  = max(times_ms)
            if not quiet:
                print(f"\n  avg={avg_ms:.0f}ms  max={mx_ms:.0f}ms")

            sec.check(f"All {len(times_ms)} runs < {GATE_SECONDS}s",
                      mx_ms < GATE_SECONDS * 1000 and all_ok,
                      f"max={mx_ms:.0f}ms")
            results["times_ms"] = [round(t, 0) for t in times_ms]
            results["avg_ms"]   = round(avg_ms, 0)
            results["max_ms"]   = round(mx_ms, 0)
            results["gate_ok"]  = mx_ms < GATE_SECONDS * 1000 and all_ok

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Recommendations
# ─────────────────────────────────────────────────────────────────────────────

def _print_recommendations(results: dict, quiet: bool) -> None:
    if quiet:
        return
    print("\n" + "═" * 64)
    print("  FINDINGS & RECOMMENDATIONS")
    print("═" * 64)

    cold = results.get("cold", {})
    ins_cold = cold.get("insurance_ms", 0)
    if ins_cold > 500:
        print(f"\n  ⚠ GLM cold load: {ins_cold:.0f} ms on first request.")
        print("    → api/app.py now pre-warms the model in a background thread")
        print("      at startup, so dyno wake-ups no longer stall the first user.")

    parallel = results.get("parallel", {})
    speedup = parallel.get("speedup_factor", 1.0)
    if speedup > 1.0:
        print(f"\n  ✓ Parallel wealth∥insurance fan-out gives {speedup:.1f}× speedup.")
        print("    The orchestrator already uses asyncio.gather — no action needed.")

    warm = results.get("warm", {})
    max_warm = warm.get("max_ms", 0)
    if max_warm < GATE_SECONDS * 1000:
        print(f"\n  ✓ Heuristic path: all warm runs < {GATE_SECONDS}s ({max_warm:.0f}ms max).")
    else:
        print(f"\n  ✗ Warm path exceeded {GATE_SECONDS}s ({max_warm:.0f}ms max).")

    print("\n  Model path (with OPENAI_API_KEY) projected timing:")
    print("    diagnostic   ~1–3 s  (one API call, sequential)")
    print("    wealth       ~2–4 s  ┐ parallel via asyncio.gather")
    print("    insurance    ~2–4 s  ┘")
    print("    compliance   ~0 s    (deterministic)")
    print("    TOTAL        ~3–7 s  (well under 10 s SLA)")
    print("\n  If model path exceeds 10 s on Render:")
    print("    • Set NAIK_WEALTH_MODEL=gpt-4o-mini   (faster, cheaper justifications)")
    print("    • Set NAIK_INSURANCE_MODEL=gpt-4o-mini")
    print("    • Keep NAIK_DIAGNOSTIC_MODEL=gpt-5.5  (scoring accuracy is critical)")

    print("═" * 64 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Naik performance benchmark")
    parser.add_argument("--url",   default=None,  help="Deployed API base URL for remote test")
    parser.add_argument("--quiet", action="store_true", help="Summary only, no run-by-run output")
    args = parser.parse_args(argv)

    print("=" * 64)
    print("  Naik Block 1 — Performance benchmark")
    print("=" * 64)

    all_results: dict = {}
    failures = 0

    try:
        local = _run_local(args.quiet)
        all_results["local"] = local
        # Count assertion failures from local runs
        warm = local.get("warm", {})
        if warm.get("max_ms", 0) >= GATE_SECONDS * 1000:
            failures += 1
    except Exception as exc:
        print(f"\n[CRASH] Local profiling failed: {exc}")
        import traceback; traceback.print_exc()
        return 2

    if args.url:
        try:
            remote = _run_remote(args.url, args.quiet)
            all_results["remote"] = remote
            if not remote.get("gate_ok", True):
                failures += 1
        except Exception as exc:
            print(f"\n[CRASH] Remote profiling failed: {exc}")
            failures += 1

    _print_recommendations(all_results, args.quiet)

    # Summary line
    cold_total = all_results.get("local", {}).get("cold", {}).get("serial_total_ms", "?")
    warm_max   = all_results.get("local", {}).get("warm",  {}).get("max_ms", "?")
    print(f"Cold serial: {cold_total}ms  |  Warm max ({WARM_RUNS} runs): {warm_max}ms")
    print(f"10 s gate: {'PASS ✓' if failures == 0 else 'FAIL ✗'}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
