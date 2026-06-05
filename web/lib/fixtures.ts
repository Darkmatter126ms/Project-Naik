// Hardcoded fixtures for Block 1. Matches api/stubs.py output exactly.
// FIXTURE_RESULT is kept as a demo fallback when no real result is in
// sessionStorage (e.g. direct navigation to /results, or API not configured).
//
// *_PERSONA_BASE exports are the minimum DiagnosticInput for each demo persona
// — no transactions, just the persona fields. The live voice transcript is
// merged in at POST time. The backend's do-no-harm validator is satisfied by
// voice_transcript alone.

import type { FinalResponse, Persona } from "./types";

// ─────────────────────────────────────────────────────────────────────────────
// Persona catalogue (shown on the home page persona-picker)
// ─────────────────────────────────────────────────────────────────────────────

export const PERSONAS: Persona[] = [
  {
    id: "sari",
    name: "Sari",
    age: 26,
    kecamatan: "Penjaringan",
    city: "Jakarta",
    monthly_income_idr: 6_000_000,
    risk_tolerance: "conservative",
    is_gig_worker: true,
    tagline_id: "Driver ojek online, Jakarta Utara. Satu reksa dana, tanpa asuransi.",
    tagline_en: "Online ojek driver, North Jakarta. One fund, no insurance.",
  },
  {
    id: "budi",
    name: "Budi",
    age: 22,
    kecamatan: "Tambora",
    city: "Jakarta",
    monthly_income_idr: 3_500_000,
    risk_tolerance: "conservative",
    is_gig_worker: false,
    tagline_id: "Pekerja muda, Jakarta Barat. Belum ada tabungan atau asuransi.",
    tagline_en: "Young worker, West Jakarta. No savings or insurance yet.",
  },
  {
    id: "aisyah",
    name: "Aisyah",
    age: 35,
    kecamatan: "Kebayoran Baru",
    city: "Jakarta",
    monthly_income_idr: 8_000_000,
    risk_tolerance: "moderate",
    is_gig_worker: false,
    tagline_id: "Ibu bekerja, Jakarta Selatan. Investasi syariah, dua anak.",
    tagline_en: "Working mother, South Jakarta. Sharia investing, two children.",
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Per-persona DiagnosticInput bases  (no transactions — merged at POST time)
// ─────────────────────────────────────────────────────────────────────────────

export const SARI_PERSONA_BASE: Record<string, unknown> = {
  user_id: "sari",
  locale: "id-ID",
  age: 26,
  monthly_income_idr: 6_000_000,
  kecamatan: "Penjaringan",
  city: "Jakarta",
  risk_tolerance: "conservative",
  household_size: 2,
  is_gig_worker: true,
  investment_horizon_years: 5.0,
  financial_goals: ["investasi syariah", "perlindungan penghasilan", "dana darurat"],
  transactions: [],
};

export const BUDI_PERSONA_BASE: Record<string, unknown> = {
  user_id: "budi",
  locale: "id-ID",
  age: 22,
  monthly_income_idr: 3_500_000,
  kecamatan: "Tambora",
  city: "Jakarta",
  risk_tolerance: "conservative",
  household_size: 1,
  is_gig_worker: false,
  investment_horizon_years: 10.0,
  financial_goals: ["dana darurat", "mulai investasi"],
  transactions: [],
};

export const AISYAH_PERSONA_BASE: Record<string, unknown> = {
  user_id: "aisyah",
  locale: "id-ID",
  age: 35,
  monthly_income_idr: 8_000_000,
  kecamatan: "Kebayoran Baru",
  city: "Jakarta",
  risk_tolerance: "moderate",
  household_size: 4,
  is_gig_worker: false,
  investment_horizon_years: 15.0,
  // halal signal: triggers sharia-only fund filter in the wealth agent
  financial_goals: ["investasi syariah", "dana pendidikan anak", "proteksi keluarga"],
  transactions: [],
};

/**
 * Look up the DiagnosticInput base for any demo persona by user_id.
 * Used by the cached-audio button in intake/page.tsx.
 */
export const PERSONA_BASES: Record<string, Record<string, unknown>> = {
  sari:   SARI_PERSONA_BASE,
  budi:   BUDI_PERSONA_BASE,
  aisyah: AISYAH_PERSONA_BASE,
};

// ─────────────────────────────────────────────────────────────────────────────
// Canonical 90-second voice transcripts  (one per persona)
//
// These are the written form of what each persona says during their intake.
// They live here — not in page.tsx — so they are the single source of truth.
// The cached-audio button in intake/page.tsx auto-fills from this map.
// ─────────────────────────────────────────────────────────────────────────────

export const PERSONA_TRANSCRIPTS: Record<string, string> = {
  sari:
    "Dulu saya pernah beli reksa dana di Bibit lewat Shopee, tapi cuma sekali lalu saya tinggal begitu saja. " +
    "Saya tidak punya asuransi apa pun. Saya kerja sebagai driver ojek online, jadi kalau banjir dan saya " +
    "tidak bisa keluar, penghasilan saya langsung berhenti — saya tidak terlindungi sama sekali. " +
    "Saya menabung sedikit, tapi sering tergoda checkout kalau ada diskon.",

  budi:
    "Saya Budi, umur 22 tahun, tinggal di Tambora Jakarta Barat. Saya baru setahun kerja, " +
    "gaji saya sekitar tiga setengah juta per bulan. Pengeluaran paling banyak buat kos, makan, dan ongkos. " +
    "Belum punya tabungan yang berarti — habis setiap bulan. Saya tidak punya asuransi, " +
    "tidak punya investasi sama sekali. Kalau ada kebutuhan mendadak, saya pakai SPayLater. " +
    "Saya mau mulai nabung tapi bingung dari mana karena pendapatan saya tidak banyak. " +
    "Yang paling penting buat saya sekarang adalah punya dana darurat dulu " +
    "biar tidak panik kalau ada yang tidak terduga.",

  aisyah:
    "Nama saya Aisyah, umur 35 tahun, tinggal di Jakarta Selatan. Penghasilan saya sekitar delapan juta per bulan. " +
    "Saya sudah menikah dan punya dua anak. Saya sudah punya satu reksa dana syariah, " +
    "tapi tidak yakin apakah itu sudah cukup. Asuransi saya hanya dari kantor — " +
    "kalau saya keluar kerja atau sakit panjang, penghasilan keluarga bisa terganggu. " +
    "Semua investasi saya harus sesuai prinsip syariah, itu syarat mutlak buat saya. " +
    "Saya juga ingin menyiapkan dana pendidikan untuk anak-anak. " +
    "Saya merasa portofolio saya perlu dievaluasi — mungkin terlalu terpusat di satu produk. " +
    "Saya ingin tahu apa yang harus diprioritaskan sekarang.",
};

// ─────────────────────────────────────────────────────────────────────────────
// Cached audio paths  (files live in web/public/audio/, served as static assets)
//
// The "Use cached audio" button fetches from these paths and plays the MP3
// through the browser's Audio API so judges can hear it during the demo.
// The transcript is filled from PERSONA_TRANSCRIPTS above — the two always
// travel together so the pipeline receives the text it needs.
// ─────────────────────────────────────────────────────────────────────────────

export const PERSONA_AUDIO: Record<string, string> = {
  sari:   "/audio/audio1_sari_canonical_90s.mp3",
  budi:   "/audio/audio2_budi_canonical_90s.mp3",
  aisyah: "/audio/audio3_aisyah_canonical_90s.mp3",
};

export const FIXTURE_RESULT: FinalResponse = {
  request_id: "req-demo-001",
  user_id: "sari",
  language: "id",
  wellness: {
    diversification: 72,
    liquidity: 80,
    growth: 86,
    risk_management: 15,
    tax_efficiency: 54,
    emergency_fund: 71,
    behavioural_resilience: 40,
    priority_gap: "risk_management",
    overall_score: 59.7,
    rationale:
      "Prioritas utama Anda adalah proteksi penghasilan: Anda bekerja sebagai pengemudi ojek tanpa asuransi, sehingga banjir bisa menghentikan pendapatan Anda.",
  },
  wealth: {
    user_id: "sari",
    risk_profile_used: "conservative",
    investment_horizon_years: 3,
    recommended_monthly_contribution_idr: 300_000,
    picks: [
      {
        fund_id: "SUCORINVEST-MONEY-MARKET-FUND",
        fund_name: "Sucorinvest Money Market Fund",
        fund_type: "pasar_uang",
        manager: "Sucorinvest Asset Management",
        risk_level: "low",
        expense_ratio_pct: 0.89,
        return_1y_pct: 5.01,
        return_3y_annualised_pct: 5.1,
        min_investment_idr: 10_000,
        is_ojk_licensed: true,
        is_sharia: false,
        match_score: 88,
        rationale:
          "Cocok untuk profil konservatif dan horizon pendek: likuiditas tinggi dan risiko rendah.",
      },
    ],
    allocation_pct: [100],
    rationale:
      "Mulai dari reksa dana pasar uang berlisensi OJK untuk menjaga dana tetap likuid.",
  },
  insurance: {
    quote_id: "NAIK-INC-0001",
    user_id: "sari",
    product_name: "Naik Income Shield",
    trigger: {
      metric: "rainfall_mm",
      threshold: 100,
      unit: "mm/24h",
      kecamatan: "Penjaringan",
      observation_window_hours: 24,
      data_source: "BMKG",
    },
    estimated_daily_earnings_idr: 200_000,
    payout_multiple: 3,
    payout_per_event_idr: 600_000,
    max_payouts_per_term: 2,
    coverage_term_days: 90,
    premium_idr: 18_000,
    premium_frequency: "monthly",
    expected_annual_loss_idr: 120_000,
    loss_ratio_estimate: 0.55,
  },
  compliance: {
    verdict_id: "NAIK-CMP-0001",
    status: "approved_with_conditions",
    is_general_guidance: true,
    requires_human_confirmation: true,
    reviewed: ["wellness", "wealth", "insurance"],
    flags: [],
    disclaimers: [
      "Ini adalah panduan umum, bukan nasihat keuangan personal. Konfirmasi manusia diperlukan sebelum transaksi apa pun.",
    ],
    rationale:
      "Rekomendasi sesuai profil risiko dan terjangkau terhadap penghasilan.",
  },
  narrative:
    "Prioritas pertama Anda adalah melindungi penghasilan dari risiko banjir. Kami menyarankan micro-cover proteksi penghasilan, lalu mulai menabung di reksa dana pasar uang yang likuid.",
  next_step: "confirm_both",
  disclaimers: [
    "Ini adalah panduan umum, bukan nasihat keuangan personal. Konfirmasi manusia diperlukan sebelum transaksi apa pun.",
  ],
};

export const SARI_TRANSACTIONS: Array<Record<string, unknown>> = [
  {
    "transaction_id": "sari-001",
    "timestamp": "2026-03-08T12:00:00Z",
    "amount_idr": 1400000,
    "direction": "credit",
    "category": "income",
    "description": "ojek earnings wk1",
    "merchant": null
  },
  {
    "transaction_id": "sari-002",
    "timestamp": "2026-03-08T12:00:00Z",
    "amount_idr": 38000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "pesan makan malam",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-003",
    "timestamp": "2026-03-09T12:00:00Z",
    "amount_idr": 95000,
    "direction": "debit",
    "category": "groceries",
    "description": "belanja harian",
    "merchant": "Alfamart"
  },
  {
    "transaction_id": "sari-004",
    "timestamp": "2026-03-09T12:00:00Z",
    "amount_idr": 180000,
    "direction": "debit",
    "category": "shopping",
    "description": "Shopee checkout diskon",
    "merchant": null
  },
  {
    "transaction_id": "sari-005",
    "timestamp": "2026-03-10T12:00:00Z",
    "amount_idr": 32000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan siang",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-006",
    "timestamp": "2026-03-11T12:00:00Z",
    "amount_idr": 85000,
    "direction": "debit",
    "category": "transport",
    "description": "bensin Pertamina",
    "merchant": null
  },
  {
    "transaction_id": "sari-007",
    "timestamp": "2026-03-12T12:00:00Z",
    "amount_idr": 28000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "sarapan",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-008",
    "timestamp": "2026-03-13T12:00:00Z",
    "amount_idr": 35000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan siang",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-009",
    "timestamp": "2026-03-15T12:00:00Z",
    "amount_idr": 1350000,
    "direction": "credit",
    "category": "income",
    "description": "ojek earnings wk2",
    "merchant": null
  },
  {
    "transaction_id": "sari-010",
    "timestamp": "2026-03-15T12:00:00Z",
    "amount_idr": 40000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan malam",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-011",
    "timestamp": "2026-03-16T12:00:00Z",
    "amount_idr": 310000,
    "direction": "debit",
    "category": "utilities_bills",
    "description": "listrik + air",
    "merchant": null
  },
  {
    "transaction_id": "sari-012",
    "timestamp": "2026-03-17T12:00:00Z",
    "amount_idr": 30000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan siang",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-013",
    "timestamp": "2026-03-18T12:00:00Z",
    "amount_idr": 110000,
    "direction": "debit",
    "category": "groceries",
    "description": "stok bulanan",
    "merchant": "Alfamart"
  },
  {
    "transaction_id": "sari-014",
    "timestamp": "2026-03-19T12:00:00Z",
    "amount_idr": 28000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "sarapan",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-015",
    "timestamp": "2026-03-20T12:00:00Z",
    "amount_idr": 500000,
    "direction": "debit",
    "category": "loan_repayment",
    "description": "SPayLater cicilan",
    "merchant": null
  },
  {
    "transaction_id": "sari-016",
    "timestamp": "2026-03-22T12:00:00Z",
    "amount_idr": 1500000,
    "direction": "credit",
    "category": "income",
    "description": "ojek earnings wk3",
    "merchant": null
  },
  {
    "transaction_id": "sari-017",
    "timestamp": "2026-03-22T12:00:00Z",
    "amount_idr": 45000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan malam",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-018",
    "timestamp": "2026-03-23T12:00:00Z",
    "amount_idr": 280000,
    "direction": "debit",
    "category": "shopping",
    "description": "sparepart motor (rantai + kampas rem)",
    "merchant": null
  },
  {
    "transaction_id": "sari-019",
    "timestamp": "2026-03-24T12:00:00Z",
    "amount_idr": 35000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan siang",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-020",
    "timestamp": "2026-03-25T12:00:00Z",
    "amount_idr": 105000,
    "direction": "debit",
    "category": "groceries",
    "description": "belanja harian",
    "merchant": "Alfamart"
  },
  {
    "transaction_id": "sari-021",
    "timestamp": "2026-03-26T12:00:00Z",
    "amount_idr": 30000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan siang",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-022",
    "timestamp": "2026-03-27T12:00:00Z",
    "amount_idr": 80000,
    "direction": "debit",
    "category": "transport",
    "description": "bensin",
    "merchant": null
  },
  {
    "transaction_id": "sari-023",
    "timestamp": "2026-03-29T12:00:00Z",
    "amount_idr": 1300000,
    "direction": "credit",
    "category": "income",
    "description": "ojek earnings wk4",
    "merchant": null
  },
  {
    "transaction_id": "sari-024",
    "timestamp": "2026-03-30T12:00:00Z",
    "amount_idr": 32000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan malam",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-025",
    "timestamp": "2026-03-31T12:00:00Z",
    "amount_idr": 90000,
    "direction": "debit",
    "category": "groceries",
    "description": "belanja",
    "merchant": "Alfamart"
  },
  {
    "transaction_id": "sari-026",
    "timestamp": "2026-04-05T12:00:00Z",
    "amount_idr": 1400000,
    "direction": "credit",
    "category": "income",
    "description": "ojek earnings wk5",
    "merchant": null
  },
  {
    "transaction_id": "sari-027",
    "timestamp": "2026-04-05T12:00:00Z",
    "amount_idr": 100000,
    "direction": "debit",
    "category": "investment",
    "description": "reksa dana pasar uang (sekali)",
    "merchant": "Bibit"
  },
  {
    "transaction_id": "sari-028",
    "timestamp": "2026-04-06T12:00:00Z",
    "amount_idr": 38000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan malam",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-029",
    "timestamp": "2026-04-07T12:00:00Z",
    "amount_idr": 28000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "sarapan",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-030",
    "timestamp": "2026-04-08T12:00:00Z",
    "amount_idr": 100000,
    "direction": "debit",
    "category": "groceries",
    "description": "belanja harian",
    "merchant": "Alfamart"
  },
  {
    "transaction_id": "sari-031",
    "timestamp": "2026-04-09T12:00:00Z",
    "amount_idr": 85000,
    "direction": "debit",
    "category": "transport",
    "description": "bensin",
    "merchant": null
  },
  {
    "transaction_id": "sari-032",
    "timestamp": "2026-04-10T12:00:00Z",
    "amount_idr": 33000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan siang",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-033",
    "timestamp": "2026-04-12T12:00:00Z",
    "amount_idr": 1350000,
    "direction": "credit",
    "category": "income",
    "description": "ojek earnings wk6",
    "merchant": null
  },
  {
    "transaction_id": "sari-034",
    "timestamp": "2026-04-12T12:00:00Z",
    "amount_idr": 42000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan malam",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-035",
    "timestamp": "2026-04-13T12:00:00Z",
    "amount_idr": 315000,
    "direction": "debit",
    "category": "utilities_bills",
    "description": "listrik",
    "merchant": null
  },
  {
    "transaction_id": "sari-036",
    "timestamp": "2026-04-14T12:00:00Z",
    "amount_idr": 30000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan siang",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-037",
    "timestamp": "2026-04-15T12:00:00Z",
    "amount_idr": 95000,
    "direction": "debit",
    "category": "groceries",
    "description": "Alfamart",
    "merchant": "Alfamart"
  },
  {
    "transaction_id": "sari-038",
    "timestamp": "2026-04-16T12:00:00Z",
    "amount_idr": 28000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "sarapan",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-039",
    "timestamp": "2026-04-19T12:00:00Z",
    "amount_idr": 1500000,
    "direction": "credit",
    "category": "income",
    "description": "ojek earnings wk7",
    "merchant": null
  },
  {
    "transaction_id": "sari-040",
    "timestamp": "2026-04-19T12:00:00Z",
    "amount_idr": 45000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan malam",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-041",
    "timestamp": "2026-04-20T12:00:00Z",
    "amount_idr": 150000,
    "direction": "debit",
    "category": "shopping",
    "description": "Shopee checkout",
    "merchant": null
  },
  {
    "transaction_id": "sari-042",
    "timestamp": "2026-04-21T12:00:00Z",
    "amount_idr": 35000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan siang",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-043",
    "timestamp": "2026-04-22T12:00:00Z",
    "amount_idr": 115000,
    "direction": "debit",
    "category": "groceries",
    "description": "stok mingguan",
    "merchant": "Alfamart"
  },
  {
    "transaction_id": "sari-044",
    "timestamp": "2026-04-23T12:00:00Z",
    "amount_idr": 28000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "sarapan",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-045",
    "timestamp": "2026-04-26T12:00:00Z",
    "amount_idr": 1300000,
    "direction": "credit",
    "category": "income",
    "description": "ojek earnings wk8",
    "merchant": null
  },
  {
    "transaction_id": "sari-046",
    "timestamp": "2026-04-27T12:00:00Z",
    "amount_idr": 35000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan malam",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-047",
    "timestamp": "2026-04-28T12:00:00Z",
    "amount_idr": 500000,
    "direction": "debit",
    "category": "loan_repayment",
    "description": "SPayLater cicilan",
    "merchant": null
  },
  {
    "transaction_id": "sari-048",
    "timestamp": "2026-04-29T12:00:00Z",
    "amount_idr": 80000,
    "direction": "debit",
    "category": "transport",
    "description": "bensin",
    "merchant": null
  },
  {
    "transaction_id": "sari-049",
    "timestamp": "2026-05-03T12:00:00Z",
    "amount_idr": 1400000,
    "direction": "credit",
    "category": "income",
    "description": "ojek earnings wk9",
    "merchant": null
  },
  {
    "transaction_id": "sari-050",
    "timestamp": "2026-05-03T12:00:00Z",
    "amount_idr": 38000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan malam",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-051",
    "timestamp": "2026-05-04T12:00:00Z",
    "amount_idr": 100000,
    "direction": "debit",
    "category": "groceries",
    "description": "belanja harian",
    "merchant": "Alfamart"
  },
  {
    "transaction_id": "sari-052",
    "timestamp": "2026-05-05T12:00:00Z",
    "amount_idr": 30000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan siang",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-053",
    "timestamp": "2026-05-06T12:00:00Z",
    "amount_idr": 28000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "sarapan",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-054",
    "timestamp": "2026-05-07T12:00:00Z",
    "amount_idr": 305000,
    "direction": "debit",
    "category": "utilities_bills",
    "description": "listrik",
    "merchant": null
  },
  {
    "transaction_id": "sari-055",
    "timestamp": "2026-05-10T12:00:00Z",
    "amount_idr": 1350000,
    "direction": "credit",
    "category": "income",
    "description": "ojek earnings wk10",
    "merchant": null
  },
  {
    "transaction_id": "sari-056",
    "timestamp": "2026-05-10T12:00:00Z",
    "amount_idr": 40000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan malam",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-057",
    "timestamp": "2026-05-11T12:00:00Z",
    "amount_idr": 85000,
    "direction": "debit",
    "category": "transport",
    "description": "bensin",
    "merchant": null
  },
  {
    "transaction_id": "sari-058",
    "timestamp": "2026-05-12T12:00:00Z",
    "amount_idr": 32000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan siang",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-059",
    "timestamp": "2026-05-13T12:00:00Z",
    "amount_idr": 95000,
    "direction": "debit",
    "category": "groceries",
    "description": "belanja Alfamart",
    "merchant": "Alfamart"
  },
  {
    "transaction_id": "sari-060",
    "timestamp": "2026-05-17T12:00:00Z",
    "amount_idr": 1500000,
    "direction": "credit",
    "category": "income",
    "description": "ojek earnings wk11",
    "merchant": null
  },
  {
    "transaction_id": "sari-061",
    "timestamp": "2026-05-17T12:00:00Z",
    "amount_idr": 45000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan malam",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-062",
    "timestamp": "2026-05-18T12:00:00Z",
    "amount_idr": 120000,
    "direction": "debit",
    "category": "shopping",
    "description": "Shopee checkout",
    "merchant": null
  },
  {
    "transaction_id": "sari-063",
    "timestamp": "2026-05-19T12:00:00Z",
    "amount_idr": 35000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan siang",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-064",
    "timestamp": "2026-05-20T12:00:00Z",
    "amount_idr": 90000,
    "direction": "debit",
    "category": "groceries",
    "description": "stok mingguan",
    "merchant": "Alfamart"
  },
  {
    "transaction_id": "sari-065",
    "timestamp": "2026-05-21T12:00:00Z",
    "amount_idr": 500000,
    "direction": "debit",
    "category": "loan_repayment",
    "description": "SPayLater cicilan",
    "merchant": null
  },
  {
    "transaction_id": "sari-066",
    "timestamp": "2026-05-24T12:00:00Z",
    "amount_idr": 1300000,
    "direction": "credit",
    "category": "income",
    "description": "ojek earnings wk12",
    "merchant": null
  },
  {
    "transaction_id": "sari-067",
    "timestamp": "2026-05-25T12:00:00Z",
    "amount_idr": 32000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "makan malam",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-068",
    "timestamp": "2026-05-26T12:00:00Z",
    "amount_idr": 80000,
    "direction": "debit",
    "category": "transport",
    "description": "bensin",
    "merchant": null
  },
  {
    "transaction_id": "sari-069",
    "timestamp": "2026-05-27T12:00:00Z",
    "amount_idr": 28000,
    "direction": "debit",
    "category": "food_beverage",
    "description": "sarapan",
    "merchant": "GoFood"
  },
  {
    "transaction_id": "sari-070",
    "timestamp": "2026-05-28T12:00:00Z",
    "amount_idr": 100000,
    "direction": "debit",
    "category": "groceries",
    "description": "belanja harian",
    "merchant": "Alfamart"
  }
];
