"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { COPY } from "@/lib/copy";
import { FIXTURE_RESULT } from "@/lib/fixtures";
import WellnessRadar from "@/components/WellnessRadar";
import FundCard from "@/components/FundCard";
import InsuranceCard from "@/components/InsuranceCard";
import ComplianceBadge from "@/components/ComplianceBadge";
import type { FinalResponse, Lang } from "@/lib/types";

export default function ResultsPage() {
  const [lang, setLang] = useState<Lang>("id");
  const [result, setResult] = useState<FinalResponse>(FIXTURE_RESULT);
  const router = useRouter();
  const t = COPY[lang];

  // Load real result if available (set by /intake after a live API call)
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("naik_result");
      if (raw) setResult(JSON.parse(raw) as FinalResponse);
    } catch {
      /* use fixture */
    }
  }, []);

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
        <button className="lang-btn" onClick={() => setLang(lang === "id" ? "en" : "id")}>
          {t.langToggle}
        </button>
      </div>

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
          <div className="panel__body panel__body--center">
            <WellnessRadar vector={wellness} labels={t.dim} size={300} />
          </div>
          <div className="panel__footer">
            <span className="overall-score-label">{t.overallScore}</span>
            <span className="overall-score-value">{wellness.overall_score}</span>
            <span className="overall-score-denom">/100</span>
          </div>
          {wellness.rationale && (
            <p className="panel__rationale">{wellness.rationale}</p>
          )}
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
