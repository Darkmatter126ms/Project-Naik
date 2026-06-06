"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { COPY } from "@/lib/copy";
import { useLang } from "@/lib/useLang";
import { useTheme } from "@/lib/useTheme";
import { FIXTURE_RESULT } from "@/lib/fixtures";
import WellnessRadar from "@/components/WellnessRadar";
import FundCard from "@/components/FundCard";
import InsuranceCard from "@/components/InsuranceCard";
import ComplianceBadge from "@/components/ComplianceBadge";
import { API_BASE, postIssue, ApiError } from "@/lib/api";
import type { IssuanceResponse, PersonaIdentity } from "@/lib/api";
import type { FinalResponse } from "@/lib/types";
import type { Lang } from "@/lib/types";

// ── Score gauge ────────────────────────────────────────────────────────────
function ScoreGauge({ score, lang }: { score: number; lang: Lang }) {
  const R      = 64;
  const STROKE = 10;
  const SZ     = (R + STROKE / 2 + 4) * 2;
  const C      = 2 * Math.PI * R;
  const filled = Math.min(1, Math.max(0, score / 100)) * C;

  const color =
    score >= 70 ? "var(--signal)"
    : score >= 40 ? "var(--warn)"
    : "var(--err)";

  const status =
    score >= 70
      ? lang === "id" ? "Baik"             : "Good"
      : score >= 40
      ? lang === "id" ? "Perlu Perhatian"  : "Needs Attention"
      :                 lang === "id" ? "Kritis"           : "Critical";

  const tip =
    score >= 70
      ? lang === "id"
          ? "Pertahankan momentum ini."
          : "Keep this momentum going."
      : score >= 40
      ? lang === "id"
          ? "Ada celah yang bisa Anda tutup."
          : "There are gaps you can close."
      : lang === "id"
          ? "Prioritaskan proteksi dasar dulu."
          : "Prioritise basic protection first.";

  return (
    <div className="score-gauge">
      <svg viewBox={`0 0 ${SZ} ${SZ}`} width={SZ} height={SZ} aria-hidden="true">
        <circle cx={SZ/2} cy={SZ/2} r={R} fill="none" stroke="var(--line-2)" strokeWidth={STROKE}/>
        <circle
          cx={SZ/2} cy={SZ/2} r={R} fill="none" stroke={color}
          strokeWidth={STROKE} strokeLinecap="round"
          strokeDasharray={`${filled} ${C - filled}`}
          transform={`rotate(-90 ${SZ/2} ${SZ/2})`}
          style={{ transition: "stroke-dasharray 1s ease, stroke 0.4s ease",
            filter: `drop-shadow(0 0 6px ${color === "var(--signal)" ? "rgba(94,242,163,0.4)" : color === "var(--warn)" ? "rgba(242,193,78,0.4)" : "rgba(255,107,107,0.4)"})` }}
        />
        <text x={SZ/2} y={SZ/2-6} textAnchor="middle" dominantBaseline="central"
          fontFamily="var(--display)" fontSize={score >= 100 ? 30 : 36} fontWeight="700" fill={color}>
          {score.toFixed(1)}
        </text>
        <text x={SZ/2} y={SZ/2+22} textAnchor="middle" dominantBaseline="central"
          fontFamily="var(--mono)" fontSize={11} letterSpacing="0.08em" fill="var(--fog)">
          /100
        </text>
      </svg>
      <span className="score-gauge__status" style={{ color }}>{status}</span>
      <span className="score-gauge__sublabel">
        {lang === "id" ? "Skor Kesehatan Keuangan" : "Financial Wellness Score"}
      </span>
      <p className="score-gauge__tip">{tip}</p>
    </div>
  );
}

// ── InsuranceNotShown ───────────────────────────────────────────────────────
// Insurance can be absent for two very different reasons:
//   1. Deliberate skip — the agent decided parametric flood cover is optional
//      for this profile (low flood risk + healthy risk_management, or the user
//      already holds equivalent cover). This is a CORRECT outcome; the Bahasa
//      explanation is in the narrative banner above. Render it calmly.
//   2. Agent failure ("agent_error") — the insurance agent raised; surface an
//      error so the team sees it during testing.
function InsuranceNotShown({ lang, skipReason }: { lang: Lang; skipReason?: string | null }) {
  const isId = lang === "id";
  const isFailure = !skipReason || skipReason === "agent_error";

  if (isFailure) {
    return (
      <div className="insurance-unavailable" style={{
        padding: "20px 16px",
        border: "1px dashed var(--warn, #f2c14e)",
        borderRadius: "8px",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
      }}>
        <span style={{ fontSize: "22px" }}>⚠️</span>
        <p style={{ margin: 0, fontFamily: "var(--mono)", fontSize: "13px", color: "var(--warn, #f2c14e)", fontWeight: 600 }}>
          {isId ? "Kutipan asuransi tidak tersedia" : "Insurance quote unavailable"}
        </p>
        <p style={{ margin: 0, fontSize: "12px", color: "var(--fog)", lineHeight: 1.5 }}>
          {isId
            ? "Agen asuransi gagal menghasilkan kutipan. Periksa log Render untuk detail."
            : "The insurance agent failed to produce a quote. Check Render logs for the exact exception."}
        </p>
      </div>
    );
  }

  // Deliberate skip — calm, informative card. Full reasoning is in the narrative.
  const heading =
    skipReason === "already_insured"
      ? isId ? "Anda sudah terlindungi" : "You're already covered"
      : isId ? "Perlindungan ini opsional untuk Anda" : "This cover is optional for you";
  const body =
    skipReason === "already_insured"
      ? isId
        ? "Anda menyebutkan sudah memiliki perlindungan penghasilan yang sesuai, jadi kami tidak merekomendasikan produk tambahan saat ini."
        : "You mentioned you already hold equivalent income protection, so we're not recommending an additional product right now."
      : isId
        ? "Berdasarkan skor manajemen risiko dan histori cuaca rendah-banjir di wilayah Anda, perlindungan penghasilan parametrik tidak mendesak saat ini. Tinjau kembali jika penghasilan Anda menjadi lebih tidak menentu."
        : "Based on your risk-management score and the low flood history in your area, parametric income protection isn't pressing right now. Revisit if your income becomes less stable.";

  return (
    <div className="insurance-optional" style={{
      padding: "20px 16px",
      border: "1px solid var(--line, #333)",
      borderRadius: "8px",
      display: "flex",
      flexDirection: "column",
      gap: "8px",
    }}>
      <span style={{ fontSize: "22px" }}>✓</span>
      <p style={{ margin: 0, fontFamily: "var(--mono)", fontSize: "13px", color: "var(--signal, #5ef2a3)", fontWeight: 600 }}>
        {heading}
      </p>
      <p style={{ margin: 0, fontSize: "12px", color: "var(--fog)", lineHeight: 1.5 }}>
        {body}
      </p>
    </div>
  );
}

// ── Issuance modal ─────────────────────────────────────────────────────────
type IssuancePhase = "idle" | "loading" | "filling" | "done" | "error";

function IssuanceModal({
  phase, polisId, issuedAt, errorMsg, iframeUrl, iframeRef, onIframeLoad, onClose,
}: {
  phase: IssuancePhase;
  polisId: string;
  issuedAt: string;
  errorMsg: string;
  iframeUrl: string;
  iframeRef: React.RefObject<HTMLIFrameElement>;
  onIframeLoad: () => void;
  onClose: () => void;
}) {
  if (phase === "idle") return null;

  const S = {
    overlay: { position: "fixed" as const, inset: 0, zIndex: 1000, background: "rgba(0,0,0,0.75)",
               display: "flex", alignItems: "center", justifyContent: "center", padding: "20px" },
    panel:   { background: "var(--surface, #111)", border: "1px solid var(--line, #333)", borderRadius: "12px",
               width: "min(960px,100%)", height: "min(88vh,800px)", display: "flex", flexDirection: "column" as const, overflow: "hidden" },
    header:  { display: "flex", alignItems: "center", justifyContent: "space-between",
               padding: "14px 20px", borderBottom: "1px solid var(--line, #333)", flexShrink: 0 },
    body:    { flex: 1, position: "relative" as const, overflow: "hidden" },
    iframe:  { width: "100%", height: "100%", border: "none",
               opacity: phase === "loading" ? 0.3 : 1, transition: "opacity 0.3s" },
    spinner: { position: "absolute" as const, inset: 0, display: "flex", flexDirection: "column" as const,
               alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.5)",
               pointerEvents: "none" as const },
    done:    { position: "absolute" as const, bottom: 0, left: 0, right: 0, padding: "16px 24px",
               background: "rgba(0,20,10,0.96)", borderTop: "2px solid var(--signal,#00ff90)",
               display: "flex", alignItems: "center", gap: "16px" },
    err:     { position: "absolute" as const, bottom: 0, left: 0, right: 0, padding: "14px 24px",
               background: "rgba(40,0,0,0.95)", borderTop: "2px solid #f55",
               fontFamily: "var(--mono)", fontSize: "13px", color: "#f88" },
  };

  return (
    <div style={S.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={S.panel}>
        {/* Header */}
        <div style={S.header}>
          <span style={{ fontFamily: "var(--mono)", fontSize: "13px", color: "var(--signal,#00ff90)", fontWeight: 700 }}>
            MONEEINSURE — PORTAL PENERBITAN POLIS
          </span>
          <button onClick={onClose} aria-label="Tutup"
            style={{ background: "none", border: "none", color: "var(--ink,#eee)", cursor: "pointer", fontSize: "22px", lineHeight: 1, padding: "2px 8px" }}>
            ×
          </button>
        </div>

        {/* Iframe + overlays */}
        <div style={S.body}>
          <iframe ref={iframeRef} src={iframeUrl} style={S.iframe}
            title="MoneeInsure Admin Portal" onLoad={onIframeLoad}
            sandbox="allow-scripts allow-same-origin allow-forms" />

          {phase === "loading" && (
            <div style={S.spinner}>
              <div style={{ width: 36, height: 36, borderRadius: "50%",
                border: "3px solid rgba(255,255,255,0.2)", borderTopColor: "var(--signal,#00ff90)",
                animation: "spin 0.8s linear infinite", marginBottom: 12 }} />
              <span style={{ color: "#ccc", fontSize: 13, fontFamily: "var(--mono)" }}>Mempersiapkan polis…</span>
            </div>
          )}

          {phase === "done" && (
            <div style={S.done}>
              <span style={{ fontSize: 24 }}>✅</span>
              <div>
                <div style={{ color: "var(--signal,#00ff90)", fontWeight: 700, fontFamily: "var(--mono)", fontSize: 15 }}>
                  Polis Berhasil Diterbitkan
                </div>
                <div style={{ color: "#ccc", fontSize: 12, fontFamily: "var(--mono)", marginTop: 2 }}>
                  {polisId} · {issuedAt ? new Date(issuedAt).toLocaleString("id-ID") : ""}
                </div>
              </div>
            </div>
          )}

          {phase === "error" && (
            <div style={S.err}>⚠ {errorMsg}</div>
          )}
        </div>
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

// ── Results page ───────────────────────────────────────────────────────────
export default function ResultsPage() {
  const [lang, setLang] = useLang();
  const [theme, toggleTheme] = useTheme();
  const [result, setResult] = useState<FinalResponse | null>(null);
  const [isDemo, setIsDemo] = useState(false);
  const router = useRouter();
  const t = COPY[lang];

  // Issuance state
  const [phase, setPhase]       = useState<IssuancePhase>("idle");
  const [polisId, setPolisId]   = useState("");
  const [issuedAt, setIssuedAt] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const iframeRef               = useRef<HTMLIFrameElement>(null);
  // Dual-ready: postMessage only when both the iframe has loaded AND /issue returned
  const iframeReadyRef  = useRef(false);
  const formDataRef     = useRef<Record<string, string> | null>(null);
  const issuanceDataRef = useRef<IssuanceResponse | null>(null);

  function tryPostMessage() {
    if (!iframeReadyRef.current || !formDataRef.current || !issuanceDataRef.current) return;
    iframeRef.current?.contentWindow?.postMessage(
      { type: "naik:autofill", formData: formDataRef.current }, "*"
    );
    setPhase("filling");
    // After the theatrical fill animation (~3.8 s), show the confirmation banner
    const iss = issuanceDataRef.current.issuance;
    setTimeout(() => {
      setPolisId(iss.polis_id);
      setIssuedAt(iss.issued_at);
      setPhase("done");
    }, 3_800);
  }

  function handleIframeLoad() {
    iframeReadyRef.current = true;
    tryPostMessage();
  }

  async function handleConfirm() {
    if (!result?.insurance) return;

    // Read persona identity stored by the intake page
    let persona: PersonaIdentity | null = null;
    try {
      const raw = sessionStorage.getItem("naik_persona_input");
      if (raw) {
        const p = JSON.parse(raw);
        persona = {
          user_id:            String(p.user_id ?? result.user_id),
          age:                Number(p.age ?? 25),
          monthly_income_idr: Number(p.monthly_income_idr ?? 0),
          kecamatan:          String(p.kecamatan ?? result.insurance.trigger.kecamatan),
          is_gig_worker:      Boolean(p.is_gig_worker ?? false),
          risk_tolerance:     String(p.risk_tolerance ?? "moderate"),
          household_size:     Number(p.household_size ?? 1),
        };
      }
    } catch { /* ignore */ }

    // Fallback: derive from FinalResponse what we can
    if (!persona) {
      persona = {
        user_id:            result.user_id,
        age:                25,
        monthly_income_idr: Math.round(result.insurance.estimated_daily_earnings_idr * 30),
        kecamatan:          result.insurance.trigger.kecamatan,
        is_gig_worker:      false,
        risk_tolerance:     "moderate",
        household_size:     1,
      };
    }

    // Reset dual-ready state
    iframeReadyRef.current  = false;
    formDataRef.current     = null;
    issuanceDataRef.current = null;
    setPhase("loading");
    setErrorMsg("");

    // POST /issue in parallel with iframe loading
    try {
      const resp = await postIssue({ quote: result.insurance, persona });
      issuanceDataRef.current = resp;
      formDataRef.current     = resp.form_data;
      tryPostMessage();
    } catch (err) {
      setPhase("error");
      setErrorMsg(err instanceof ApiError ? err.message : "Tidak dapat menerbitkan polis.");
    }
  }

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("naik_result");
      if (raw) {
        setResult(JSON.parse(raw) as FinalResponse);
        setIsDemo(false);
      } else {
        setResult(FIXTURE_RESULT);
        setIsDemo(true);
      }
    } catch {
      setResult(FIXTURE_RESULT);
      setIsDemo(true);
    }
  }, []);

  if (!result) {
    return (
      <div className="page page--results">
        <div className="loading-center">
          <div className="spinner" aria-label={t.loadingAriaLabel} />
          <p className="loading-label">{t.loading}</p>
        </div>
      </div>
    );
  }

  const { wellness, wealth, insurance, compliance } = result;
  const gapLabel = t.dim[wellness.priority_gap];

  return (
    <div className="page page--results">
      {/* Nav bar */}
      <div className="results-nav">
        <button className="back-link" onClick={() => router.push("/")}>{t.backToHome}</button>
        <h1 className="page-title page-title--inline">{t.resultsTitle}</h1>
        <div className="nav-controls">
          <button className="lang-btn" onClick={toggleTheme}
            aria-label="Toggle colour theme" title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
            {theme === "dark" ? "☀" : "🌙"}
          </button>
          <button className="lang-btn" onClick={() => setLang(lang === "id" ? "en" : "id")}>
            {t.langToggle}
          </button>
        </div>
      </div>

      {/* Demo banner */}
      {isDemo && (
        <div className="demo-banner" role="note">
          <span className="demo-banner__icon">🔬</span>
          <span>{t.demoBannerPre} &ldquo;{t.analyzeBtn}&rdquo; {t.demoBannerPost}</span>
          <button className="demo-banner__cta" onClick={() => router.push("/")}>{t.demoStart}</button>
        </div>
      )}

      {/* Narrative banner */}
      <div className="narrative-banner">
        <p className="narrative-banner__text">{result.narrative}</p>
        <div className="narrative-banner__gap">
          <span className="narrative-banner__gap-label">{t.priorityGap}</span>
          <span className="narrative-banner__gap-value">{gapLabel}</span>
          <span className="narrative-banner__gap-hint">{t.priorityGapLabel}</span>
        </div>
      </div>

      {/* Four panels */}
      <div className="results-grid">

        {/* Panel 1: Wellness Radar */}
        <section className="panel panel--radar">
          <h2 className="panel__title">{t.radarTitle}</h2>
          <div className="radar-panel-content">
            <div className="score-gauge-col">
              <ScoreGauge score={wellness.overall_score} lang={lang} />
              {wellness.rationale && (
                <p className="score-gauge__rationale">{wellness.rationale}</p>
              )}
            </div>
            <div className="wellness-radar-wrap">
              <WellnessRadar vector={wellness} labels={t} />
            </div>
          </div>
        </section>

        {/* Panel 2: Fund Recommendation */}
        <section className="panel panel--wealth">
          <h2 className="panel__title">{t.wealthTitle}</h2>
          {wealth ? (
            <>
              <div className="panel__body">
                {wealth.picks.map((pick, i) => (
                  <FundCard key={pick.fund_id} pick={pick}
                    allocationPct={wealth.allocation_pct?.[i]} labels={t} />
                ))}
              </div>
              <div className="panel__footer">
                <span className="metric__label">{t.monthlyContrib}</span>
                <span className="metric__value metric__value--accent">
                  Rp {wealth.recommended_monthly_contribution_idr.toLocaleString("id-ID")}
                </span>
              </div>
              <p className="panel__rationale">{wealth.rationale}</p>
            </>
          ) : (
            <p className="panel__empty">—</p>
          )}
        </section>

        {/* Panel 3: Insurance */}
        <section className="panel panel--insurance">
          <h2 className="panel__title">{t.insuranceTitle}</h2>
          <div className="panel__body">
            {insurance ? (
              <InsuranceCard quote={insurance} labels={t} />
            ) : (
              // insurance=null can mean a deliberate skip (low flood risk /
              // already insured) OR an agent failure. insurance_skip_reason
              // disambiguates: a skip renders a calm "optional cover" card with
              // the reasoning in the narrative; "agent_error"/missing renders an
              // error so the team catches real failures during testing.
              <InsuranceNotShown lang={lang} skipReason={result.insurance_skip_reason} />
            )}
          </div>
        </section>

        {/* Panel 4: Compliance */}
        <section className="panel panel--compliance">
          <h2 className="panel__title">{t.complianceTitle}</h2>
          <div className="panel__body">
            <ComplianceBadge verdict={compliance} labels={t} />
          </div>
        </section>

      </div>

      {/* Issuance modal */}
      <IssuanceModal
        phase={phase}
        polisId={polisId}
        issuedAt={issuedAt}
        errorMsg={errorMsg}
        iframeUrl={`${API_BASE}/admin/issue-form`}
        iframeRef={iframeRef}
        onIframeLoad={handleIframeLoad}
        onClose={() => setPhase("idle")}
      />

      {/* Confirm CTA */}
      <div className="cta-center results-cta">
        <button
          className="btn btn--primary btn--wide"
          onClick={handleConfirm}
          disabled={!result?.insurance || phase === "loading" || phase === "filling"}
        >
          {phase === "loading" || phase === "filling" ? "Memproses…" : t.confirmAction}
        </button>
      </div>
    </div>
  );
}
