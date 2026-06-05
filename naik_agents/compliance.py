"""Naik compliance agent — the final-stage OJK gate.

Reviews the upstream outputs (wellness, the :class:`WealthRecommendation`, the
:class:`InsuranceQuote` and its Bahasa copy) and emits a validated
:class:`ComplianceVerdict`, returning the user-facing text *rewritten* so it is
safe to surface under Indonesian (OJK) rules. Every output is framed as general
guidance, and any transaction is gated behind a human-confirmed step.

Unlike the wealth and insurance agents, the compliance agent is **deterministic
by design and has no model path.** A compliance control must be auditable and
must *guarantee* it catches prohibited language — you cannot delegate "did this
sentence promise a return?" to an LLM's judgement and still call it a gate. So
the four rules below are deterministic rewriters, and the verdict is computed,
not generated. (A model could later rephrase the already-sanitised text more
naturally, but the enforcement must remain deterministic.)

The four rules (build-plan contract):
  1. Rewrite specific return predictions  ("imbal hasil 18% per tahun" → hedged).
  2. Rewrite guarantee language           ("dijamin untung", "tanpa risiko" → hedged).
  3. Flag a sharia-non-compliant fund shown to a halal investor (→ human review).
  4. Require manual confirmation on every transaction step (always on).

Schema note: :class:`ComplianceVerdict` holds the *decision* (status, flags,
disclaimers, rationale) but not the rewritten artefacts, so ``run_compliance``
returns a :class:`ComplianceResult` carrying the verdict together with the
rewritten :class:`WealthRecommendation` and the rewritten insurance Bahasa text;
the orchestrator folds those into ``FinalResponse``. The schema field is
``requires_human_confirmation`` (the plan's "human_confirmation_required"), and
it is always True.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

try:  # deployed import style
    from api.schemas import (
        ComplianceStatus,
        ComplianceVerdict,
        DiagnosticInput,
        FundPick,
        InsuranceQuote,
        WealthRecommendation,
        WellnessVector,
    )
    from naik_agents.wealth import resolve_sharia_only
except ImportError:  # pragma: no cover - script/direct execution fallback
    import sys

    _HERE = os.path.dirname(__file__)
    sys.path.insert(0, os.path.join(_HERE, ".."))
    sys.path.insert(0, os.path.join(_HERE, "..", "api"))
    from schemas import (  # type: ignore
        ComplianceStatus,
        ComplianceVerdict,
        DiagnosticInput,
        FundPick,
        InsuranceQuote,
        WealthRecommendation,
        WellnessVector,
    )
    from wealth import resolve_sharia_only  # type: ignore


# --------------------------------------------------------------------------- #
# Rule 1 + 2: prohibited-language rewriters                                   #
# --------------------------------------------------------------------------- #

# Compliant replacements (Bahasa). Each is a self-contained phrase so a rewrite
# never leaves broken grammar, and never re-matches its own pattern (idempotent).
_RETURN_REPLACEMENT = "berpotensi memberikan imbal hasil (kinerja masa lalu tidak menjamin hasil di masa depan)"
_GUARANTEE_REPLACEMENT = "berpotensi memberikan imbal hasil (tanpa jaminan)"
_NO_RISK_REPLACEMENT = "dengan risiko yang relatif lebih rendah (semua investasi tetap mengandung risiko)"

# Rule 1 — a forward-looking return claim: an optional modal, a return word, an
# optional qualifier, then a percentage (and optional per-period). The leading
# modal is consumed so the replacement reads grammatically.
_RETURN_PRED_RE = re.compile(
    r"(?:\b(?:akan|bisa|dapat|memberi(?:kan)?|menawarkan)\s+)?"
    r"\b(?:imbal\s+hasil|return|keuntungan|untung|profit|cuan|menghasilkan|"
    r"pertumbuhan|tumbuh|naik)\b\s*"
    r"(?:sekitar|kira-kira|kurang\s+lebih|hingga|sampai|mencapai|rata-rata|"
    r"sebesar|di\s+kisaran)?\s*"
    r"\d+(?:[.,]\d+)?\s*%"
    r"(?:\s*(?:per\s*tahun|setahun|per\s*bulan|sebulan|p\.?\s*a\.?|/\s*tahun))?",
    re.IGNORECASE,
)

# Expense-ratio / fee / inflation contexts that legitimately carry a percentage
# and must NOT be rewritten as a return prediction.
_FEE_CONTEXT = ("biaya", "pengelolaan", "rasio", "expense", "ratio", "fee", "inflasi", "pajak")

# Rule 2a — guarantee-of-return language.
_GUARANTEE_RE = re.compile(
    r"\b(?:di\s*jamin(?:kan)?|jaminan\s+(?:untung|keuntungan|imbal\s+hasil|hasil|profit|cuan)|"
    r"pasti\s+(?:untung|cuan|naik|menghasilkan|profit|berhasil|dapat\s+untung)|"
    r"guaranteed?)\b",
    re.IGNORECASE,
)
# Rule 2b — "no risk" claims.
_NO_RISK_RE = re.compile(
    r"\b(?:tanpa\s+risiko|bebas\s+risiko|nol\s+risiko|100\s*%\s*aman|risk[-\s]?free)\b",
    re.IGNORECASE,
)


def _rewrite_return_predictions(text: str) -> tuple[str, bool]:
    """Replace specific return predictions with hedged phrasing (Rule 1).

    Leaves expense-ratio / fee / inflation percentages untouched (those are not
    return claims) by checking the context immediately preceding each match.
    """
    changed = False

    def repl(m: re.Match) -> str:
        nonlocal changed
        pre = text[max(0, m.start() - 24):m.start()].lower()
        if any(k in pre for k in _FEE_CONTEXT):
            return m.group(0)  # a fee/inflation figure, not a return prediction
        changed = True
        return _RETURN_REPLACEMENT

    return _RETURN_PRED_RE.sub(repl, text), changed


def _rewrite_guarantees(text: str) -> tuple[str, bool]:
    """Replace guarantee and no-risk language with hedged phrasing (Rule 2).

    Leaves a legitimate deposit-insurance reference ("dijamin LPS") intact, and
    does not touch parametric-payout wording (e.g. "cair otomatis"), which the
    patterns never match.
    """
    changed = False

    def repl_guarantee(m: re.Match) -> str:
        nonlocal changed
        post = text[m.end():m.end() + 6].lower()
        if "lps" in post:  # "dijamin LPS" — a factual deposit-insurance statement
            return m.group(0)
        changed = True
        return _GUARANTEE_REPLACEMENT

    out = _GUARANTEE_RE.sub(repl_guarantee, text)

    def repl_no_risk(_m: re.Match) -> str:
        nonlocal changed
        changed = True
        return _NO_RISK_REPLACEMENT

    out = _NO_RISK_RE.sub(repl_no_risk, out)
    return out, changed


def sanitize_text(text: Optional[str]) -> tuple[Optional[str], bool, bool]:
    """Apply Rules 1 & 2 to one string.

    Returns (clean_text, return_rewritten, guarantee_rewritten). ``None`` passes
    through unchanged so optional fields are handled uniformly.
    """
    if not text:
        return text, False, False
    out, ret_changed = _rewrite_return_predictions(text)
    out, gtee_changed = _rewrite_guarantees(out)
    return out, ret_changed, gtee_changed


# --------------------------------------------------------------------------- #
# Rule 3: sharia suitability                                                  #
# --------------------------------------------------------------------------- #

_SHARIA_FLAG_NOTE = (
    " [PERLU TINJAUAN: dana ini belum tersertifikasi syariah dan tidak sesuai "
    "untuk investor syariah.]"
)


def _flag_sharia_noncompliance(
    wealth: WealthRecommendation, halal: bool
) -> tuple[WealthRecommendation, list[str]]:
    """Flag any non-sharia pick shown to a halal investor (Rule 3).

    Does not silently drop the pick — that would alter the recommendation
    invisibly. Instead it annotates the offending pick's rationale and returns
    the offending fund_ids so the verdict can escalate to human review.
    """
    if not halal:
        return wealth, []
    offending = [p.fund_id for p in wealth.picks if not p.is_sharia]
    if not offending:
        return wealth, []
    new_picks = [
        p.model_copy(update={"rationale": (p.rationale or "") + _SHARIA_FLAG_NOTE})
        if not p.is_sharia
        else p
        for p in wealth.picks
    ]
    return wealth.model_copy(update={"picks": new_picks}), offending


# --------------------------------------------------------------------------- #
# Result wrapper                                                              #
# --------------------------------------------------------------------------- #


@dataclass
class ComplianceResult:
    """The verdict plus the rewritten artefacts the orchestrator should surface.

    ``wealth`` and ``insurance_description`` are the *post-rewrite* copies; the
    ``InsuranceQuote`` itself carries no free text so it passes through unchanged
    (kept for a symmetric handoff). ``flags`` mirrors the verdict's flags for
    convenient assertions.
    """

    verdict: ComplianceVerdict
    wealth: Optional[WealthRecommendation] = None
    insurance: Optional[InsuranceQuote] = None
    insurance_description: Optional[str] = None
    flags: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Disclaimers (Bahasa, OJK general-guidance framing)                          #
# --------------------------------------------------------------------------- #

_DISCLAIMER_GENERAL = (
    "Ini adalah panduan umum, bukan nasihat keuangan yang dipersonalisasi, "
    "sesuai ketentuan OJK."
)
_DISCLAIMER_PAST_PERF = "Kinerja masa lalu tidak menjamin hasil di masa depan."
_DISCLAIMER_INVEST_RISK = (
    "Investasi reksa dana mengandung risiko; nilai investasi dapat naik atau turun."
)
# Rule 4 — the literal manual-confirmation requirement on every transaction step.
_DISCLAIMER_MANUAL_CONFIRM = (
    "Konfirmasi manual diperlukan sebelum melakukan transaksi apa pun."
)
_DISCLAIMER_PARAMETRIC = (
    "Asuransi parametrik membayar berdasarkan indeks cuaca BMKG, bukan penilaian "
    "kerugian individual."
)
_DISCLAIMER_REWRITTEN = (
    "Beberapa pernyataan telah disesuaikan agar tidak menjanjikan hasil atau "
    "jaminan tertentu."
)
_DISCLAIMER_SHARIA = (
    "Terdapat dana yang belum tersertifikasi syariah; perlu tinjauan sebelum "
    "ditawarkan kepada investor syariah."
)


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #


def run_compliance(
    *,
    wealth: Optional[WealthRecommendation] = None,
    insurance: Optional[InsuranceQuote] = None,
    insurance_description: Optional[str] = None,
    wellness: Optional[WellnessVector] = None,
    inp: Optional[DiagnosticInput] = None,
    halal_investor: Optional[bool] = None,
) -> ComplianceResult:
    """Run the OJK compliance gate over the upstream outputs.

    Args:
        wealth: the wealth recommendation to review/rewrite (Rules 1–3).
        insurance: the insurance quote (structured; passed through unchanged).
        insurance_description: the insurance Bahasa copy to review/rewrite
            (Rules 1–2; parametric-payout wording is preserved).
        wellness: the diagnostic output, recorded as reviewed.
        inp: persona context. Used to infer halal-investor status for Rule 3
            (via the wealth agent's ``resolve_sharia_only``) and for the user id.
        halal_investor: explicit halal flag; overrides inference when given.

    Returns:
        A :class:`ComplianceResult` with a validated verdict and the rewritten
        artefacts. ``requires_human_confirmation`` is always True (Rule 4) and
        ``is_general_guidance`` is always True (schema invariant).
    """
    reviewed: list[str] = []
    flags: list[str] = []
    return_rewritten = False
    guarantee_rewritten = False

    if wellness is not None:
        reviewed.append("wellness")

    # --- Rules 1 & 2 on the wealth rationales ---------------------------------
    rewritten_wealth = wealth
    if wealth is not None:
        reviewed.append("wealth")
        overall, r1, g1 = sanitize_text(wealth.rationale)
        return_rewritten |= r1
        guarantee_rewritten |= g1
        new_picks: list[FundPick] = []
        for pick in wealth.picks:
            clean, r2, g2 = sanitize_text(pick.rationale)
            return_rewritten |= r2
            guarantee_rewritten |= g2
            new_picks.append(pick.model_copy(update={"rationale": clean}) if (r2 or g2) else pick)
        rewritten_wealth = wealth.model_copy(
            update={"rationale": overall or wealth.rationale, "picks": new_picks}
        )

    # --- Rule 3 on the (rewritten) wealth picks -------------------------------
    halal = halal_investor if halal_investor is not None else (
        resolve_sharia_only(inp, None) if inp is not None else False
    )
    sharia_offending: list[str] = []
    if rewritten_wealth is not None:
        rewritten_wealth, sharia_offending = _flag_sharia_noncompliance(rewritten_wealth, halal)

    # --- Rules 1 & 2 on the insurance Bahasa copy -----------------------------
    rewritten_description = insurance_description
    if insurance is not None:
        reviewed.append("insurance")
    if insurance_description is not None:
        rewritten_description, r3, g3 = sanitize_text(insurance_description)
        return_rewritten |= r3
        guarantee_rewritten |= g3

    # --- Flags + status -------------------------------------------------------
    if return_rewritten:
        flags.append("return_prediction_rewritten")
    if guarantee_rewritten:
        flags.append("guarantee_language_rewritten")
    if sharia_offending:
        flags.append("sharia_non_compliant_fund")

    if sharia_offending:
        status = ComplianceStatus.NEEDS_HUMAN_REVIEW
    elif return_rewritten or guarantee_rewritten:
        status = ComplianceStatus.APPROVED_WITH_CONDITIONS
    else:
        status = ComplianceStatus.APPROVED

    # --- Disclaimers (Rule 4 always included) ---------------------------------
    disclaimers = [_DISCLAIMER_GENERAL, _DISCLAIMER_MANUAL_CONFIRM]
    if wealth is not None:
        disclaimers += [_DISCLAIMER_PAST_PERF, _DISCLAIMER_INVEST_RISK]
    if insurance is not None:
        disclaimers.append(_DISCLAIMER_PARAMETRIC)
    if return_rewritten or guarantee_rewritten:
        disclaimers.append(_DISCLAIMER_REWRITTEN)
    if sharia_offending:
        disclaimers.append(_DISCLAIMER_SHARIA)

    # --- Rationale (Bahasa) ---------------------------------------------------
    parts = [
        "Semua keluaran ditinjau dan dibingkai sebagai panduan umum sesuai "
        "ketentuan OJK."
    ]
    if return_rewritten or guarantee_rewritten:
        parts.append(
            "Beberapa pernyataan imbal hasil atau jaminan telah disesuaikan agar "
            "tidak menjanjikan hasil tertentu."
        )
    if sharia_offending:
        parts.append(
            "Ditemukan dana yang belum tersertifikasi syariah untuk investor "
            "syariah, sehingga ditandai untuk tinjauan manusia."
        )
    parts.append("Setiap transaksi tetap memerlukan konfirmasi manual dari pengguna.")
    rationale = " ".join(parts)

    user_id = (
        (wealth.user_id if wealth is not None else None)
        or (insurance.user_id if insurance is not None else None)
        or (inp.user_id if inp is not None else None)
        or "unknown"
    )

    verdict = ComplianceVerdict(
        verdict_id=f"compliance-{user_id}",
        status=status,
        is_general_guidance=True,           # schema invariant
        requires_human_confirmation=True,    # Rule 4 — always on
        reviewed=reviewed,
        flags=flags,
        disclaimers=disclaimers,
        rationale=rationale,
    )

    return ComplianceResult(
        verdict=verdict,
        wealth=rewritten_wealth,
        insurance=insurance,
        insurance_description=rewritten_description,
        flags=flags,
    )


__all__ = [
    "sanitize_text",
    "run_compliance",
    "ComplianceResult",
]
