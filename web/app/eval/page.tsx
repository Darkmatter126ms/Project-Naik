"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { COPY } from "@/lib/copy";
import type { Lang } from "@/lib/types";

const STREAMLIT_URL =
  process.env.NEXT_PUBLIC_STREAMLIT_URL ??
  "https://naik-eval.streamlit.app"; // set NEXT_PUBLIC_STREAMLIT_URL in Vercel env vars

export default function EvalPage() {
  const [lang, setLang] = useState<Lang>("id");
  const router = useRouter();
  const t = COPY[lang];

  return (
    <div className="page page--eval">
      <div className="lang-toggle">
        <button className="lang-btn" onClick={() => setLang(lang === "id" ? "en" : "id")}>
          {t.langToggle}
        </button>
      </div>

      <button className="back-link" onClick={() => router.push("/")}>
        {t.backToHome}
      </button>

      <h1 className="page-title">{t.evalTitle}</h1>
      <p className="page-subtitle">{t.evalBody}</p>

      <div className="eval-metrics">
        {[
          { label: "Suitability", value: "—" },
          { label: "Fund-rank accuracy", value: "—" },
          { label: "Trigger precision", value: "—" },
          { label: "Do-no-harm violations", value: "—" },
        ].map((m) => (
          <div key={m.label} className="eval-metric-card">
            <span className="eval-metric-card__value">{m.value}</span>
            <span className="eval-metric-card__label">{m.label}</span>
          </div>
        ))}
      </div>

      <p className="eval-hint">
        Angka di atas akan terisi setelah Sher Min menjalankan{" "}
        <code>run_eval.py</code> dan dashboard Streamlit terhubung ke Postgres.
      </p>

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
