"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { COPY } from "@/lib/copy";
import { useLang } from "@/lib/useLang";

const STREAMLIT_URL =
  process.env.NEXT_PUBLIC_STREAMLIT_URL ??
  "https://naik-eval.streamlit.app";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "https://naik-api.onrender.com";

// Shape returned by GET /eval-summary
interface EvalSummary {
  status: "ok" | "no_data" | "error";
  personas_evaluated: number;
  suitability: number | null;
  fund_rank_correctness: number | null;
  claim_trigger_precision: number | null;
  do_no_harm: number | null;
  last_run: string | null;
}

/** Format a 0–1 score as a percentage string, e.g. 0.98 → "98.0%" */
function fmtScore(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

export default function EvalPage() {
  const [lang, setLang] = useLang();
  const router = useRouter();
  const t = COPY[lang];

  const [summary, setSummary] = useState<EvalSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchSummary() {
      try {
        const res = await fetch(`${API_BASE}/eval-summary`, {
          cache: "no-store",
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: EvalSummary = await res.json();
        if (!cancelled) setSummary(data);
      } catch {
        // Network failure — leave summary null so cards show "—" gracefully
        if (!cancelled) setSummary(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchSummary();
    return () => { cancelled = true; };
  }, []);

  // "…" while fetching, real score or "—" once settled
  const val = (key: keyof EvalSummary): string => {
    if (loading) return "…";
    if (!summary || summary.status !== "ok") return "—";
    return fmtScore(summary[key] as number | null);
  };

  const metrics = [
    { key: "suitability",             label: t.evalMetricSuitability },
    { key: "fund_rank_correctness",   label: t.evalMetricFundRank    },
    { key: "claim_trigger_precision", label: t.evalMetricTrigger     },
    { key: "do_no_harm",              label: t.evalMetricDoNoHarm    },
  ] as const;

  return (
    <div className="page page--eval">
      <div className="lang-toggle">
        <button
          className="lang-btn"
          onClick={() => setLang(lang === "id" ? "en" : "id")}
        >
          {t.langToggle}
        </button>
      </div>

      <button className="back-link" onClick={() => router.push("/")}>
        {t.backToHome}
      </button>

      <h1 className="page-title">{t.evalTitle}</h1>
      <p className="page-subtitle">{t.evalBody}</p>

      <div className="eval-metrics">
        {metrics.map((m) => (
          <div key={m.key} className="eval-metric-card">
            <span className="eval-metric-card__value">{val(m.key)}</span>
            <span className="eval-metric-card__label">{m.label}</span>
          </div>
        ))}
      </div>

      {/* Persona count + timestamp — shown only when live data is available */}
      {summary?.status === "ok" && (
        <p className="eval-hint">
          {summary.personas_evaluated} personas evaluated
          {summary.last_run
            ? ` · last run ${new Date(summary.last_run).toLocaleString()}`
            : ""}
        </p>
      )}

      {/* Static hint when no eval data exists yet */}
      {!loading && summary?.status !== "ok" && (
        <p className="eval-hint">{t.evalHint}</p>
      )}

      <div className="cta-center">
        <a
          className="btn btn--primary btn--wide"
          href={STREAMLIT_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t.openDashboard}
        </a>
      </div>
    </div>
  );
}
