"use client";

import { useRouter } from "next/navigation";
import { COPY } from "@/lib/copy";
import { useLang } from "@/lib/useLang";
import { useTheme } from "@/lib/useTheme";
import {
  PERSONAS,
  PERSONA_BASES,
  SARI_TRANSACTIONS,
  BUDI_TRANSACTIONS,
  AISYAH_TRANSACTIONS,
} from "@/lib/fixtures";

// 90-day transaction histories keyed by persona id.
// Sari: 70-tx Shopee gig-worker history.
// Budi: 74-tx salaried worker (KRL commute, GoFood, SPayLater cicilan).
// Aisyah: 68-tx working mother (family groceries, school fees, halal Bibit investment).
const PERSONA_TRANSACTIONS: Record<string, unknown[]> = {
  sari:   SARI_TRANSACTIONS,
  budi:   BUDI_TRANSACTIONS,
  aisyah: AISYAH_TRANSACTIONS,
};

export default function HomePage() {
  const [lang, setLang] = useLang();
  const [theme, toggleTheme] = useTheme();
  const router = useRouter();
  const t = COPY[lang];

  function selectPersona(personaId: string) {
    const base = PERSONA_BASES[personaId];
    if (!base) return;
    sessionStorage.setItem("naik_persona", JSON.stringify({
      ...base,
      transactions: PERSONA_TRANSACTIONS[personaId] ?? [],
    }));
    router.push("/intake");
  }

  function startDirect() {
    sessionStorage.removeItem("naik_persona");
    router.push("/onboard");
  }

  // Avatar initial — first letter of persona name
  function initial(name: string) {
    return name.charAt(0).toUpperCase();
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

      {/* Persona selector — all three rendered dynamically */}
      <p className="section-label">{t.selectPersona}</p>
      <div className="persona-list">
        {PERSONAS.map((persona) => {
          const base = PERSONA_BASES[persona.id] as Record<string, unknown>;
          const isGig    = Boolean(base?.is_gig_worker);
          const isHalal  = (base?.financial_goals as string[] | undefined)?.some(g =>
            g.toLowerCase().includes("syariah"),
          );
          const income   = Number(base?.monthly_income_idr ?? 0).toLocaleString("id-ID");
          const tagline  = lang === "id" ? persona.tagline_id : persona.tagline_en;

          return (
            <div key={persona.id} className="persona-card">
              <div className="persona-card__avatar">{initial(persona.name)}</div>
              <div className="persona-card__body">
                <div className="persona-card__name-row">
                  <span className="persona-card__name">{persona.name}</span>
                  <span className="persona-card__age">{persona.age} thn</span>
                  {isGig && (
                    <span className="persona-card__gig">{t.gigYes}</span>
                  )}
                </div>

                <div className="persona-card__stats">
                  <div className="stat">
                    <span className="stat__label">{t.incomeLabel}</span>
                    <span className="stat__value">Rp {income}/bln</span>
                  </div>
                  <div className="stat">
                    <span className="stat__label">{t.locationLabel}</span>
                    <span className="stat__value">{persona.kecamatan}, {persona.city}</span>
                  </div>
                  <div className="stat">
                    <span className="stat__label">{t.profileLabel}</span>
                    <span className="stat__value">
                      {persona.risk_tolerance === "conservative" ? t.riskConservativeTitle : persona.risk_tolerance === "moderate" ? t.riskModerateTitle : t.riskAggressiveTitle}
                      {isHalal ? " · Syariah" : ""}
                    </span>
                  </div>
                </div>

                <p className="persona-card__meta">{tagline}</p>

                <div className="persona-card__actions">
                  <button
                    className="btn btn--primary"
                    onClick={() => selectPersona(persona.id)}
                  >
                    {/* Re-use useSari label for Sari; generic label for others */}
                    {persona.id === "sari"
                      ? t.useSari
                      : lang === "id"
                        ? `Pilih ${persona.name}`
                        : `Use ${persona.name}`}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
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
