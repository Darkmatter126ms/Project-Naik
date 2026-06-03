"""CRRA utility weighting for the diagnostic agent.

The diagnostic scores seven wellness dimensions, but *which* gap matters most
depends on the user's attitude to risk. We encode that with a constant relative
risk aversion (CRRA) utility:

    u(c) = (c**(1 - gamma) - 1) / (1 - gamma)      for gamma != 1
    u(c) = ln(c)                                   for gamma  = 1

A higher relative-risk-aversion coefficient ``gamma`` means the user feels a
shortfall in *protective* dimensions (risk_management, emergency_fund,
liquidity) much more acutely than a shortfall in *return-seeking* ones (growth).
A lower gamma flips that emphasis toward growth.

These weights are computed deterministically in Python — not guessed by the LLM
— so the persona→weight mapping is auditable and reproducible. They are passed
to the agent as *context* to bias its emphasis and its written rationale. They
do NOT override the raw scores: ``priority_gap`` remains the genuinely
lowest-scoring dimension (enforced by the schema), so a real protection gap
surfaces regardless of risk appetite.

Mapping (self-declared profile -> gamma), aligned with the three Bibit tiers:
    conservative -> gamma = 4.0   (strongly protection-weighted)
    moderate     -> gamma = 2.0   (balanced)
    aggressive   -> gamma = 1.0   (log utility; growth-tolerant)
"""

from __future__ import annotations

from typing import Dict

# Import the canonical dimension list / enum from the source of truth.
try:  # package-relative (deployed: `from naik_agents.diagnostic import ...`)
    from api.schemas import DIMENSION_ORDER, RiskProfile, WellnessDimension
except ImportError:  # pragma: no cover - direct/script execution fallback
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
    from schemas import DIMENSION_ORDER, RiskProfile, WellnessDimension  # type: ignore

#: Relative-risk-aversion coefficient by self-declared profile.
GAMMA_BY_PROFILE: Dict[RiskProfile, float] = {
    RiskProfile.CONSERVATIVE: 4.0,
    RiskProfile.MODERATE: 2.0,
    RiskProfile.AGGRESSIVE: 1.0,
}

#: How each dimension leans: +1 protective, -1 return-seeking, 0 neutral.
#: Protective dimensions gain weight as gamma rises; growth loses it.
_DIMENSION_LEAN: Dict[WellnessDimension, int] = {
    WellnessDimension.DIVERSIFICATION: 0,
    WellnessDimension.LIQUIDITY: +1,
    WellnessDimension.GROWTH: -1,
    WellnessDimension.RISK_MANAGEMENT: +1,
    WellnessDimension.TAX_EFFICIENCY: 0,
    WellnessDimension.EMERGENCY_FUND: +1,
    WellnessDimension.BEHAVIOURAL_RESILIENCE: 0,
}


def gamma_for(risk_tolerance: RiskProfile) -> float:
    """Return the CRRA relative-risk-aversion coefficient for a profile."""
    return GAMMA_BY_PROFILE[risk_tolerance]


def crra_utility(consumption: float, gamma: float) -> float:
    """CRRA utility of a positive consumption level.

    Used here on dimension scores normalised to (0, 1] to express how painful a
    given shortfall feels under a particular risk aversion.
    """
    if consumption <= 0:
        consumption = 1e-9  # guard the singularity at 0
    if abs(gamma - 1.0) < 1e-9:
        from math import log

        return log(consumption)
    return (consumption ** (1.0 - gamma) - 1.0) / (1.0 - gamma)


def crra_weights(risk_tolerance: RiskProfile) -> Dict[WellnessDimension, float]:
    """Compute normalised per-dimension importance weights for a profile.

    The weight tilts toward protective dimensions as ``gamma`` rises. Concretely,
    each dimension's base weight is scaled by ``(1 + lean * (gamma - 1) * k)``,
    clipped to stay positive, then normalised to sum to 1 across the seven
    dimensions. Returns a dict keyed by ``WellnessDimension`` in canonical order.
    """
    gamma = gamma_for(risk_tolerance)
    k = 0.18  # sensitivity of the tilt to gamma
    raw: Dict[WellnessDimension, float] = {}
    for dim in DIMENSION_ORDER:
        lean = _DIMENSION_LEAN[dim]
        factor = 1.0 + lean * (gamma - 1.0) * k
        raw[dim] = max(factor, 0.05)  # keep strictly positive
    total = sum(raw.values())
    return {dim: round(w / total, 4) for dim, w in raw.items()}


def crra_weights_table(risk_tolerance: RiskProfile) -> str:
    """Render the weights as a compact, LLM-friendly context block."""
    gamma = gamma_for(risk_tolerance)
    weights = crra_weights(risk_tolerance)
    lines = [
        f"CRRA risk-aversion gamma = {gamma:.1f} ({risk_tolerance.value}).",
        "Per-dimension importance weights (higher = this gap matters more for "
        "THIS user; weights sum to 1.0):",
    ]
    for dim, w in weights.items():
        lines.append(f"  - {dim.value}: {w:.3f}")
    return "\n".join(lines)
