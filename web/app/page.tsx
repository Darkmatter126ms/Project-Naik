"use client";

import { useRouter } from "next/navigation";
import { COPY } from "@/lib/copy";
import { useLang } from "@/lib/useLang";
import { useTheme } from "@/lib/useTheme";
import { SARI_PERSONA_BASE, SARI_TRANSACTIONS } from "@/lib/fixtures";

export default function HomePage() {
  const [lang, setLang] = useLang();
  const [theme, toggleTheme] = useTheme();
  const router = useRouter();
  const t = COPY[lang];

  function selectSari() {
    // Write Sari's full profile including her 70-transaction Shopee history
    // so the diagnostic agent reads real spending patterns — not just transcript.
    sessionStorage.setItem("naik_persona", JSON.stringify({
      ...SARI_PERSONA_BASE,
      transactions: SARI_TRANSACTIONS,
    }));
    router.push("/intake");
  }

  function startDirect() {
    // Clear any stale persona so the onboard form starts fresh
    sessionStorage.removeItem("naik_persona");
    router.push("/onboard");
  }

  return (
    <div className="page page--home">
      {/* Controls */}
      <div className="lang-toggle">
        <button className="lang-btn" onClick={toggleTheme} aria-label="Toggle theme">
          {theme === "dark" ? "☀" : "🌙"}
        </button>
        <button className="lang-btn" onClick={() => setLang(lang === "id" ? "en" : "id")}>
          {t.langToggle}
        </button>
      </div>

      {/* Hero */}
      <div className="hero">
        <p className="hero__eyebrow">{t.heroEyebrow}</p>
        <h1 className="hero__headline">
          {t.heroHeadline.split("\n").map((line, i) => (
            <span key={i} className="hero__headline-line">{line}</span>
          ))}
        </h1>
        <p className="hero__body">{t.heroBody}</p>
      </div>

      {/* Persona selector */}
      <p className="section-label">{t.selectPersona}</p>
      <div className="persona-list">
        <div className="persona-card">
          <div className="persona-card__avatar">S</div>
          <div className="persona-card__body">
            <div className="persona-card__name-row">
              <span className="persona-card__name">Sari Dewi</span>
              <span className="persona-card__age">26 thn</span>
              <span className="persona-card__gig">
                {t.gigYes}
              </span>
            </div>
            <div className="persona-card__stats">
              <div className="stat">
                <span className="stat__label">{t.incomeLabel}</span>
                <span className="stat__value">Rp 6.000.000/bln</span>
              </div>
              <div className="stat">
                <span className="stat__label">{t.locationLabel}</span>
                <span className="stat__value">Penjaringan, Jakarta</span>
              </div>
              <div className="stat">
                <span className="stat__label">{t.profileLabel}</span>
                <span className="stat__value">Conservative · Syariah</span>
              </div>
            </div>
            <p className="persona-card__meta">
              {lang === "id"
                ? "Pernah beli 1 reksa dana Bibit lewat Shopee lalu ghosting. Tidak punya asuransi selain credit-life SPayLater."
                : "Bought one Bibit fund through Shopee, then went dark. Only coverage is the credit-life policy bundled with SPayLater."}
            </p>

            <div className="persona-card__actions">
              <button className="btn btn--primary" onClick={selectSari}>
                {t.useSari}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Or speak directly */}
      <div className="divider-or">{t.orSpeakNow}</div>
      <div className="cta-center">
        <button className="btn btn--outline btn--wide" onClick={startDirect}>
          {t.startIntake}
        </button>
      </div>

      {/* Eval link */}
      <div className="home-eval-link">
        <button className="back-link" onClick={() => router.push("/eval")}>
          {lang === "id" ? "Lihat Dasbor Evaluasi →" : "View Evaluation Dashboard →"}
        </button>
      </div>
    </div>
  );
}
