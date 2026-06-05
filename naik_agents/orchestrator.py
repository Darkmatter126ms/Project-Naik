"""Naik orchestrator — the four-agent pipeline behind ``run_naik``.

    run_naik(DiagnosticInput) -> FinalResponse

Flow (build plan):
    1. diagnostic        runs first and alone — everything downstream needs the
                         WellnessVector and the priority gap.
    2. wealth ∥ insurance run concurrently via ``asyncio.gather`` — they share no
                         state, so they fire together. This is genuine agentic
                         parallelism (real concurrency for the agents' model-path
                         network calls), not sequential prompting dressed up.
    3. compliance        runs last as the OJK gate, rewriting the user-facing copy
                         and emitting the verdict.
    4. assembly          folds the compliance-rewritten artefacts into a validated
                         FinalResponse with a single next_step.

The agents are synchronous functions, so we run them in worker threads via
``asyncio.to_thread`` and gather the two parallel ones. ``run_naik`` is a
synchronous entry point (what the smoke test and CLI call) wrapping an async
core; it is also safe to call from inside an existing event loop (Flask async
view, the Realtime voice loop) — see the running-loop guard below.

The orchestrator resolves the halal decision once and threads it consistently
into both the wealth agent (``sharia_only``) and the compliance gate
(``halal_investor``), so the two never disagree about whether the user is a
sharia investor.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Optional

try:  # deployed import style
    from api.schemas import (
        ComplianceStatus,
        DiagnosticInput,
        FinalResponse,
        NextStep,
        WellnessDimension,
        WellnessVector,
    )
    from naik_agents.compliance import ComplianceResult, run_compliance
    from naik_agents.diagnostic import run_diagnostic
    from naik_agents.insurance import run_insurance
    from naik_agents.wealth import resolve_sharia_only, run_wealth
except ImportError:  # pragma: no cover - script/direct execution fallback
    import sys

    _HERE = os.path.dirname(__file__)
    sys.path.insert(0, os.path.join(_HERE, ".."))
    sys.path.insert(0, os.path.join(_HERE, "..", "api"))
    from schemas import (  # type: ignore
        ComplianceStatus,
        DiagnosticInput,
        FinalResponse,
        NextStep,
        WellnessDimension,
        WellnessVector,
    )
    from compliance import ComplianceResult, run_compliance  # type: ignore
    from diagnostic import run_diagnostic  # type: ignore
    from insurance import run_insurance  # type: ignore
    from wealth import resolve_sharia_only, run_wealth  # type: ignore


# --------------------------------------------------------------------------- #
# Bahasa narrative                                                            #
# --------------------------------------------------------------------------- #

_GAP_PHRASE_ID: dict[WellnessDimension, str] = {
    WellnessDimension.DIVERSIFICATION: "diversifikasi portofolio",
    WellnessDimension.LIQUIDITY: "likuiditas (dana yang mudah dicairkan)",
    WellnessDimension.GROWTH: "pertumbuhan investasi",
    WellnessDimension.RISK_MANAGEMENT: "perlindungan terhadap risiko",
    WellnessDimension.TAX_EFFICIENCY: "efisiensi pajak",
    WellnessDimension.EMERGENCY_FUND: "dana darurat",
    WellnessDimension.BEHAVIOURAL_RESILIENCE: "ketahanan keuangan",
}


def _narrative_id(
    wellness: WellnessVector,
    wealth_rationale: Optional[str],
    insurance_description: Optional[str],
) -> str:
    """Assemble the user-facing Bahasa summary from the (rewritten) pieces."""
    gap = _GAP_PHRASE_ID.get(wellness.priority_gap, wellness.priority_gap.value)
    parts = [
        f"Berdasarkan pola transaksi dan profil Anda, "
        f"{gap} adalah prioritas utama yang perlu ditangani sekarang."
    ]
    if wealth_rationale:
        parts.append(wealth_rationale)
    if insurance_description:
        parts.append(insurance_description)
    parts.append(
        "Semua ini adalah panduan umum; setiap transaksi memerlukan konfirmasi "
        "manual dari Anda."
    )
    return " ".join(parts)


def _decide_next_step(
    status: ComplianceStatus, has_wealth: bool, has_insurance: bool
) -> NextStep:
    """Pick the single action, consistent with the FinalResponse attachments."""
    if status in (ComplianceStatus.NEEDS_HUMAN_REVIEW, ComplianceStatus.REJECTED):
        return NextStep.ESCALATE_TO_HUMAN
    if has_wealth and has_insurance:
        return NextStep.CONFIRM_BOTH
    if has_wealth:
        return NextStep.CONFIRM_INVESTMENT
    if has_insurance:
        return NextStep.CONFIRM_INSURANCE
    return NextStep.REVIEW_ONLY


# --------------------------------------------------------------------------- #
# Assembly                                                                    #
# --------------------------------------------------------------------------- #


def _assemble(
    inp: DiagnosticInput, wellness: WellnessVector, comp: ComplianceResult
) -> FinalResponse:
    """Fold the compliance-rewritten artefacts into a validated FinalResponse."""
    wealth_reco = comp.wealth                # compliance-rewritten (or None)
    quote = comp.insurance                   # structured, unchanged (or None)
    next_step = _decide_next_step(
        comp.verdict.status, wealth_reco is not None, quote is not None
    )
    narrative = _narrative_id(
        wellness,
        wealth_reco.rationale if wealth_reco is not None else None,
        comp.insurance_description,
    )
    return FinalResponse(
        request_id=f"naik-{uuid.uuid4().hex[:12]}",
        user_id=inp.user_id,
        wellness=wellness,
        wealth=wealth_reco,
        insurance=quote,
        compliance=comp.verdict,
        narrative=narrative,
        next_step=next_step,
        disclaimers=comp.verdict.disclaimers,
    )


# --------------------------------------------------------------------------- #
# Async core                                                                  #
# --------------------------------------------------------------------------- #


async def run_naik_async(
    inp: DiagnosticInput,
    *,
    sharia_only: Optional[bool] = None,
    model: Optional[str] = None,
    force_heuristic: bool = False,
) -> FinalResponse:
    """Async pipeline: diagnostic → (wealth ∥ insurance) → compliance → assemble.

    Args:
        inp: the user's intake.
        sharia_only: force the halal filter; when None it is inferred from the
            user's goals/transcript and threaded into both wealth and compliance.
        model: override model name for every agent's model path.
        force_heuristic: run every agent's deterministic path (CI/offline/demo).
    """
    # 1. Diagnostic first (downstream depends on the vector). In a thread so a
    #    model-path network call never blocks the event loop.
    diag = await asyncio.to_thread(
        run_diagnostic, inp, model=model, force_heuristic=force_heuristic
    )
    wellness = diag.vector

    # Resolve halal once; thread it into wealth and compliance identically.
    halal = resolve_sharia_only(inp, sharia_only)

    # 2. Wealth ∥ insurance — genuinely concurrent. return_exceptions so one
    #    agent failing degrades the response instead of killing it.
    wealth_res, ins_res = await asyncio.gather(
        asyncio.to_thread(
            run_wealth, wellness, inp,
            sharia_only=halal, model=model, force_heuristic=force_heuristic,
        ),
        asyncio.to_thread(
            run_insurance, wellness, inp,
            model=model, force_heuristic=force_heuristic,
        ),
        return_exceptions=True,
    )
    wealth_reco = None if isinstance(wealth_res, BaseException) else wealth_res.recommendation
    quote = None if isinstance(ins_res, BaseException) else ins_res.quote
    ins_description = None if isinstance(ins_res, BaseException) else ins_res.bahasa_description

    # 3. Compliance gate last — rewrites copy, emits the verdict.
    comp = run_compliance(
        wealth=wealth_reco,
        insurance=quote,
        insurance_description=ins_description,
        wellness=wellness,
        inp=inp,
        halal_investor=halal,
    )

    # 4. Assemble.
    return _assemble(inp, wellness, comp)


# --------------------------------------------------------------------------- #
# Sync entry point                                                            #
# --------------------------------------------------------------------------- #


def run_naik(
    inp: DiagnosticInput,
    *,
    sharia_only: Optional[bool] = None,
    model: Optional[str] = None,
    force_heuristic: bool = False,
) -> FinalResponse:
    """Run the full Naik pipeline and return a validated :class:`FinalResponse`.

    Synchronous entry point (what the smoke test and CLI call). Safe to call
    from outside or inside a running event loop: with no loop we use
    ``asyncio.run``; inside one we run the async core on a dedicated thread so we
    never call ``asyncio.run`` from within a live loop.
    """
    coro_kwargs = dict(sharia_only=sharia_only, model=model, force_heuristic=force_heuristic)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_naik_async(inp, **coro_kwargs))

    # A loop is already running on this thread — offload to a worker thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(run_naik_async(inp, **coro_kwargs))).result()


__all__ = ["run_naik", "run_naik_async"]
