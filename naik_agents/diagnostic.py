"""Naik diagnostic agent.

Scores the seven financial-wellness dimensions of a :class:`WellnessVector` from
a Bahasa Indonesia voice transcript plus an anonymised Shopee transaction
history. Before the model call, CRRA utility weights are computed from the
persona's self-declared risk tolerance (see :mod:`agents.crra`) and passed as
context so the agent emphasises the gaps that matter most for that user.

Two execution paths, same output contract:

* **Model path** — when ``OPENAI_API_KEY`` is set, calls the OpenAI API with a
  strict JSON schema (structured output) and parses seven scores.
* **Heuristic path** — a deterministic local scorer used when no key is present
  (offline dev, CI, the hackathon's flaky wifi). It ports the dimension
  semantics from the Wealth-Wellness-Hub scoring model, reading signals from the
  transcript and transaction summary.

In both paths the seven scores are handed to ``WellnessVector.from_scores``,
which derives ``priority_gap`` as the genuinely lowest-scoring dimension and
validates the result. The agent never sets ``priority_gap`` itself, so the label
can never disagree with the data.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Optional

try:  # deployed import style
    from api.schemas import (
        DiagnosticInput,
        RiskProfile,
        Transaction,
        TransactionDirection,
        WellnessVector,
    )
    from naik_agents.crra import crra_weights_table, gamma_for
except ImportError:  # pragma: no cover - script/direct execution fallback
    import sys

    _HERE = os.path.dirname(__file__)
    sys.path.insert(0, os.path.join(_HERE, ".."))
    sys.path.insert(0, os.path.join(_HERE, "..", "api"))
    from schemas import (  # type: ignore
        DiagnosticInput,
        RiskProfile,
        Transaction,
        TransactionDirection,
        WellnessVector,
    )
    from crra import crra_weights_table, gamma_for  # type: ignore

DEFAULT_MODEL = os.environ.get("NAIK_DIAGNOSTIC_MODEL", "gpt-5.5")

# --------------------------------------------------------------------------- #
# System prompt                                                               #
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """\
You are Naik's financial-wellness diagnostic agent for Indonesian users. You \
score SEVEN wellness dimensions from a Bahasa Indonesia voice transcript and an \
anonymised Shopee transaction summary. You output ONLY structured JSON.

Each dimension is a float from 0 to 100 (higher = healthier). Score what the \
EVIDENCE supports; absence of any signal for a protective dimension is itself \
evidence of weakness, not a reason to default to a middling score.

DIMENSIONS (definitions are fixed — score these exact constructs):
- diversification: breadth across asset types / fund categories. One holding or \
none -> low. Several distinct types -> high.
- liquidity: share of wealth in readily-accessible cash. Little or no accessible \
cash -> low.
- growth: exposure to return-seeking (equity-like) assets appropriate to the \
user's horizon. No invested growth assets -> low.
- risk_management: adequacy of DOWNSIDE PROTECTION — insurance cover, income \
protection, buffers against shocks. No insurance and exposure to income shocks \
(e.g. gig/informal work, flood-prone area) -> LOW. This is about protection, \
NOT investment risk appetite.
- tax_efficiency: use of tax-advantaged vehicles where available. No evidence -> low-to-mid.
- emergency_fund: months of expenses held in reserve. Mentions of no savings / \
living payday-to-payday / cannot cover an emergency -> low.
- behavioural_resilience: consistency and discipline of saving/investing \
behaviour. Impulsive spending, abandoned investments, no routine -> low; regular \
contributions and a plan -> high.

CRRA CONTEXT: you are given per-dimension importance weights derived from the \
user's risk tolerance. Use them to weight your WRITTEN rationale and to break \
near-ties in emphasis. Do NOT let them override clear evidence: if the evidence \
shows a dimension is weak, score it weak regardless of its weight.

OUTPUT: JSON with keys diversification, liquidity, growth, risk_management, \
tax_efficiency, emergency_fund, behavioural_resilience (each 0-100 number) and \
rationale (one or two sentences in Bahasa Indonesia naming the single weakest \
area). Do NOT include a priority_gap field — it is derived downstream from your \
scores. Output JSON only, no prose, no code fences.
"""

# JSON schema for OpenAI structured output (seven scores + rationale).
_SCORE_PROPS = {
    name: {"type": "number", "minimum": 0, "maximum": 100}
    for name in (
        "diversification",
        "liquidity",
        "growth",
        "risk_management",
        "tax_efficiency",
        "emergency_fund",
        "behavioural_resilience",
    )
}
RESPONSE_JSON_SCHEMA = {
    "name": "wellness_scores",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {**_SCORE_PROPS, "rationale": {"type": "string"}},
        "required": [*_SCORE_PROPS.keys(), "rationale"],
    },
}


# --------------------------------------------------------------------------- #
# Transaction summarisation                                                   #
# --------------------------------------------------------------------------- #


def summarise_transactions(txns: list[Transaction]) -> str:
    """Produce a compact, model-friendly summary of the transaction history.

    Aggregates spend by category, total inflow/outflow, and a crude
    discretionary-share signal — enough for the agent to read behavioural
    patterns without dumping every row.
    """
    if not txns:
        return "No transaction history provided."

    inflow = sum(t.amount_idr for t in txns if t.direction is TransactionDirection.CREDIT)
    outflow = sum(t.amount_idr for t in txns if t.direction is TransactionDirection.DEBIT)
    by_cat: dict[str, int] = {}
    for t in txns:
        if t.direction is TransactionDirection.DEBIT:
            by_cat[t.category.value] = by_cat.get(t.category.value, 0) + t.amount_idr

    top = sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)[:6]
    invest = sum(v for c, v in by_cat.items() if c in ("investment", "insurance"))
    net = inflow - outflow

    lines = [
        f"{len(txns)} transactions. Total inflow Rp {inflow:,}, outflow Rp {outflow:,}, "
        f"net Rp {net:,}.",
        "Top spend categories (Rp): "
        + ", ".join(f"{c}={v:,}" for c, v in top)
        + ".",
        f"Spend on investment+insurance: Rp {invest:,}"
        + (" (none)" if invest == 0 else "")
        + ".",
    ]
    return " ".join(lines)


def _build_user_message(inp: DiagnosticInput) -> str:
    """Assemble the user-turn content: profile + CRRA weights + signals."""
    weights_block = crra_weights_table(inp.risk_tolerance)
    profile = (
        f"User profile: age {inp.age}, monthly income Rp {inp.monthly_income_idr:,}, "
        f"kecamatan {inp.kecamatan}"
        + (f" ({inp.city})" if inp.city else "")
        + f", household size {inp.household_size}, "
        f"gig/informal worker: {'yes' if inp.is_gig_worker else 'no'}, "
        f"self-declared risk tolerance: {inp.risk_tolerance.value}."
    )
    goals = (
        "Stated goals: " + "; ".join(inp.financial_goals) + "."
        if inp.financial_goals
        else "Stated goals: none provided."
    )
    transcript = (
        f'Voice transcript (Bahasa Indonesia): "{inp.voice_transcript.strip()}"'
        if inp.voice_transcript.strip()
        else "Voice transcript: none provided."
    )
    tx_summary = "Transaction summary: " + summarise_transactions(inp.transactions)

    return "\n\n".join([profile, goals, weights_block, transcript, tx_summary])


# --------------------------------------------------------------------------- #
# Heuristic (offline) scorer — ports Wealth-Wellness-Hub dimension semantics   #
# --------------------------------------------------------------------------- #
#
# Design (balanced transcript + transactions, with negation handling):
#   For each dimension we compute two signals in [-1, +1]:
#     * a TRANSCRIPT signal from polarity-aware concept matching, and
#     * a TRANSACTION signal from the ledger (savings rate, category mix, ...).
#   We blend them (weights per dimension) into a single signal, then map to a
#   0-100 score around a neutral midpoint. No additive penalty stacking: each
#   concept contributes a bounded, saturating amount, so three cues can't drive
#   a dimension to the floor. Negation is detected in a short window before a
#   concept word, so "sudah punya asuransi" reads +1 and "tidak punya asuransi"
#   reads -1 on the SAME concept.

import re  # noqa: E402  (kept local to the heuristic section)

# Tokens that negate / weaken a following concept (Bahasa + English).
_NEGATORS = (
    "tidak", "tak", "belum", "tanpa", "bukan", "kurang", "ga", "gak", "nggak",
    "engga", "enggak", "no", "never", "not", "without", "lack",
)
# Tokens that emphasise / strengthen a following concept.
_BOOSTERS = ("sudah", "udah", "selalu", "rutin", "setiap", "always", "regularly", "have")

# Concept lexicons per dimension. Each entry is a list of phrases; the polarity
# is decided by the surrounding negation/booster window, not by the list.
_CONCEPTS: dict[str, tuple[str, ...]] = {
    "risk_management": (
        "asuransi", "perlindungan", "proteksi", "terlindungi", "insurance",
        "cover", "jaminan",
    ),
    "emergency_fund": (
        "dana darurat", "tabungan darurat", "tabungan", "dana cadangan",
        "emergency fund", "savings buffer", "simpanan",
    ),
    "growth": (
        "investasi", "reksa dana", "saham", "obligasi", "equity", "fund",
        "bibit", "deposito", "invest",
    ),
    "diversification": (
        "diversifikasi", "beberapa", "berbagai", "macam-macam", "bermacam",
        "diversified", "spread", "berbagai aset",
    ),
    "liquidity": (
        "kas", "cash", "likuid", "uang tunai", "mudah dicairkan", "rekening",
        "tabungan biasa",
    ),
    "tax_efficiency": (
        "pajak", "tax", "dplk", "pensiun", "tax-advantaged", "tabungan pensiun",
    ),
    "behavioural_resilience": (
        "rutin", "disiplin", "konsisten", "teratur", "rencana keuangan",
        "berinvestasi setiap bulan", "menabung tiap bulan", "regularly",
        "consistent", "discipline",
    ),
}
# Concepts that, when present (positively), indicate WEAKNESS for the dimension
# (e.g. impulsive spending hurts behavioural_resilience; living payday-to-payday
# hurts emergency_fund). Polarity-aware too.
_NEGATIVE_CONCEPTS: dict[str, tuple[str, ...]] = {
    "behavioural_resilience": (
        "impulsif", "boros", "tergoda", "checkout", "kalap", "ghosting",
        "berhenti investasi", "sekali saja", "lupa", "impulsive",
    ),
    "emergency_fund": (
        "pas-pasan", "gaji habis", "uang habis", "habis sebelum", "paycheck to paycheck",
        "tidak bisa menabung", "tidak punya dana darurat", "tanpa dana darurat",
        "no emergency fund",
    ),
    "risk_management": (
        "penghasilan berhenti", "kalau sakit tidak", "kalau tidak kerja",
        "rentan", "income stops",
    ),
    "liquidity": (
        "susah dicairkan", "sulit dicairkan", "terkunci", "tidak likuid", "illiquid",
        "kas saya sangat sedikit", "uang terkunci", "locked",
    ),
}

_NEG_RE = re.compile(r"\b(" + "|".join(_NEGATORS) + r")\b")
_BOOST_RE = re.compile(r"\b(" + "|".join(_BOOSTERS) + r")\b")


def _polarity_for(text: str, phrase: str, window: int = 24) -> Optional[int]:
    """Return +1, -1, or None for a phrase given its negation/booster context.

    Looks at a short character window immediately preceding each occurrence of
    ``phrase``. If a negator appears there -> -1; else if a booster appears ->
    +1; else +1 (a bare positive mention). Returns None if the phrase is absent.
    """
    idx = text.find(phrase)
    if idx == -1:
        return None
    pol = 0
    while idx != -1:
        pre = text[max(0, idx - window): idx]
        if _NEG_RE.search(pre):
            pol -= 1
        elif _BOOST_RE.search(pre):
            pol += 1
        else:
            pol += 1
        nxt = text.find(phrase, idx + len(phrase))
        idx = nxt
    return 1 if pol > 0 else (-1 if pol < 0 else 1)


def _phrase_contains_negator(phrase: str) -> bool:
    """True if the weakness phrase itself embeds a negator (e.g. 'tidak punya ...').

    Such phrases ARE the weakness when stated plainly, so we treat their plain
    assertion as polarity +1 (weakness present) rather than letting the embedded
    negator flip them.
    """
    return bool(_NEG_RE.search(phrase))


def _transcript_signal(text: str, dim: str) -> float:
    """Net transcript evidence for a dimension, in roughly [-1, +1] (saturating)."""
    score = 0.0
    for phrase in _CONCEPTS.get(dim, ()):  # positive-leaning concepts
        pol = _polarity_for(text, phrase)
        if pol is not None:
            score += 0.6 * pol
    for phrase in _NEGATIVE_CONCEPTS.get(dim, ()):  # weakness-indicating concepts
        if phrase not in text:
            continue
        if _phrase_contains_negator(phrase):
            # phrase already encodes the weakness ("tidak punya dana darurat");
            # an explicit "I don't have X" is a high-confidence weakness signal,
            # weighted more than soft single-word cues.
            score -= 0.85
        else:
            # neutral weakness word ("boros"); honour surrounding polarity so
            # "tidak boros" doesn't count as a weakness.
            pol = _polarity_for(text, phrase)
            if pol is not None:
                score -= 0.5 * pol
    # saturate so many cues can't blow past the bound
    return max(-1.0, min(1.0, score))


def _score_heuristic(inp: DiagnosticInput) -> dict[str, float]:
    """Deterministic local scoring used when no LLM key is available.

    A transparent fallback so the pipeline and the demo run even if the model
    call fails. Dimension meanings mirror the Wealth-Wellness-Hub project; the
    scoring blends polarity-aware transcript evidence with ledger-derived
    signals. Each dimension is mapped to 0-100 around a neutral midpoint.
    """
    text = (inp.voice_transcript or "").lower()
    txns = inp.transactions

    # --- transaction-derived signals (all roughly normalised to [-1, +1]) ---
    inflow = sum(t.amount_idr for t in txns if t.direction is TransactionDirection.CREDIT)
    outflow = sum(t.amount_idr for t in txns if t.direction is TransactionDirection.DEBIT)
    debit_total = max(outflow, 1)
    savings_rate = (inflow - outflow) / inflow if inflow > 0 else 0.0

    debit_cats = {t.category.value for t in txns if t.direction is TransactionDirection.DEBIT}
    cat_count = len(debit_cats)
    has_insurance_tx = "insurance" in debit_cats
    has_investment_tx = "investment" in debit_cats
    invest_share = sum(
        t.amount_idr for t in txns
        if t.direction is TransactionDirection.DEBIT and t.category.value == "investment"
    ) / debit_total
    discretionary_share = sum(
        t.amount_idr for t in txns
        if t.direction is TransactionDirection.DEBIT
        and t.category.value in ("shopping", "entertainment")
    ) / debit_total

    # tx signals in [-1, +1]
    tx_sig = {
        "risk_management": (0.7 if has_insurance_tx else -0.4)
        + (-0.4 if inp.is_gig_worker else 0.1),
        "emergency_fund": max(-1.0, min(1.0, (savings_rate - 0.05) * 4.0)),
        "growth": (0.8 if has_investment_tx else -0.5) + min(0.4, invest_share * 8.0),
        "diversification": max(-1.0, min(1.0, (cat_count - 4) / 4.0)),
        # liquidity: positive savings helps, but cash locked into investments
        # hurts — a high investment share of spending means low accessible cash.
        "liquidity": max(-1.0, min(1.0, (savings_rate - 0.05) * 3.5 - invest_share * 3.0)),
        "tax_efficiency": 0.25 if has_investment_tx else -0.1,
        "behavioural_resilience": max(
            -1.0, min(1.0, (savings_rate * 3.0) - (discretionary_share * 2.5))
        ),
    }
    for k in tx_sig:  # clamp
        tx_sig[k] = max(-1.0, min(1.0, tx_sig[k]))

    # blend weights: how much transcript vs transactions drive each dimension.
    # Protection/behaviour are best evidenced by what people SAY; balances and
    # breadth are best evidenced by what they DO.
    w_transcript = {
        "risk_management": 0.60, "emergency_fund": 0.45, "growth": 0.45,
        "diversification": 0.30, "liquidity": 0.35, "tax_efficiency": 0.55,
        "behavioural_resilience": 0.55,
    }
    # neutral midpoints + how far a full ±1 signal can move the score
    midpoint = {
        "risk_management": 50.0, "emergency_fund": 50.0, "growth": 48.0,
        "diversification": 52.0, "liquidity": 55.0, "tax_efficiency": 50.0,
        "behavioural_resilience": 55.0,
    }
    span = 38.0  # a full +1 blended signal => midpoint + 38; full -1 => midpoint - 38

    out: dict[str, float] = {}
    for dim in (
        "diversification", "liquidity", "growth", "risk_management",
        "tax_efficiency", "emergency_fund", "behavioural_resilience",
    ):
        ts = _transcript_signal(text, dim)
        wt = w_transcript[dim] if text.strip() else 0.0  # no transcript -> tx only
        blended = wt * ts + (1.0 - wt) * tx_sig[dim]
        blended = max(-1.0, min(1.0, blended))
        score = midpoint[dim] + span * blended
        out[dim] = round(float(max(5.0, min(98.0, score))), 1)
    return out


# --------------------------------------------------------------------------- #
# Model path                                                                  #
# --------------------------------------------------------------------------- #


def _score_with_model(inp: DiagnosticInput, model: str) -> dict[str, float]:
    """Call the OpenAI API with structured output; return the seven scores + rationale."""
    from openai import OpenAI  # imported lazily so offline runs need no SDK

    client = OpenAI()
    user_msg = _build_user_message(inp)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_schema", "json_schema": RESPONSE_JSON_SCHEMA},
        temperature=0,
    )
    content = resp.choices[0].message.content or "{}"
    return json.loads(content)


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #


@dataclass
class DiagnosticResult:
    """Wraps the vector with provenance (which path produced it)."""

    vector: WellnessVector
    source: str  # "model" or "heuristic"


def run_diagnostic(
    inp: DiagnosticInput,
    *,
    model: Optional[str] = None,
    force_heuristic: bool = False,
) -> DiagnosticResult:
    """Score a user and return a validated :class:`WellnessVector`.

    Uses the OpenAI model when ``OPENAI_API_KEY`` is set (and ``force_heuristic``
    is False); otherwise falls back to the deterministic local scorer. Either
    way, the seven scores go through ``WellnessVector.from_scores`` so
    ``priority_gap`` is derived and the result is schema-valid.
    """
    use_model = (not force_heuristic) and bool(os.environ.get("OPENAI_API_KEY"))
    rationale: Optional[str] = None

    if use_model:
        try:
            payload = _score_with_model(inp, model or DEFAULT_MODEL)
            rationale = payload.pop("rationale", None)
            source = "model"
        except Exception:  # noqa: BLE001 - never let a model hiccup break the pipeline
            payload = _score_heuristic(inp)
            source = "heuristic"
    else:
        payload = _score_heuristic(inp)
        source = "heuristic"

    vector = WellnessVector.from_scores(
        diversification=float(payload["diversification"]),
        liquidity=float(payload["liquidity"]),
        growth=float(payload["growth"]),
        risk_management=float(payload["risk_management"]),
        tax_efficiency=float(payload["tax_efficiency"]),
        emergency_fund=float(payload["emergency_fund"]),
        behavioural_resilience=float(payload["behavioural_resilience"]),
        rationale=rationale,
    )
    return DiagnosticResult(vector=vector, source=source)


__all__ = [
    "SYSTEM_PROMPT",
    "RESPONSE_JSON_SCHEMA",
    "summarise_transactions",
    "run_diagnostic",
    "DiagnosticResult",
]
