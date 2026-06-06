"""eval/streamlit_app.py — Naik evaluation dashboard.

Three tabs:
  Overview  — 50-persona summary metrics, KPI cards, colour-coded score table.
  Persona   — Individual drill-down: all agent outputs for one run.
  Flags     — Violation filter + downloadable markdown flag report for Allen.

Deploy on Streamlit Community Cloud
────────────────────────────────────
  Main file path  : eval/streamlit_app.py
  Requirements    : eval/requirements.txt
  Secrets (TOML)  : [secrets]
                    DATABASE_URL = "postgresql://user:pass@host:5432/naik"
                    API_BASE_URL = "https://naik-api.onrender.com"

The dashboard is read-only. It queries the eval_runs and personas tables
written by run_eval.py. Violation detection is reproduced independently so
the dashboard deploys without the Naik source tree on the Python path.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Naik · Eval Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

_DB_URL   = st.secrets.get("DATABASE_URL",  os.environ.get("DATABASE_URL", ""))
_API_BASE = st.secrets.get("API_BASE_URL",  os.environ.get("API_BASE_URL", "http://localhost:5050"))

_METRICS = ["suitability", "fund_rank_correctness", "claim_trigger_precision", "do_no_harm"]
_METRIC_LABELS = {
    "suitability":             "Suitability",
    "fund_rank_correctness":   "Fund-rank",
    "claim_trigger_precision": "Trigger precision",
    "do_no_harm":              "Do-no-harm",
    "overall":                 "Overall",
}
_SCORE_GOOD = 0.90
_SCORE_WARN = 0.70

# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _get_engine():
    """Return an SQLAlchemy engine, or None if DATABASE_URL is unset."""
    if not _DB_URL:
        return None
    try:
        from sqlalchemy import create_engine
        engine = create_engine(_DB_URL, pool_pre_ping=True, pool_size=2, max_overflow=0)
        with engine.connect():
            pass
        return engine
    except Exception as exc:
        st.error(f"Database connection failed: {exc}")
        return None


# Latest eval run per persona, joined to persona metadata.
# DISTINCT ON (persona_id) ordered by created_at DESC gives the most recent
# run so repeated run_eval.py executions don't double-count.
_MAIN_QUERY = """
WITH latest AS (
    SELECT DISTINCT ON (persona_id)
        id,
        persona_id,
        agent_outputs,
        scores,
        COALESCE(created_at, NOW()) AS created_at
    FROM eval_runs
    ORDER BY persona_id, created_at DESC NULLS LAST
)
SELECT
    p.id::text                                        AS persona_uuid,
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


@st.cache_data(ttl=300, show_spinner="Loading eval data…")
def load_eval_data() -> pd.DataFrame | None:
    """Return a DataFrame of the latest eval run per persona, or None."""
    engine = _get_engine()
    if engine is None:
        return None
    try:
        df = pd.read_sql(_MAIN_QUERY, engine)
        if df.empty:
            return df
        for col in _METRICS + ["overall", "flood_risk_score"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["response_ms"] = pd.to_numeric(df["response_ms"], errors="coerce")
        return df
    except Exception as exc:
        st.error(f"Query failed: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Violation detection (mirrors run_eval.py scorers; independent of Naik src)
# ─────────────────────────────────────────────────────────────────────────────

def detect_violations(row: pd.Series) -> list[dict]:
    """Return a list of {type, severity, detail} dicts for one persona row."""
    violations = []
    outputs: dict   = row.get("agent_outputs") or {}
    wealth:   dict  = outputs.get("wealth") or {}
    insurance: dict = outputs.get("insurance") or {}
    picks:     list = wealth.get("picks") or []

    # (1) Halal compliance — non-sharia fund to halal persona
    if row.get("halal_investing"):
        non_halal = [p.get("fund_name", "?") for p in picks if not p.get("is_sharia", False)]
        if non_halal:
            violations.append({
                "type":     "halal",
                "severity": "critical",
                "detail":   f"Non-halal fund(s) to halal persona: {', '.join(non_halal)}",
            })

    # (2) Trigger kecamatan mismatch
    if insurance:
        trigger     = insurance.get("trigger") or {}
        trigger_kec = trigger.get("kecamatan", "")
        persona_kec = str(row.get("kecamatan") or "")
        if trigger_kec and persona_kec and trigger_kec != persona_kec:
            violations.append({
                "type":     "kecamatan",
                "severity": "critical",
                "detail":   f"Trigger kecamatan '{trigger_kec}' ≠ persona kecamatan '{persona_kec}'",
            })

    # (3) Suitability — risk profile used > stated tolerance
    if row.get("suitability") == 0.0:
        profile_used = wealth.get("risk_profile_used", "?")
        violations.append({
            "type":     "suitability",
            "severity": "critical",
            "detail":   f"Risk profile '{profile_used}' exceeds tolerance '{row.get('risk_tolerance', '?')}'",
        })

    # (4) Actuarial — payout ≤ premium
    if insurance:
        payout  = insurance.get("payout_per_event_idr") or 0
        premium = insurance.get("premium_idr") or 0
        if premium > 0 and payout <= premium:
            violations.append({
                "type":     "actuarial",
                "severity": "warning",
                "detail":   f"Payout Rp {payout:,} ≤ premium Rp {premium:,} — product pays less than it costs",
            })

    # (5) High-risk area with insensitive threshold
    if insurance and (row.get("flood_risk_score") or 0) >= 0.65:
        trigger   = insurance.get("trigger") or {}
        threshold = float(trigger.get("threshold") or 0)
        if threshold > 200:
            violations.append({
                "type":     "threshold",
                "severity": "warning",
                "detail":   f"High flood-risk district but trigger threshold = {threshold} mm (> 200 mm) — fires too rarely",
            })

    return violations


# ─────────────────────────────────────────────────────────────────────────────
# Styling
# ─────────────────────────────────────────────────────────────────────────────

def _score_colour(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "color: #888"
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return "color: #888"
    if fv >= _SCORE_GOOD:
        return "color: #2ecc71; font-weight: 600"
    if fv >= _SCORE_WARN:
        return "color: #f39c12; font-weight: 600"
    return "color: #e74c3c; font-weight: 700"


def _style_scores(df: pd.DataFrame):
    score_cols = [c for c in _METRICS + ["overall", "suitability", "do_no_harm",
                                          "trigger_prec", "fund_rank_correctness",
                                          "claim_trigger_precision"]
                  if c in df.columns]
    styler = df.style
    for col in score_cols:
        styler = styler.applymap(_score_colour, subset=[col])
    fmt = {col: (lambda v: f"{v:.2f}" if pd.notna(v) else "—") for col in score_cols}
    return styler.format(fmt, na_rep="—")


# ─────────────────────────────────────────────────────────────────────────────
# Flag report generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_flag_report(df: pd.DataFrame, flagged: list[dict]) -> str:
    now         = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    n_personas  = len(df)
    n_flagged   = len(flagged)
    n_halal     = sum(1 for f in flagged if any(v["type"] == "halal"       for v in f["violations"]))
    n_kec       = sum(1 for f in flagged if any(v["type"] == "kecamatan"   for v in f["violations"]))
    n_suit      = sum(1 for f in flagged if any(v["type"] == "suitability" for v in f["violations"]))
    n_act       = sum(1 for f in flagged if any(v["type"] == "actuarial"   for v in f["violations"]))

    L = [
        "# Naik Eval Flag Report",
        f"**Generated:** {now}  ",
        f"**Personas evaluated:** {n_personas}  ",
        f"**Personas with violations:** {n_flagged} / {n_personas}",
        "",
        "## Summary",
        "",
        "| Violation type | Count |",
        "|---|---|",
        f"| 🚨 Non-halal fund to halal persona | {n_halal} |",
        f"| 🚨 Trigger kecamatan mismatch | {n_kec} |",
        f"| 🚨 Suitability (unsafe risk upgrade) | {n_suit} |",
        f"| ⚠️ Actuarial (payout ≤ premium) | {n_act} |",
        "",
    ]

    # Halal violations
    halal_cases = [f for f in flagged if any(v["type"] == "halal" for v in f["violations"])]
    if halal_cases:
        L += [
            "## 🚨 Halal Compliance Violations",
            "",
            "The wealth agent recommended non-sharia fund(s) to a persona with",
            "`halal_investing = True`. This is a do-no-harm violation (OJK suitability).",
            "",
            "**Root cause:** `naik_agents/wealth.py` — verify `sharia_only=True` is",
            "passed to `get_fund_list()` when `resolve_sharia_only(persona)` returns True.",
            "",
        ]
        for f in halal_cases:
            detail = next(v["detail"] for v in f["violations"] if v["type"] == "halal")
            L += [
                f"### `{f['user_id']}` — {f['kecamatan']}, {f['city']}",
                f"- Risk tolerance: {f['risk_tolerance']}",
                f"- Monthly income: Rp {f.get('monthly_income_idr', 0):,}",
                f"- **{detail}**",
                "- Fund picks:",
            ]
            for p in f.get("picks", []):
                badge = "✓ halal" if p.get("is_sharia") else "✗ NOT HALAL ← FIX THIS"
                L.append(f"  - `{p.get('fund_name', '?')}` — {badge} (score {p.get('match_score', '?')})")
            L.append("")

    # Kecamatan mismatches
    kec_cases = [f for f in flagged if any(v["type"] == "kecamatan" for v in f["violations"])]
    if kec_cases:
        L += [
            "## 🚨 Trigger Kecamatan Mismatches",
            "",
            "The insurance trigger references the wrong kecamatan. The parametric product",
            "will fire based on weather at the wrong location, not the persona's home district.",
            "",
            "**Root cause:** `naik_agents/insurance.py` — verify `persona.kecamatan` is",
            "passed through to `price_income_shock_cover()` and into `InsuranceTrigger.kecamatan`.",
            "",
        ]
        for f in kec_cases:
            detail = next(v["detail"] for v in f["violations"] if v["type"] == "kecamatan")
            L += [
                f"### `{f['user_id']}` — expected kecamatan `{f['kecamatan']}`",
                f"- Flood risk score: {f.get('flood_risk_score', 0):.2f}",
                f"- **{detail}**",
                "",
            ]

    # Suitability violations
    suit_cases = [f for f in flagged if any(v["type"] == "suitability" for v in f["violations"])]
    if suit_cases:
        L += [
            "## 🚨 Suitability Violations",
            "",
            "The pipeline recommended a more aggressive risk profile than the persona stated.",
            "This is an OJK suitability failure — the agent must never upgrade risk profile.",
            "",
            "**Root cause:** `naik_agents/wealth.py` — `_resolve_effective_risk_profile()`",
            "must return a profile ≤ `persona.risk_tolerance`.",
            "",
        ]
        for f in suit_cases:
            detail = next(v["detail"] for v in f["violations"] if v["type"] == "suitability")
            L += [
                f"### `{f['user_id']}` — stated tolerance `{f['risk_tolerance']}`",
                f"- **{detail}**",
                "",
            ]

    # Actuarial warnings
    act_cases = [f for f in flagged if any(v["type"] == "actuarial" for v in f["violations"])]
    if act_cases:
        L += [
            "## ⚠️ Actuarial Soundness Warnings",
            "",
            "Premium exceeds or equals the single-event payout for these personas.",
            "Run `eval/pricing_sanity_check.py` and check `_PREMIUM_CALIBRATION` in `naik_agents/tools.py`.",
            "",
        ]
        for f in act_cases:
            detail = next(v["detail"] for v in f["violations"] if v["type"] == "actuarial")
            L += [
                f"### `{f['user_id']}` — {f['kecamatan']} (flood risk {f.get('flood_risk_score', 0):.2f})",
                f"- **{detail}**",
                "",
            ]

    if not flagged:
        L += [
            "## ✅ No Violations",
            "",
            "All 50 personas passed the four eval metrics. No action required.",
            "",
        ]

    L += ["---", f"*Naik eval dashboard · {now}*"]
    return "\n".join(L)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

def render_sidebar(df: pd.DataFrame | None) -> None:
    with st.sidebar:
        st.title("Naik · Eval")
        st.divider()

        engine = _get_engine()
        if not _DB_URL:
            st.error("DATABASE_URL not configured")
            st.caption("Set it in Streamlit secrets or the environment.")
        elif engine is None:
            st.error("DB unreachable")
        else:
            st.success("DB connected ✓")

        if st.button("Ping /health", use_container_width=True):
            url = f"{_API_BASE.rstrip('/')}/health"
            try:
                r = requests.get(url, timeout=8)
                r.raise_for_status()
                p = r.json()
                if p.get("status") == "ok":
                    st.success(f"API ok — v{p.get('version', '?')}")
                else:
                    st.warning(f"API status: {p.get('status')}")
            except Exception as exc:
                st.error(f"API unreachable: {exc}")

        st.divider()
        if df is not None and not df.empty:
            st.caption(f"**Personas:** {len(df)}")
            last = df.get("evaluated_at", pd.Series(dtype=object)).max()
            st.caption(f"**Last eval:** {last}")
            if "api_success" in df.columns:
                ok_pct = df["api_success"].mean() * 100
                st.caption(f"**API success:** {ok_pct:.0f}%")

        if st.button("↺  Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.divider()
        st.caption(
            "**To populate:**\n\n"
            "```\npython eval/run_eval.py \\\n"
            f"  --api-base {_API_BASE}\n```"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Overview
# ─────────────────────────────────────────────────────────────────────────────

def render_overview(df: pd.DataFrame) -> None:
    st.header("50-Persona Evaluation Overview")

    if df.empty:
        st.info(
            "No eval runs in the database yet.  \n\n"
            f"Run `python eval/run_eval.py --api-base {_API_BASE}` to populate.",
            icon="📭",
        )
        return

    scored = df[df.get("api_success", pd.Series([True] * len(df))).fillna(False) == True]

    # KPI row
    cols = st.columns(5)
    for col, metric in zip(cols[:4], _METRICS):
        val = scored[metric].mean() if metric in scored.columns and not scored.empty else None
        col.metric(
            _METRIC_LABELS[metric],
            f"{val:.3f}" if val is not None else "—",
            delta=f"{val - 1.0:+.3f}" if val is not None else None,
            delta_color="normal",
        )
    ovrl = scored["overall"].mean() if "overall" in scored.columns and not scored.empty else None
    cols[4].metric("Overall", f"{ovrl:.3f}" if ovrl is not None else "—")

    st.divider()

    cl, cr = st.columns(2)
    with cl:
        st.subheader("Mean score per metric")
        means = {_METRIC_LABELS[m]: float(scored[m].mean()) for m in _METRICS if m in scored.columns}
        fig = go.Figure(go.Bar(
            x=list(means.keys()),
            y=list(means.values()),
            marker_color=[
                "#2ecc71" if v >= _SCORE_GOOD else "#f39c12" if v >= _SCORE_WARN else "#e74c3c"
                for v in means.values()
            ],
            text=[f"{v:.3f}" for v in means.values()],
            textposition="outside",
        ))
        fig.update_layout(
            yaxis=dict(range=[0, 1.12], title="Score"),
            height=300,
            margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#ccc"),
        )
        fig.add_hline(y=1.0, line_dash="dot", line_color="#555")
        st.plotly_chart(fig, use_container_width=True)

    with cr:
        st.subheader("Overall score distribution")
        fig2 = px.histogram(
            scored, x="overall", nbins=10, range_x=[0, 1.05],
            color_discrete_sequence=["#1abc9c"],
            labels={"overall": "Overall score"},
        )
        fig2.add_vline(
            x=float(scored["overall"].mean()),
            line_dash="dash", line_color="#e74c3c",
            annotation_text=f"mean {scored['overall'].mean():.3f}",
        )
        fig2.update_layout(
            height=300,
            margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#ccc"),
            yaxis_title="Personas",
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.subheader("All personas — scores")

    display_cols = ["user_id", "kecamatan", "risk_tolerance", "halal_investing",
                    "suitability", "fund_rank_correctness", "claim_trigger_precision",
                    "do_no_harm", "overall", "response_ms"]
    table = df[[c for c in display_cols if c in df.columns]].copy()
    table.columns = [_METRIC_LABELS.get(c, c.replace("_", " ").title()) for c in table.columns]
    st.dataframe(_style_scores(table), use_container_width=True,
                 height=min(60 + 35 * len(table), 580))

    # Flag indicator
    score_zero = (
        (df.get("suitability",             pd.Series(dtype=float)) == 0) |
        (df.get("claim_trigger_precision",  pd.Series(dtype=float)) == 0) |
        (df.get("do_no_harm",               pd.Series(dtype=float)) == 0)
    )
    if score_zero.any():
        st.warning(
            f"⚠ {int(score_zero.sum())} persona(s) have a score of 0 on at least one metric. "
            "See the **🚩 Flags** tab.",
            icon="🚩",
        )

    failed = df[df.get("api_success", pd.Series([True] * len(df))).fillna(True) == False]
    if not failed.empty:
        with st.expander(f"⚠ {len(failed)} API call(s) failed"):
            st.dataframe(failed[["user_id", "error_msg"]].fillna("—"), use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Persona detail
# ─────────────────────────────────────────────────────────────────────────────

def render_persona_detail(df: pd.DataFrame) -> None:
    st.header("Persona Drill-down")

    if df.empty:
        st.info("No data yet. Run `run_eval.py` to populate.", icon="📭")
        return

    selected = st.selectbox("Select persona", sorted(df["user_id"].tolist()))
    row = df[df["user_id"] == selected].iloc[0]
    outputs: dict   = row.get("agent_outputs") or {}
    wealth:   dict  = outputs.get("wealth")    or {}
    insurance: dict = outputs.get("insurance") or {}
    wellness:  dict = outputs.get("wellness")  or {}
    compliance: dict = outputs.get("compliance") or {}

    # Header
    halal_tag = " 🌙 Halal"  if row.get("halal_investing") else ""
    gig_tag   = " 🛵 Gig"    if row.get("is_gig_worker")    else ""
    st.markdown(
        f"### {row['user_id']}{halal_tag}{gig_tag}  \n"
        f"**{row.get('kecamatan', '?')}, {row.get('city', '?')}**  ·  "
        f"Age {row.get('age', '?')}  ·  "
        f"Rp {int(row.get('monthly_income_idr') or 0):,}/month  ·  "
        f"{str(row.get('risk_tolerance', '?')).title()}"
    )
    st.caption(
        f"Flood risk: **{float(row.get('flood_risk_score') or 0):.2f}**  ·  "
        f"Insurance: {row.get('current_insurance', '?')}  ·  "
        f"Evaluated: {row.get('evaluated_at', '?')}  ·  "
        f"Response: {row.get('response_ms', '?')} ms"
    )

    # Score badges
    st.divider()
    score_cols = st.columns(5)
    for col, m in zip(score_cols, _METRICS + ["overall"]):
        val = row.get(m)
        col.metric(_METRIC_LABELS.get(m, m), f"{val:.2f}" if pd.notna(val) else "—")

    # Violations
    violations = detect_violations(row)
    if violations:
        for v in violations:
            icon = "🚨" if v["severity"] == "critical" else "⚠️"
            st.error(f"{icon} **{v['type'].upper()}**: {v['detail']}")
    else:
        st.success("No violations for this persona.", icon="✅")

    st.divider()
    col_l, col_r = st.columns(2)

    with col_l:
        with st.expander("🧠 Wellness", expanded=True):
            dim_keys = ["diversification", "liquidity", "growth", "risk_management",
                        "tax_efficiency", "emergency_fund", "behavioural_resilience"]
            dim_vals = {k: wellness.get(k) for k in dim_keys if wellness.get(k) is not None}
            if dim_vals:
                fig = go.Figure(go.Scatterpolar(
                    r=list(dim_vals.values()),
                    theta=[k.replace("_", " ").title() for k in dim_vals],
                    fill="toself",
                    line_color="#1abc9c",
                    fillcolor="rgba(26,188,156,0.15)",
                ))
                fig.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                    height=280,
                    margin=dict(t=20, b=20, l=20, r=20),
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#ccc"),
                )
                st.plotly_chart(fig, use_container_width=True)
            st.caption(
                f"Priority gap: **{wellness.get('priority_gap', '?')}**  ·  "
                f"Overall: **{wellness.get('overall_score', '?')}**"
            )
            if wellness.get("rationale"):
                st.caption(f"*{wellness['rationale']}*")

        with st.expander("⚖️ Compliance"):
            if compliance:
                status = compliance.get("status", "?")
                st.markdown(f"**Status:** `{status}`")
                st.markdown(f"General guidance: `{compliance.get('is_general_guidance', '?')}`")
                st.markdown(f"Human confirmation: `{compliance.get('requires_human_confirmation', '?')}`")
                for d in (compliance.get("disclaimers") or [])[:2]:
                    st.caption(f"· {d}")
            else:
                st.caption("No compliance output.")

    with col_r:
        with st.expander("💰 Fund Picks", expanded=True):
            picks = wealth.get("picks") or []
            if picks:
                st.caption(
                    f"Profile used: **{wealth.get('risk_profile_used', '?')}**  ·  "
                    f"Monthly contribution: Rp {int(wealth.get('recommended_monthly_contribution_idr') or 0):,}"
                )
                for i, p in enumerate(picks, 1):
                    sharia_icon = "🌙" if p.get("is_sharia") else "❌"
                    st.markdown(
                        f"**{i}. {p.get('fund_name', '?')}** {sharia_icon}  \n"
                        f"Score {p.get('match_score', '?')}  ·  "
                        f"Risk {p.get('risk_level', '?')}  ·  "
                        f"ER {p.get('expense_ratio_pct', '?')}%  \n"
                        f"*{p.get('rationale', '')}*"
                    )
            else:
                st.caption("No wealth recommendation.")

        with st.expander("🛡️ Insurance Quote"):
            if insurance:
                trigger  = insurance.get("trigger") or {}
                payout   = insurance.get("payout_per_event_idr") or 0
                premium  = insurance.get("premium_idr") or 0
                ratio    = payout / premium if premium > 0 else 0
                kec_ok   = trigger.get("kecamatan") == row.get("kecamatan")
                kec_icon = "✓" if kec_ok else "❌"
                st.markdown(
                    f"**Trigger:** {trigger.get('metric', '?')} ≥ {trigger.get('threshold', '?')} "
                    f"{trigger.get('unit', '')}  \n"
                    f"**Kecamatan:** {trigger.get('kecamatan', '?')} {kec_icon}  \n"
                    f"**Payout:** Rp {int(payout):,} ({insurance.get('payout_multiple', '?')}× daily)  \n"
                    f"**Premium:** Rp {int(premium):,}/{insurance.get('premium_frequency', '?')}  \n"
                    f"**Ratio:** {ratio:.1f}× (payout ÷ premium)"
                )
                if not kec_ok:
                    st.error(
                        f"Expected kecamatan '{row.get('kecamatan')}', "
                        f"got '{trigger.get('kecamatan')}'"
                    )
            else:
                st.caption("No insurance quote.")

    if outputs.get("narrative"):
        with st.expander("📝 Narrative"):
            st.write(outputs["narrative"])
            st.caption(f"Next step: **{outputs.get('next_step', '?')}**")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 3 — Flags & Report (Block 2)
# ─────────────────────────────────────────────────────────────────────────────

def render_flags(df: pd.DataFrame) -> None:
    st.header("🚩 Flags & Report")
    st.caption("Surfaces violations: halal compliance · kecamatan mismatch · suitability · actuarial soundness.")

    if df.empty:
        st.info("No eval data yet. Run `run_eval.py` first.", icon="📭")
        return

    # Build flagged list
    flagged: list[dict] = []
    for _, row in df.iterrows():
        violations = detect_violations(row)
        if not violations:
            continue
        outputs: dict = row.get("agent_outputs") or {}
        wealth:  dict = outputs.get("wealth") or {}
        flagged.append({
            "user_id":            row.get("user_id", "?"),
            "kecamatan":          row.get("kecamatan", "?"),
            "city":               row.get("city", "?"),
            "risk_tolerance":     row.get("risk_tolerance", "?"),
            "halal_investing":    row.get("halal_investing", False),
            "flood_risk_score":   float(row.get("flood_risk_score") or 0),
            "monthly_income_idr": int(row.get("monthly_income_idr") or 0),
            "violations":         violations,
            "picks":              wealth.get("picks") or [],
            "suitability":        row.get("suitability"),
            "do_no_harm":         row.get("do_no_harm"),
            "claim_trigger_precision": row.get("claim_trigger_precision"),
        })

    # Summary metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Flagged personas", len(flagged), f"of {len(df)} total")
    c2.metric("🚨 Halal",
              sum(1 for f in flagged if any(v["type"] == "halal" for v in f["violations"])))
    c3.metric("🚨 Kecamatan",
              sum(1 for f in flagged if any(v["type"] == "kecamatan" for v in f["violations"])))
    c4.metric("🚨 Suitability / actuarial",
              sum(1 for f in flagged
                  if any(v["type"] in ("suitability", "actuarial") for v in f["violations"])))

    if not flagged:
        st.success("✅ No violations across all personas.", icon="✅")
    else:
        st.divider()
        st.subheader("Flagged personas")
        rows_tbl = [{
            "user_id":       f["user_id"],
            "kecamatan":     f["kecamatan"],
            "halal":         "🌙" if f["halal_investing"] else "",
            "tolerance":     f["risk_tolerance"],
            "suitability":   f["suitability"],
            "do_no_harm":    f["do_no_harm"],
            "trigger_prec":  f["claim_trigger_precision"],
            "violations":    " | ".join(v["detail"] for v in f["violations"]),
        } for f in flagged]
        st.dataframe(
            _style_scores(pd.DataFrame(rows_tbl)),
            use_container_width=True,
            height=min(60 + 35 * len(rows_tbl), 380),
        )

        st.divider()
        st.subheader("Violation details")
        for f in flagged:
            with st.expander(
                f"**{f['user_id']}** — {f['kecamatan']}, {f['city']} "
                f"{'🌙' if f['halal_investing'] else ''}"
            ):
                for v in f["violations"]:
                    icon = "🚨" if v["severity"] == "critical" else "⚠️"
                    st.error(f"{icon} **{v['type'].upper()}**: {v['detail']}")
                st.caption(
                    f"suit={f['suitability']}  dnhm={f['do_no_harm']}  "
                    f"trig={f['claim_trigger_precision']}"
                )
                if f["picks"] and f["halal_investing"]:
                    for p in f["picks"]:
                        badge = "✓ halal" if p.get("is_sharia") else "❌ NOT HALAL"
                        st.caption(f"  · {p.get('fund_name', '?')} — {badge}")

    # Download report
    st.divider()
    st.subheader("Download flag report")
    report_md = generate_flag_report(df, flagged)
    col1, col2 = st.columns([1, 3])
    with col1:
        st.download_button(
            "⬇ naik_flag_report.md",
            data=report_md,
            file_name="naik_flag_report.md",
            mime="text/markdown",
            use_container_width=True,
            type="primary",
        )
    with col2:
        st.caption(
            f"{len(df)} personas · {len(flagged)} violation(s) · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
    with st.expander("Preview report"):
        st.markdown(report_md)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    df = load_eval_data()
    if df is None:
        df = pd.DataFrame()

    render_sidebar(df)

    tab1, tab2, tab3 = st.tabs(["📊 Overview", "🔍 Persona Detail", "🚩 Flags & Report"])
    with tab1:
        render_overview(df)
    with tab2:
        render_persona_detail(df)
    with tab3:
        render_flags(df)


main()
