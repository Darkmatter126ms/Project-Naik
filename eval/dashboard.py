"""eval/dashboard.py — Naik evaluation demo dashboard.

Single-page view optimised for hackathon presentation:
  • 4 metric numbers large enough to read from across a room.
  • Compact 50-persona score table; click any row to drill down.
  • Full agent-output detail panel (wellness radar, fund picks,
    insurance trigger, narrative) for the selected persona.

Deploy on Streamlit Community Cloud
────────────────────────────────────
  Main file path  : eval/dashboard.py
  Requirements    : eval/requirements.txt
  Secrets (TOML)  : DATABASE_URL = "postgresql://..."
                    API_BASE_URL = "https://naik-api.onrender.com"
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Page config — collapsed sidebar so the demo starts full-width
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Naik · Eval",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

_DB_URL   = st.secrets.get("DATABASE_URL",  os.environ.get("DATABASE_URL", ""))
_API_BASE = st.secrets.get("API_BASE_URL",  os.environ.get("API_BASE_URL", "http://localhost:5050"))

# ─────────────────────────────────────────────────────────────────────────────
# CSS — metric card numbers are 4 rem; everything else scales with the browser
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* ── metric cards ─────────────────────────────────────────────────────────── */
.metric-card {
    background  : rgba(255,255,255,0.04);
    border      : 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding     : 2.25rem 1.25rem 2rem;
    text-align  : center;
}
.metric-value {
    font-size   : 4rem;
    font-weight : 900;
    line-height : 1;
    letter-spacing: -2px;
    font-variant-numeric: tabular-nums;
}
.metric-label {
    font-size   : 0.68rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color       : rgba(255,255,255,0.45);
    margin-top  : 0.65rem;
}
.metric-sub {
    font-size   : 0.62rem;
    color       : rgba(255,255,255,0.25);
    margin-top  : 0.2rem;
}
/* ── section header ───────────────────────────────────────────────────────── */
.section-header {
    font-size   : 0.7rem;
    font-weight : 600;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color       : rgba(255,255,255,0.35);
    margin-bottom: 0.5rem;
}
/* ── drill-down container ─────────────────────────────────────────────────── */
.drill-container {
    background  : rgba(255,255,255,0.03);
    border      : 1px solid rgba(255,255,255,0.07);
    border-radius: 12px;
    padding     : 1.5rem;
    margin-top  : 0.5rem;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _get_engine():
    if not _DB_URL:
        return None
    try:
        from sqlalchemy import create_engine
        engine = create_engine(_DB_URL, pool_pre_ping=True, pool_size=2, max_overflow=0)
        with engine.connect():
            pass
        return engine
    except Exception as exc:
        st.error(f"DB connection failed: {exc}")
        return None


_QUERY = """
WITH latest AS (
    SELECT DISTINCT ON (persona_id)
        persona_id,
        agent_outputs,
        scores,
        COALESCE(created_at, NOW()) AS created_at
    FROM eval_runs
    ORDER BY persona_id, created_at DESC NULLS LAST
)
SELECT
    p.data->>'user_id'                                AS user_id,
    p.data->>'kecamatan'                              AS kecamatan,
    p.data->>'city'                                   AS city,
    p.data->>'risk_tolerance'                         AS risk_tolerance,
    (p.data->>'monthly_income_idr')::bigint           AS monthly_income_idr,
    (p.data->>'is_gig_worker')::boolean               AS is_gig_worker,
    (p.data->>'age')::int                             AS age,
    (p.data->'_meta'->>'halal_investing')::boolean    AS halal_investing,
    (p.data->'_meta'->>'flood_risk_score')::float     AS flood_risk_score,
    p.data->'_meta'->>'current_insurance'             AS current_insurance,
    (l.scores->>'suitability')::float                 AS suitability,
    (l.scores->>'fund_rank_correctness')::float       AS fund_rank_correctness,
    (l.scores->>'claim_trigger_precision')::float     AS claim_trigger_precision,
    (l.scores->>'do_no_harm')::float                  AS do_no_harm,
    (l.scores->>'overall')::float                     AS overall,
    (l.scores->>'response_ms')::int                   AS response_ms,
    (l.scores->>'success')::boolean                   AS api_success,
    l.scores->>'error_msg'                            AS error_msg,
    l.agent_outputs                                   AS agent_outputs,
    l.created_at                                      AS evaluated_at
FROM latest l
JOIN personas p ON l.persona_id = p.id
ORDER BY p.data->>'user_id'
"""

_SCORE_COLS = ["suitability", "fund_rank_correctness",
               "claim_trigger_precision", "do_no_harm", "overall"]


@st.cache_data(ttl=180, show_spinner="Fetching eval data…")
def load_data() -> pd.DataFrame:
    engine = _get_engine()
    if engine is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql(_QUERY, engine)
        for col in _SCORE_COLS + ["flood_risk_score"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception as exc:
        st.error(f"Query failed: {exc}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pct(v: float | None) -> str:
    """0–1 float → '98.0%' string."""
    return f"{v * 100:.1f}%" if v is not None and pd.notna(v) else "—"


def _colour(v: float | None, *, invert: bool = False) -> str:
    """Return a hex colour scaled from red → green (or inverted)."""
    if v is None or pd.isna(v):
        return "#666"
    good = v >= 0.90
    warn = v >= 0.70
    if invert:
        good, warn = not good, not warn
    if good:
        return "#00e676"
    if warn:
        return "#ffc107"
    return "#f44336"


def _metric_card(value: str, label: str, colour: str, sub: str = "") -> str:
    return (
        f'<div class="metric-card">'
        f'<div class="metric-value" style="color:{colour}">{value}</div>'
        f'<div class="metric-label">{label}</div>'
        + (f'<div class="metric-sub">{sub}</div>' if sub else "")
        + "</div>"
    )


def _score_cell_colour(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "color:#555"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "color:#555"
    if f >= 0.90:
        return "color:#00e676;font-weight:700"
    if f >= 0.70:
        return "color:#ffc107;font-weight:600"
    return "color:#f44336;font-weight:700"


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — minimal, collapsed by default
# ─────────────────────────────────────────────────────────────────────────────

def _sidebar(df: pd.DataFrame) -> None:
    with st.sidebar:
        st.caption("**Naik · Eval Dashboard**")
        st.divider()

        engine = _get_engine()
        if not _DB_URL:
            st.error("DATABASE_URL not set")
        elif engine is None:
            st.error("DB unreachable")
        else:
            st.success("DB connected ✓")

        if st.button("Ping /health", use_container_width=True):
            try:
                r = requests.get(f"{_API_BASE.rstrip('/')}/health", timeout=8)
                p = r.json()
                st.success(f"API ok — v{p.get('version','?')}")
            except Exception as exc:
                st.error(f"API unreachable: {exc}")

        if st.button("↺  Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        if not df.empty:
            st.divider()
            st.caption(f"**{len(df)}** personas")
            last = df.get("evaluated_at", pd.Series(dtype=object)).max()
            st.caption(f"Last eval: {last}")

        st.divider()
        st.caption(
            "To populate:\n\n"
            "```\npython eval/run_eval.py \\\n"
            f"  --api-base {_API_BASE}\n```"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Persona drill-down
# ─────────────────────────────────────────────────────────────────────────────

_WELLNESS_DIMS = [
    "diversification", "liquidity", "growth", "risk_management",
    "tax_efficiency", "emergency_fund", "behavioural_resilience",
]
_DIM_LABELS = {
    "diversification":      "Diversif.",
    "liquidity":            "Liquidity",
    "growth":               "Growth",
    "risk_management":      "Protection",
    "tax_efficiency":       "Tax eff.",
    "emergency_fund":       "Emerg. fund",
    "behavioural_resilience": "Discipline",
}


def _wellness_radar(wellness: dict) -> go.Figure:
    values = [wellness.get(d, 0) for d in _WELLNESS_DIMS]
    labels = [_DIM_LABELS[d] for d in _WELLNESS_DIMS]
    fig = go.Figure(go.Scatterpolar(
        r=values + [values[0]],
        theta=labels + [labels[0]],
        fill="toself",
        line_color="#00e676",
        fillcolor="rgba(0,230,118,0.12)",
        hovertemplate="%{theta}: %{r:.1f}<extra></extra>",
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True, range=[0, 100],
                tickfont=dict(size=9, color="#666"),
                gridcolor="#333",
            ),
            angularaxis=dict(tickfont=dict(size=10, color="#aaa")),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=20, b=20, l=30, r=30),
        height=280,
        font=dict(color="#ccc"),
        showlegend=False,
    )
    return fig


def _render_drill_down(row: pd.Series) -> None:
    outputs: dict   = row.get("agent_outputs") or {}
    wellness: dict  = outputs.get("wellness")  or {}
    wealth: dict    = outputs.get("wealth")    or {}
    insurance: dict = outputs.get("insurance") or {}
    compliance: dict = outputs.get("compliance") or {}
    picks: list     = wealth.get("picks")      or []

    halal_tag = " · 🌙 Halal"   if row.get("halal_investing") else ""
    gig_tag   = " · 🛵 Gig"     if row.get("is_gig_worker")   else ""

    st.markdown('<div class="drill-container">', unsafe_allow_html=True)

    # ── Identity ─────────────────────────────────────────────────────────── #
    st.markdown(
        f"**{row.get('user_id', '?')}**  ·  "
        f"{row.get('kecamatan', '?')}, {row.get('city', '?')}  ·  "
        f"Age {row.get('age', '?')}  ·  "
        f"Rp {int(row.get('monthly_income_idr') or 0):,}/month  ·  "
        f"{str(row.get('risk_tolerance', '?')).title()}"
        f"{halal_tag}{gig_tag}  ·  "
        f"Flood risk {float(row.get('flood_risk_score') or 0):.2f}"
    )

    # ── Score badges ─────────────────────────────────────────────────────── #
    sc = st.columns(5)
    for col, (label, key) in zip(sc, [
        ("Suitability",        "suitability"),
        ("Fund-rank",          "fund_rank_correctness"),
        ("Trigger precision",  "claim_trigger_precision"),
        ("Do-no-harm",         "do_no_harm"),
        ("Overall",            "overall"),
    ]):
        v = row.get(key)
        col.metric(label, _pct(v))

    st.divider()

    # ── Two-column layout ─────────────────────────────────────────────────── #
    col_l, col_r = st.columns([1, 1], gap="large")

    with col_l:
        # Wellness radar
        st.markdown('<p class="section-header">Wellness vector</p>',
                    unsafe_allow_html=True)
        if any(wellness.get(d) is not None for d in _WELLNESS_DIMS):
            st.plotly_chart(_wellness_radar(wellness), use_container_width=True)
        priority = wellness.get("priority_gap", "?")
        overall  = wellness.get("overall_score", "?")
        st.caption(
            f"Priority gap: **{priority}**  ·  "
            f"Wellness score: **{overall}** / 100"
        )
        if wellness.get("rationale"):
            st.caption(f"*{wellness['rationale']}*")

        # Compliance
        st.markdown('<p class="section-header" style="margin-top:1rem">Compliance</p>',
                    unsafe_allow_html=True)
        if compliance:
            status = compliance.get("status", "?")
            colour = "#00e676" if "approved" in status else "#f44336"
            st.markdown(
                f"<span style='color:{colour};font-weight:700'>"
                f"{status.replace('_',' ').title()}</span>  ·  "
                f"Human confirmation: `{compliance.get('requires_human_confirmation','?')}`",
                unsafe_allow_html=True,
            )

    with col_r:
        # Fund picks
        st.markdown('<p class="section-header">Fund picks</p>',
                    unsafe_allow_html=True)
        if picks:
            st.caption(
                f"Profile used: **{wealth.get('risk_profile_used', '?')}**  ·  "
                f"Monthly contribution: Rp {int(wealth.get('recommended_monthly_contribution_idr') or 0):,}"
            )
            for i, p in enumerate(picks, 1):
                sharia_icon = "🌙" if p.get("is_sharia") else "❌"
                st.markdown(
                    f"**{i}.** {p.get('fund_name','?')} {sharia_icon}  \n"
                    f"<span style='color:#aaa;font-size:0.85rem'>"
                    f"Score {p.get('match_score','?')}  ·  "
                    f"Risk {p.get('risk_level','?')}  ·  "
                    f"ER {p.get('expense_ratio_pct','?')}%</span>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No wealth recommendation.")

        # Insurance
        st.markdown('<p class="section-header" style="margin-top:1rem">Income shield</p>',
                    unsafe_allow_html=True)
        if insurance:
            trigger = insurance.get("trigger") or {}
            payout  = insurance.get("payout_per_event_idr") or 0
            premium = insurance.get("premium_idr") or 0
            ratio   = round(payout / premium, 1) if premium > 0 else "—"
            kec_ok  = trigger.get("kecamatan") == row.get("kecamatan")
            kec_icon = "✓" if kec_ok else "❌"
            st.markdown(
                f"Trigger: **{trigger.get('metric','?')} ≥ {trigger.get('threshold','?')} "
                f"{trigger.get('unit','')}** at {trigger.get('kecamatan','?')} {kec_icon}  \n"
                f"Payout: **Rp {int(payout):,}** "
                f"({insurance.get('payout_multiple','?')}× daily)  \n"
                f"Premium: **Rp {int(premium):,}** / {insurance.get('premium_frequency','?')}  \n"
                f"Ratio: **{ratio}×** (payout ÷ premium)"
            )
            if not kec_ok:
                st.error(
                    f"Kecamatan mismatch: trigger '{trigger.get('kecamatan')}' "
                    f"≠ persona '{row.get('kecamatan')}'"
                )
        else:
            st.caption("No insurance quote.")

    # ── Narrative ─────────────────────────────────────────────────────────── #
    narrative = outputs.get("narrative", "")
    if narrative:
        st.divider()
        st.markdown('<p class="section-header">Narrative shown to user</p>',
                    unsafe_allow_html=True)
        st.markdown(
            f"<p style='font-size:0.95rem;line-height:1.65;color:#ddd'>{narrative}</p>",
            unsafe_allow_html=True,
        )
        st.caption(f"Next step: **{outputs.get('next_step', '?')}**")

    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main page
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    df = load_data()
    _sidebar(df)

    # ── Header ────────────────────────────────────────────────────────────── #
    st.markdown(
        "<h2 style='margin:0;font-size:1.5rem;font-weight:700;"
        "letter-spacing:-0.5px'>Naik · Evaluation Results</h2>",
        unsafe_allow_html=True,
    )

    if df.empty:
        st.info(
            "No eval data found.  \n\n"
            f"Run `python eval/run_eval.py --api-base {_API_BASE}` to populate.",
            icon="📭",
        )
        return

    scored = df[df.get("api_success", pd.Series([True] * len(df))).fillna(False)]

    # ── 4 Metric cards ────────────────────────────────────────────────────── #
    # Compute aggregates
    n_total      = len(df)
    n_scored     = len(scored)
    suit_avg     = scored["suitability"].mean()             if not scored.empty else None
    rank_avg     = scored["fund_rank_correctness"].mean()   if not scored.empty else None
    trig_avg     = scored["claim_trigger_precision"].mean() if not scored.empty else None
    dnhm_fail    = int((scored["do_no_harm"] == 0.0).sum()) if not scored.empty else 0
    last_run     = df["evaluated_at"].max()

    col_a, col_b, col_c, col_d = st.columns(4, gap="medium")
    cards = [
        (col_a, _pct(suit_avg),  _colour(suit_avg),          "SUITABILITY",       f"{n_scored} personas"),
        (col_b, _pct(rank_avg),  _colour(rank_avg),          "FUND-RANK ACCURACY", ""),
        (col_c, _pct(trig_avg),  _colour(trig_avg),          "TRIGGER PRECISION",  ""),
        (col_d,
         str(dnhm_fail),
         "#00e676" if dnhm_fail == 0 else "#f44336",
         "DO-NO-HARM VIOLATIONS",
         "0 = perfect" if dnhm_fail == 0 else f"of {n_scored} personas"),
    ]
    for col, value, colour, label, sub in cards:
        with col:
            st.markdown(
                _metric_card(value, label, colour, sub),
                unsafe_allow_html=True,
            )

    # Run metadata
    last_str = (
        last_run.strftime("%Y-%m-%d %H:%M UTC") if hasattr(last_run, "strftime")
        else str(last_run)
    )
    st.markdown(
        f"<p style='color:rgba(255,255,255,0.3);font-size:0.75rem;"
        f"margin-top:0.75rem'>Last run: {last_str}"
        f" &nbsp;·&nbsp; {n_total} personas &nbsp;·&nbsp; "
        f"{n_scored} API calls successful</p>",
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Persona table ─────────────────────────────────────────────────────── #
    st.markdown(
        '<p class="section-header">All personas — click a row to drill down</p>',
        unsafe_allow_html=True,
    )

    # Build display table: compact columns only
    disp = pd.DataFrame({
        "persona":   df["user_id"],
        "kecamatan": df["kecamatan"],
        "risk":      df["risk_tolerance"].str[:4],       # "cons" / "mode" / "aggr"
        "🌙":        df["halal_investing"].apply(lambda v: "🌙" if v else ""),
        "suit":      df["suitability"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "rank":      df["fund_rank_correctness"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "trigger":   df["claim_trigger_precision"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "d-n-h":     df["do_no_harm"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "overall":   df["overall"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "ms":        df["response_ms"].apply(lambda v: f"{int(v)}" if pd.notna(v) else "—"),
    })

    # Colour overall column
    def _style_row(row):
        styles = [""] * len(row)
        try:
            v = float(row["overall"])
        except (ValueError, TypeError):
            return styles
        c = "color:#00e676" if v >= 0.90 else "color:#ffc107" if v >= 0.70 else "color:#f44336"
        styles[disp.columns.get_loc("overall")] = c
        return styles

    event = st.dataframe(
        disp.style.apply(_style_row, axis=1),
        use_container_width=True,
        height=min(60 + 35 * len(disp), 480),
        selection_mode="single-row",
        on_select="rerun",
        key="persona_table",
    )

    # ── Drill-down ────────────────────────────────────────────────────────── #
    selected = event.selection.rows  # type: ignore[attr-defined]
    if selected:
        row = df.iloc[selected[0]]
        st.markdown(
            f"<p class='section-header' style='margin-top:0.5rem'>"
            f"Drill-down — {row.get('user_id', '?')}</p>",
            unsafe_allow_html=True,
        )
        _render_drill_down(row)
    else:
        st.caption("← Select any row to see the full agent output.")


main()
