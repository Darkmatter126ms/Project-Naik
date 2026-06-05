"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { COPY } from "@/lib/copy";
import { useLang } from "@/lib/useLang";
import { useTheme } from "@/lib/useTheme";
import { FIXTURE_RESULT } from "@/lib/fixtures";
import WellnessRadar from "@/components/WellnessRadar";
import FundCard from "@/components/FundCard";
import InsuranceCard from "@/components/InsuranceCard";
import ComplianceBadge from "@/components/ComplianceBadge";
import type { FinalResponse } from "@/lib/types";
import type { Lang } from "@/lib/types";

// ── Score gauge ────────────────────────────────────────────────────────────
// Circular progress ring whose colour and status text reflect the wellness
// score:  ≥ 70 = green · 40–69 = amber · < 40 = red.
function ScoreGauge({ score, lang }: { score: number; lang: Lang }) {
  const R      = 64;
  const STROKE = 10;
  const SZ     = (R + STROKE / 2 + 4) * 2;      // ~152
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
        {/* Track */}
        <circle
          cx={SZ / 2} cy={SZ / 2} r={R}
          fill="none"
          stroke="var(--line-2)"
          strokeWidth={STROKE}
        />
        {/* Arc */}
        <circle
          cx={SZ / 2} cy={SZ / 2} r={R}
          fill="none"
          stroke={color}
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${C - filled}`}
          transform={`rotate(-90 ${SZ / 2} ${SZ / 2})`}
          style={{
            transition: "stroke-dasharray 1s ease, stroke 0.4s ease",
            filter: `drop-shadow(0 0 6px ${color === "var(--signal)" ? "rgba(94,242,163,0.4)" : color === "var(--warn)" ? "rgba(242,193,78,0.4)" : "rgba(255,107,107,0.4)"})`,
          }}
        />
        {/* Score number */}
        <text
          x={SZ / 2} y={SZ / 2 - 6}
          textAnchor="middle"
          dominantBaseline="central"
          fontFamily="var(--display)"
          fontSize={score >= 100 ? 30 : 36}
          fontWeight="700"
          fill={color}
        >
          {score.toFixed(1)}
        </text>
        {/* /100 */}
        <text
          x={SZ / 2} y={SZ / 2 + 22}
          textAnchor="middle"
          dominantBaseline="central"
          fontFamily="var(--mono)"
          fontSize={11}
          letterSpacing="0.08em"
          fill="var(--fog)"
        >
          /100
        </text>
      </svg>

      {/* Status + hint */}
      <span className="score-gauge__status" style={{ color }}>{status}</span>
      <span className="score-gauge__sublabel">
        {lang === "id" ? "Skor Kesehatan Keuangan" : "Financial Wellness Score"}
      </span>
      <p className="score-gauge__tip">{tip}</p>
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
        <button className="back-link" onClick={() => router.push("/")}>
          {t.backToHome}
        </button>
        <h1 className="page-title page-title--inline">{t.resultsTitle}</h1>
        <div className="nav-controls">
          <button
            className="lang-btn"
            onClick={toggleTheme}
            aria-label="Toggle colour theme"
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? "☀" : "🌙"}
          </button>
          <button
            className="lang-btn"
            onClick={() => setLang(lang === "id" ? "en" : "id")}
          >
            {t.langToggle}
          </button>
        </div>
      </div>

      {/* Demo banner */}
      {isDemo && (
        <div className="demo-banner" role="note">
          <span className="demo-banner__icon">🔬</span>
          <span>
            {t.demoBannerPre} &ldquo;{t.analyzeBtn}&rdquo; {t.demoBannerPost}
          </span>
          <button className="demo-banner__cta" onClick={() => router.push("/")}>
            {t.demoStart}
          </button>
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
          {/*
            Gauge left · Radar right.
            ScoreGauge is fixed-width; WellnessRadar fills the remaining space.
            The 500×500 internal coordinate space ensures all axis labels stay
            within the SVG viewBox regardless of the rendered pixel size.
          */}
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
                  <FundCard
                    key={pick.fund_id}
                    pick={pick}
                    allocationPct={wealth.allocation_pct?.[i]}
                    labels={t}
                  />
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
              <p className="panel__empty">—</p>
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

      {/* Confirm CTA */}
      <div className="cta-center results-cta">
        <button className="btn btn--primary btn--wide">
          {t.confirmAction}
        </button>
      </div>
    </div>
  );
}
