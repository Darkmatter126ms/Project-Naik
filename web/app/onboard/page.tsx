"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { COPY } from "@/lib/copy";
import { useLang } from "@/lib/useLang";
import { useTheme } from "@/lib/useTheme";

// ── District → City lookup (matches generate_personas.DISTRICTS exactly) ── //
const KECAMATAN_CITY: Record<string, string> = {
  // Jakarta
  Penjaringan: "Jakarta", Pluit: "Jakarta", Kapuk: "Jakarta",
  "Muara Baru": "Jakarta", Cengkareng: "Jakarta", Kalideres: "Jakarta",
  Tambora: "Jakarta", Cilincing: "Jakarta", "Tanjung Priok": "Jakarta",
  "Duren Sawit": "Jakarta", Tebet: "Jakarta", Menteng: "Jakarta",
  Kebayoran: "Jakarta", Cilandak: "Jakarta", "Pondok Indah": "Jakarta",
  // Surabaya
  Kenjeran: "Surabaya", Semampir: "Surabaya", Krembangan: "Surabaya",
  Benowo: "Surabaya", Asemrowo: "Surabaya", "Pabean Cantikan": "Surabaya",
  Wonokromo: "Surabaya", Rungkut: "Surabaya", Gubeng: "Surabaya",
  // Medan
  "Medan Belawan": "Medan", "Medan Deli": "Medan", "Medan Labuhan": "Medan",
  "Medan Barat": "Medan", "Medan Helvetia": "Medan", "Medan Baru": "Medan",
};

const BY_CITY: Record<string, string[]> = {
  Jakarta: [
    "Penjaringan", "Pluit", "Kapuk", "Muara Baru", "Cengkareng", "Kalideres",
    "Tambora", "Cilincing", "Tanjung Priok", "Duren Sawit", "Tebet",
    "Menteng", "Kebayoran", "Cilandak", "Pondok Indah",
  ],
  Surabaya: [
    "Kenjeran", "Semampir", "Krembangan", "Benowo", "Asemrowo",
    "Pabean Cantikan", "Wonokromo", "Rungkut", "Gubeng",
  ],
  Medan: [
    "Medan Belawan", "Medan Deli", "Medan Labuhan",
    "Medan Barat", "Medan Helvetia", "Medan Baru",
  ],
};

type RiskTolerance = "conservative" | "moderate" | "aggressive";

interface FormState {
  age:          string;
  income:       string;
  kecamatan:    string;
  isGigWorker:  boolean;
  riskTolerance: RiskTolerance | "";
  halal:        boolean;
}

// ── Builds a DiagnosticInput-compatible object from the form ─────────────── //
function buildPersona(form: FormState): Record<string, unknown> {
  const goals = ["dana darurat", "perlindungan penghasilan"];
  if (form.halal)      goals.push("investasi syariah");
  else                 goals.push("investasi reksa dana");
  if (form.isGigWorker) goals.push("proteksi pendapatan tidak tetap");

  return {
    user_id:                 `user_${Date.now()}`,
    age:                     parseInt(form.age, 10),
    monthly_income_idr:      parseInt(form.income, 10),
    kecamatan:               form.kecamatan,
    city:                    KECAMATAN_CITY[form.kecamatan] ?? "Jakarta",
    risk_tolerance:          form.riskTolerance as RiskTolerance,
    household_size:          2,
    is_gig_worker:           form.isGigWorker,
    investment_horizon_years: 5,
    financial_goals:         goals,
    transactions:            [],
  };
}

// ── Returns the set of field keys that are invalid ───────────────────────── //
function validate(form: FormState): Set<string> {
  const errs = new Set<string>();
  const age = parseInt(form.age, 10);
  if (!form.age || isNaN(age) || age < 17 || age > 100) errs.add("age");
  const income = parseInt(form.income, 10);
  if (!form.income || isNaN(income) || income < 500_000) errs.add("income");
  if (!form.kecamatan)    errs.add("kecamatan");
  if (!form.riskTolerance) errs.add("riskTolerance");
  return errs;
}

// ── Toggle component ─────────────────────────────────────────────────────── //
function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="toggle-switch">
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
      />
      <span className="toggle-slider" />
    </label>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────── //
export default function OnboardPage() {
  const [lang, setLang] = useLang();
  const [theme, toggleTheme] = useTheme();
  const router = useRouter();
  const t = COPY[lang];

  const [form, setForm] = useState<FormState>({
    age: "", income: "", kecamatan: "",
    isGigWorker: false, riskTolerance: "", halal: false,
  });
  // Only show validation errors after first submit attempt
  const [submitted, setSubmitted] = useState(false);

  const errors = submitted ? validate(form) : new Set<string>();

  function set<K extends keyof FormState>(key: K, val: FormState[K]) {
    setForm(prev => ({ ...prev, [key]: val }));
  }

  function handleSubmit() {
    setSubmitted(true);
    if (validate(form).size > 0) return;
    sessionStorage.setItem("naik_persona", JSON.stringify(buildPersona(form)));
    router.push("/intake");
  }

  const RISK_OPTIONS: Array<{ value: RiskTolerance; title: string; desc: string }> = [
    { value: "conservative", title: t.riskConservativeTitle, desc: t.riskConservativeDesc },
    { value: "moderate",     title: t.riskModerateTitle,     desc: t.riskModerateDesc },
    { value: "aggressive",   title: t.riskAggressiveTitle,   desc: t.riskAggressiveDesc },
  ];

  const errMsg = {
    age:          lang === "id" ? "Usia harus antara 17–100 tahun" : "Age must be between 17 and 100",
    income:       lang === "id" ? "Masukkan penghasilan bulanan (min. Rp 500.000)" : "Enter monthly income (min. Rp 500,000)",
    kecamatan:    lang === "id" ? "Pilih kecamatan Anda" : "Select your district",
    riskTolerance: lang === "id" ? "Pilih profil risiko Anda" : "Select your risk profile",
  };

  return (
    <div className="page page--onboard">
      {/* Controls */}
      <div className="lang-toggle">
        <button className="lang-btn" onClick={toggleTheme} aria-label="Toggle theme">
          {theme === "dark" ? "☀" : "🌙"}
        </button>
        <button className="lang-btn" onClick={() => setLang(lang === "id" ? "en" : "id")}>
          {t.langToggle}
        </button>
      </div>

      <button className="back-link" onClick={() => router.push("/")}>
        {t.backToHome}
      </button>

      <h1 className="page-title">{t.onboardTitle}</h1>
      <p className="page-subtitle">{t.onboardSubtitle}</p>

      <div className="onboard-form">

        {/* ── Section 1: About You ────────────────────────────────────────── */}
        <div className="form-section">
          <span className="form-section__title">{t.onboardSectionYou}</span>

          <div className="form-fields-grid">
            {/* Age */}
            <div className="form-field">
              <label className="form-label" htmlFor="f-age">{t.ageLabel}</label>
              <input
                id="f-age"
                className={`form-input${errors.has("age") ? " form-input--error" : ""}`}
                type="number"
                min={17} max={100}
                placeholder={t.agePlaceholder}
                value={form.age}
                onChange={e => set("age", e.target.value)}
              />
              {errors.has("age") && <span className="form-error">{errMsg.age}</span>}
            </div>

            {/* Monthly income */}
            <div className="form-field">
              <label className="form-label" htmlFor="f-income">{t.incomeLabel}</label>
              <div className="form-input-prefix">
                <input
                  id="f-income"
                  className={`form-input${errors.has("income") ? " form-input--error" : ""}`}
                  type="number"
                  min={500000}
                  step={100000}
                  placeholder={t.incomePlaceholder}
                  value={form.income}
                  onChange={e => set("income", e.target.value)}
                />
              </div>
              {errors.has("income") && <span className="form-error">{errMsg.income}</span>}
            </div>
          </div>

          {/* Kecamatan */}
          <div className="form-field">
            <label className="form-label" htmlFor="f-kecamatan">{t.kecamatanLabel}</label>
            <div className="form-select-wrap">
              <select
                id="f-kecamatan"
                className={`form-select${errors.has("kecamatan") ? " form-input--error" : ""}`}
                value={form.kecamatan}
                onChange={e => set("kecamatan", e.target.value)}
              >
                <option value="">{t.kecamatanPlaceholder}</option>
                {Object.entries(BY_CITY).map(([city, districts]) => (
                  <optgroup key={city} label={city}>
                    {districts.map(d => (
                      <option key={d} value={d}>{d}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
            {errors.has("kecamatan") && <span className="form-error">{errMsg.kecamatan}</span>}
          </div>
        </div>

        {/* ── Section 2: Financial Preferences ───────────────────────────── */}
        <div className="form-section">
          <span className="form-section__title">{t.onboardSectionFinance}</span>

          {/* Gig worker toggle */}
          <div className="toggle-row">
            <div className="toggle-row__label">
              <span className="toggle-row__title">{t.gigYes}</span>
              <span className="toggle-row__desc">
                {lang === "id"
                  ? "Ojek, freelance, atau penghasilan tidak tetap"
                  : "Ojek, freelance, or irregular income"}
              </span>
            </div>
            <Toggle checked={form.isGigWorker} onChange={v => set("isGigWorker", v)} />
          </div>

          {/* Halal toggle */}
          <div className="toggle-row">
            <div className="toggle-row__label">
              <span className="toggle-row__title">{t.halalLabel}</span>
              <span className="toggle-row__desc">{t.halalDesc}</span>
            </div>
            <Toggle checked={form.halal} onChange={v => set("halal", v)} />
          </div>

          {/* Risk tolerance — 3 cards, explicit choice required */}
          <div className="form-field">
            <label className="form-label">{t.riskLabel}</label>
            <div className="risk-cards">
              {RISK_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  className={`risk-card${form.riskTolerance === opt.value ? " risk-card--selected" : ""}`}
                  onClick={() => set("riskTolerance", opt.value)}
                >
                  <span className="risk-card__title">{opt.title}</span>
                  <span className="risk-card__desc">{opt.desc}</span>
                </button>
              ))}
            </div>
            {errors.has("riskTolerance") && (
              <span className="form-error">{errMsg.riskTolerance}</span>
            )}
          </div>
        </div>

        <div className="cta-center">
          <button className="btn btn--primary btn--wide" onClick={handleSubmit}>
            {t.continueToIntake}
          </button>
        </div>

      </div>
    </div>
  );
}
