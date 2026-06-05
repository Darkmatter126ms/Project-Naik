"""naik_agents/nudges.py — Behavioural nudge selection.

Reads ``design/prompts/nudges.json`` (the 20-entry Bahasa Indonesia nudge
library) and returns the single most relevant nudge for a given combination
of wellness priority_gap and calendar context.

Calendar context is inferred from two sources in priority order:

1.  **Date-based** (highest priority):
    - *lebaran*: March 10 – April 15 (Idul Fitri ± 2 weeks)
    - *post_bonus*: April 16 – May 31 and December 20 – January 15
      (THR aftermath + year-end bonus season)
    - *flood_season*: November – March (Jakarta wet season)

2.  **Transaction-based** (lower priority, only if date gives no context):
    - *payday_week*: an income credit posted within the last 7 days.

The first matching context wins. If no context matches, the agent falls
back to the ``"default"`` nudge for the persona's priority_gap.

Usage::

    from naik_agents.nudges import select_nudge
    nudge = select_nudge(wellness_vector, diagnostic_input)
    # nudge is a non-empty Bahasa string, or "" if the library is unavailable.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger("naik.nudges")

# --------------------------------------------------------------------------- #
# Library loader                                                              #
# --------------------------------------------------------------------------- #

_NUDGES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "design", "prompts", "nudges.json"
)


@lru_cache(maxsize=1)
def _load_library() -> dict:
    """Load and cache the nudges.json file. Returns {} on any error."""
    path = os.path.normpath(_NUDGES_PATH)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("nudges", {})
    except FileNotFoundError:
        logger.warning("nudges.json not found at %s — nudges disabled.", path)
        return {}
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("nudges.json parse error: %s — nudges disabled.", exc)
        return {}


# --------------------------------------------------------------------------- #
# Calendar context detection                                                  #
# --------------------------------------------------------------------------- #

def _calendar_context(inp) -> Optional[str]:  # inp: DiagnosticInput
    """Infer the current calendar context from today's date and transactions.

    Returns one of 'lebaran', 'post_bonus', 'flood_season', 'payday_week',
    or None (signals the caller to use the 'default' nudge).
    """
    today = datetime.date.today()
    m, d = today.month, today.day

    # 1. Lebaran / Idul Fitri: arrives late March – early April each year.
    #    We approximate the ± 2-week window around the typical 2026 date
    #    (20 Mar 2026) with a fixed March 10 – April 15 corridor.
    if (m == 3 and d >= 10) or (m == 4 and d <= 15):
        return "lebaran"

    # 2. Post-bonus: THR is paid in the two weeks before Lebaran and the
    #    remaining April + May covers the spending normalisation window.
    #    Year-end bonus season is December 20 – January 15.
    if (m == 4 and d > 15) or m == 5:
        return "post_bonus"
    if (m == 12 and d >= 20) or (m == 1 and d <= 15):
        return "post_bonus"

    # 3. Flood season: Jakarta's wet season runs November through March.
    if m in (11, 12, 1, 2, 3):
        return "flood_season"

    # 4. Payday week: an income credit posted in the last 7 days.
    if inp.transactions:
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - datetime.timedelta(days=7)
        recent_income = [
            t for t in inp.transactions
            if (
                t.direction.value == "credit"
                and t.category is not None
                and t.category.value == "income"
                and t.timestamp >= cutoff
            )
        ]
        if recent_income:
            return "payday_week"

    return None


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #

def select_nudge(wellness, inp) -> str:  # wellness: WellnessVector, inp: DiagnosticInput
    """Return the best-matching nudge string, or '' if unavailable.

    Selection logic:
      1. Look up ``library[priority_gap][calendar_context]``.
      2. Fall back to ``library[priority_gap]['default']``.
      3. Fall back to '' so the rationale is never broken by a missing nudge.

    Args:
        wellness: the WellnessVector output of the diagnostic agent.
        inp:      the user's DiagnosticInput (for transaction-based context).

    Returns:
        A non-empty Bahasa Indonesia nudge string, or '' on any failure.
    """
    library = _load_library()
    if not library:
        return ""

    gap_key = wellness.priority_gap.value  # e.g. "risk_management"
    gap_nudges: dict = library.get(gap_key, {})
    if not gap_nudges:
        logger.debug("No nudges found for priority_gap=%s", gap_key)
        return ""

    context = _calendar_context(inp)
    nudge = (
        gap_nudges.get(context, "")          # context-specific, or
        or gap_nudges.get("default", "")     # default for this gap, or
        or ""                                # silent fallback
    )

    if nudge:
        logger.debug("Nudge selected: gap=%s context=%s → %.50s…", gap_key, context, nudge)
    return nudge


__all__ = ["select_nudge"]
