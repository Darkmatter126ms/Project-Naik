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

// ─────────────────────────────────────────────────────────────────────────────
// Cached voice intake types + data  (Hilda / H-3-2)
// Each entry is a pre-recorded Bahasa Indonesia intake that can be played back
// for demos.  `transcriptSegments` lets the UI reveal the transcript word-by-word
// in sync with the audio.
// ─────────────────────────────────────────────────────────────────────────────

export interface TranscriptSegment {
  text: string;
  durationMs: number;
}

export interface CachedVoiceIntake {
  id: string;
  label: string;
  /** Path relative to /public, e.g. "/audio/audio1_sari_canonical_90s.mp3" */
  audioSrc: string;
  /** Total playback duration in ms — used to cap the fake countdown */
  playbackMs: number;
  /** Word-by-word reveal schedule in sync with the audio */
  transcriptSegments: TranscriptSegment[];
  /** Full transcript (used once audio ends or on fallback) */
  transcript: string;
  /** DiagnosticInput-shaped persona this intake belongs to */
  persona: Record<string, unknown>;
}

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

export const BUDI_TRANSACTIONS: Array<Record<string, unknown>> = [
  { "transaction_id": "budi-b001", "timestamp": "2026-03-09T09:00:00Z", "amount_idr": 1750000, "direction": "credit", "category": "income", "description": "gaji Maret wk1-2", "merchant": null },
  { "transaction_id": "budi-b002", "timestamp": "2026-03-10T10:00:00Z", "amount_idr": 700000, "direction": "debit", "category": "utilities_bills", "description": "kos bulan Maret", "merchant": null },
  { "transaction_id": "budi-b003", "timestamp": "2026-03-11T12:00:00Z", "amount_idr": 35000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b004", "timestamp": "2026-03-12T08:00:00Z", "amount_idr": 32000, "direction": "debit", "category": "food_beverage", "description": "sarapan", "merchant": "GoFood" },
  { "transaction_id": "budi-b005", "timestamp": "2026-03-13T19:00:00Z", "amount_idr": 28000, "direction": "debit", "category": "food_beverage", "description": "makan malam", "merchant": "GoFood" },
  { "transaction_id": "budi-b006", "timestamp": "2026-03-14T11:00:00Z", "amount_idr": 55000, "direction": "debit", "category": "groceries", "description": "belanja mingguan", "merchant": "Indomaret" },
  { "transaction_id": "budi-b007", "timestamp": "2026-03-15T07:00:00Z", "amount_idr": 48000, "direction": "debit", "category": "transport", "description": "KRL mingguan", "merchant": null },
  { "transaction_id": "budi-b008", "timestamp": "2026-03-16T12:00:00Z", "amount_idr": 33000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b009", "timestamp": "2026-03-18T12:00:00Z", "amount_idr": 30000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b010", "timestamp": "2026-03-19T20:00:00Z", "amount_idr": 78000, "direction": "debit", "category": "shopping", "description": "Shopee checkout", "merchant": null },
  { "transaction_id": "budi-b011", "timestamp": "2026-03-20T08:00:00Z", "amount_idr": 28000, "direction": "debit", "category": "food_beverage", "description": "sarapan", "merchant": "GoFood" },
  { "transaction_id": "budi-b012", "timestamp": "2026-03-22T07:00:00Z", "amount_idr": 48000, "direction": "debit", "category": "transport", "description": "KRL mingguan", "merchant": null },
  { "transaction_id": "budi-b013", "timestamp": "2026-03-23T09:00:00Z", "amount_idr": 1750000, "direction": "credit", "category": "income", "description": "gaji Maret wk3-4", "merchant": null },
  { "transaction_id": "budi-b014", "timestamp": "2026-03-23T11:00:00Z", "amount_idr": 200000, "direction": "debit", "category": "loan_repayment", "description": "SPayLater cicilan", "merchant": null },
  { "transaction_id": "budi-b015", "timestamp": "2026-03-24T12:00:00Z", "amount_idr": 60000, "direction": "debit", "category": "groceries", "description": "Indomaret stok", "merchant": "Indomaret" },
  { "transaction_id": "budi-b016", "timestamp": "2026-03-25T12:00:00Z", "amount_idr": 35000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b017", "timestamp": "2026-03-27T08:00:00Z", "amount_idr": 32000, "direction": "debit", "category": "food_beverage", "description": "sarapan", "merchant": "GoFood" },
  { "transaction_id": "budi-b018", "timestamp": "2026-03-28T19:00:00Z", "amount_idr": 30000, "direction": "debit", "category": "food_beverage", "description": "makan malam", "merchant": "GoFood" },
  { "transaction_id": "budi-b019", "timestamp": "2026-03-29T07:00:00Z", "amount_idr": 48000, "direction": "debit", "category": "transport", "description": "KRL mingguan", "merchant": null },
  { "transaction_id": "budi-b020", "timestamp": "2026-03-30T12:00:00Z", "amount_idr": 33000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b021", "timestamp": "2026-04-01T11:00:00Z", "amount_idr": 115000, "direction": "debit", "category": "utilities_bills", "description": "listrik + kuota", "merchant": null },
  { "transaction_id": "budi-b022", "timestamp": "2026-04-02T20:00:00Z", "amount_idr": 45000, "direction": "debit", "category": "food_beverage", "description": "makan malam", "merchant": "GoFood" },
  { "transaction_id": "budi-b023", "timestamp": "2026-04-03T12:00:00Z", "amount_idr": 28000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b024", "timestamp": "2026-04-05T07:00:00Z", "amount_idr": 48000, "direction": "debit", "category": "transport", "description": "KRL mingguan", "merchant": null },
  { "transaction_id": "budi-b025", "timestamp": "2026-04-06T11:00:00Z", "amount_idr": 55000, "direction": "debit", "category": "groceries", "description": "belanja mingguan", "merchant": "Indomaret" },
  { "transaction_id": "budi-b026", "timestamp": "2026-04-08T09:00:00Z", "amount_idr": 1750000, "direction": "credit", "category": "income", "description": "gaji April wk1-2", "merchant": null },
  { "transaction_id": "budi-b027", "timestamp": "2026-04-08T10:00:00Z", "amount_idr": 700000, "direction": "debit", "category": "utilities_bills", "description": "kos bulan April", "merchant": null },
  { "transaction_id": "budi-b028", "timestamp": "2026-04-09T12:00:00Z", "amount_idr": 35000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b029", "timestamp": "2026-04-10T08:00:00Z", "amount_idr": 30000, "direction": "debit", "category": "food_beverage", "description": "sarapan", "merchant": "GoFood" },
  { "transaction_id": "budi-b030", "timestamp": "2026-04-11T19:00:00Z", "amount_idr": 28000, "direction": "debit", "category": "food_beverage", "description": "makan malam", "merchant": "GoFood" },
  { "transaction_id": "budi-b031", "timestamp": "2026-04-12T07:00:00Z", "amount_idr": 48000, "direction": "debit", "category": "transport", "description": "KRL mingguan", "merchant": null },
  { "transaction_id": "budi-b032", "timestamp": "2026-04-13T11:00:00Z", "amount_idr": 65000, "direction": "debit", "category": "groceries", "description": "Indomaret stok", "merchant": "Indomaret" },
  { "transaction_id": "budi-b033", "timestamp": "2026-04-15T12:00:00Z", "amount_idr": 33000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b034", "timestamp": "2026-04-16T20:00:00Z", "amount_idr": 120000, "direction": "debit", "category": "shopping", "description": "Shopee Lebaran checkout", "merchant": null },
  { "transaction_id": "budi-b035", "timestamp": "2026-04-17T12:00:00Z", "amount_idr": 40000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b036", "timestamp": "2026-04-18T19:00:00Z", "amount_idr": 28000, "direction": "debit", "category": "food_beverage", "description": "makan malam", "merchant": "GoFood" },
  { "transaction_id": "budi-b037", "timestamp": "2026-04-19T07:00:00Z", "amount_idr": 48000, "direction": "debit", "category": "transport", "description": "KRL mingguan", "merchant": null },
  { "transaction_id": "budi-b038", "timestamp": "2026-04-20T12:00:00Z", "amount_idr": 35000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b039", "timestamp": "2026-04-21T11:00:00Z", "amount_idr": 60000, "direction": "debit", "category": "groceries", "description": "belanja mingguan", "merchant": "Indomaret" },
  { "transaction_id": "budi-b040", "timestamp": "2026-04-22T09:00:00Z", "amount_idr": 1750000, "direction": "credit", "category": "income", "description": "gaji April wk3-4", "merchant": null },
  { "transaction_id": "budi-b041", "timestamp": "2026-04-22T11:00:00Z", "amount_idr": 200000, "direction": "debit", "category": "loan_repayment", "description": "SPayLater cicilan", "merchant": null },
  { "transaction_id": "budi-b042", "timestamp": "2026-04-24T12:00:00Z", "amount_idr": 35000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b043", "timestamp": "2026-04-25T08:00:00Z", "amount_idr": 32000, "direction": "debit", "category": "food_beverage", "description": "sarapan", "merchant": "GoFood" },
  { "transaction_id": "budi-b044", "timestamp": "2026-04-26T07:00:00Z", "amount_idr": 48000, "direction": "debit", "category": "transport", "description": "KRL mingguan", "merchant": null },
  { "transaction_id": "budi-b045", "timestamp": "2026-04-28T12:00:00Z", "amount_idr": 33000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b046", "timestamp": "2026-04-29T11:00:00Z", "amount_idr": 110000, "direction": "debit", "category": "utilities_bills", "description": "listrik + internet", "merchant": null },
  { "transaction_id": "budi-b047", "timestamp": "2026-05-01T12:00:00Z", "amount_idr": 35000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b048", "timestamp": "2026-05-02T19:00:00Z", "amount_idr": 25000, "direction": "debit", "category": "food_beverage", "description": "makan malam", "merchant": "GoFood" },
  { "transaction_id": "budi-b049", "timestamp": "2026-05-03T07:00:00Z", "amount_idr": 48000, "direction": "debit", "category": "transport", "description": "KRL mingguan", "merchant": null },
  { "transaction_id": "budi-b050", "timestamp": "2026-05-04T11:00:00Z", "amount_idr": 60000, "direction": "debit", "category": "groceries", "description": "Indomaret stok", "merchant": "Indomaret" },
  { "transaction_id": "budi-b051", "timestamp": "2026-05-08T09:00:00Z", "amount_idr": 1750000, "direction": "credit", "category": "income", "description": "gaji Mei wk1-2", "merchant": null },
  { "transaction_id": "budi-b052", "timestamp": "2026-05-08T10:00:00Z", "amount_idr": 700000, "direction": "debit", "category": "utilities_bills", "description": "kos bulan Mei", "merchant": null },
  { "transaction_id": "budi-b053", "timestamp": "2026-05-09T12:00:00Z", "amount_idr": 35000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b054", "timestamp": "2026-05-10T08:00:00Z", "amount_idr": 30000, "direction": "debit", "category": "food_beverage", "description": "sarapan", "merchant": "GoFood" },
  { "transaction_id": "budi-b055", "timestamp": "2026-05-11T19:00:00Z", "amount_idr": 28000, "direction": "debit", "category": "food_beverage", "description": "makan malam", "merchant": "GoFood" },
  { "transaction_id": "budi-b056", "timestamp": "2026-05-12T07:00:00Z", "amount_idr": 48000, "direction": "debit", "category": "transport", "description": "KRL mingguan", "merchant": null },
  { "transaction_id": "budi-b057", "timestamp": "2026-05-13T11:00:00Z", "amount_idr": 62000, "direction": "debit", "category": "groceries", "description": "belanja mingguan", "merchant": "Indomaret" },
  { "transaction_id": "budi-b058", "timestamp": "2026-05-15T12:00:00Z", "amount_idr": 33000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b059", "timestamp": "2026-05-17T20:00:00Z", "amount_idr": 89000, "direction": "debit", "category": "shopping", "description": "Shopee checkout", "merchant": null },
  { "transaction_id": "budi-b060", "timestamp": "2026-05-19T07:00:00Z", "amount_idr": 48000, "direction": "debit", "category": "transport", "description": "KRL mingguan", "merchant": null },
  { "transaction_id": "budi-b061", "timestamp": "2026-05-20T12:00:00Z", "amount_idr": 35000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b062", "timestamp": "2026-05-21T19:00:00Z", "amount_idr": 30000, "direction": "debit", "category": "food_beverage", "description": "makan malam", "merchant": "GoFood" },
  { "transaction_id": "budi-b063", "timestamp": "2026-05-22T09:00:00Z", "amount_idr": 1750000, "direction": "credit", "category": "income", "description": "gaji Mei wk3-4", "merchant": null },
  { "transaction_id": "budi-b064", "timestamp": "2026-05-22T11:00:00Z", "amount_idr": 200000, "direction": "debit", "category": "loan_repayment", "description": "SPayLater cicilan", "merchant": null },
  { "transaction_id": "budi-b065", "timestamp": "2026-05-23T11:00:00Z", "amount_idr": 65000, "direction": "debit", "category": "groceries", "description": "Indomaret stok", "merchant": "Indomaret" },
  { "transaction_id": "budi-b066", "timestamp": "2026-05-24T12:00:00Z", "amount_idr": 35000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b067", "timestamp": "2026-05-25T08:00:00Z", "amount_idr": 32000, "direction": "debit", "category": "food_beverage", "description": "sarapan", "merchant": "GoFood" },
  { "transaction_id": "budi-b068", "timestamp": "2026-05-26T07:00:00Z", "amount_idr": 48000, "direction": "debit", "category": "transport", "description": "KRL mingguan", "merchant": null },
  { "transaction_id": "budi-b069", "timestamp": "2026-05-27T11:00:00Z", "amount_idr": 110000, "direction": "debit", "category": "utilities_bills", "description": "listrik", "merchant": null },
  { "transaction_id": "budi-b070", "timestamp": "2026-05-29T12:00:00Z", "amount_idr": 33000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "budi-b071", "timestamp": "2026-05-31T19:00:00Z", "amount_idr": 28000, "direction": "debit", "category": "food_beverage", "description": "makan malam", "merchant": "GoFood" },
  { "transaction_id": "budi-b072", "timestamp": "2026-06-02T07:00:00Z", "amount_idr": 48000, "direction": "debit", "category": "transport", "description": "KRL mingguan", "merchant": null },
  { "transaction_id": "budi-b073", "timestamp": "2026-06-04T11:00:00Z", "amount_idr": 60000, "direction": "debit", "category": "groceries", "description": "belanja mingguan", "merchant": "Indomaret" },
  { "transaction_id": "budi-b074", "timestamp": "2026-06-05T12:00:00Z", "amount_idr": 35000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
];

export const AISYAH_TRANSACTIONS: Array<Record<string, unknown>> = [
  { "transaction_id": "aisyah-a001", "timestamp": "2026-03-09T09:00:00Z", "amount_idr": 8000000, "direction": "credit", "category": "income", "description": "gaji Maret", "merchant": null },
  { "transaction_id": "aisyah-a002", "timestamp": "2026-03-10T10:00:00Z", "amount_idr": 500000, "direction": "debit", "category": "utilities_bills", "description": "SPP anak bulan Maret", "merchant": null },
  { "transaction_id": "aisyah-a003", "timestamp": "2026-03-11T11:00:00Z", "amount_idr": 350000, "direction": "debit", "category": "groceries", "description": "belanja mingguan keluarga", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a004", "timestamp": "2026-03-12T12:00:00Z", "amount_idr": 95000, "direction": "debit", "category": "food_beverage", "description": "makan siang keluarga", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a005", "timestamp": "2026-03-13T10:00:00Z", "amount_idr": 300000, "direction": "debit", "category": "investment", "description": "reksa dana syariah Bibit", "merchant": "Bibit" },
  { "transaction_id": "aisyah-a006", "timestamp": "2026-03-14T19:00:00Z", "amount_idr": 120000, "direction": "debit", "category": "food_beverage", "description": "makan malam keluarga", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a007", "timestamp": "2026-03-15T11:00:00Z", "amount_idr": 250000, "direction": "debit", "category": "shopping", "description": "Shopee kebutuhan rumah", "merchant": null },
  { "transaction_id": "aisyah-a008", "timestamp": "2026-03-16T08:00:00Z", "amount_idr": 100000, "direction": "debit", "category": "transport", "description": "Grab mingguan", "merchant": "Grab" },
  { "transaction_id": "aisyah-a009", "timestamp": "2026-03-18T11:00:00Z", "amount_idr": 380000, "direction": "debit", "category": "groceries", "description": "belanja mingguan Indomaret", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a010", "timestamp": "2026-03-19T12:00:00Z", "amount_idr": 80000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a011", "timestamp": "2026-03-21T20:00:00Z", "amount_idr": 185000, "direction": "debit", "category": "shopping", "description": "Shopee buku anak", "merchant": null },
  { "transaction_id": "aisyah-a012", "timestamp": "2026-03-22T19:00:00Z", "amount_idr": 110000, "direction": "debit", "category": "food_beverage", "description": "makan malam keluarga", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a013", "timestamp": "2026-03-23T10:00:00Z", "amount_idr": 480000, "direction": "debit", "category": "utilities_bills", "description": "listrik + air + internet", "merchant": null },
  { "transaction_id": "aisyah-a014", "timestamp": "2026-03-25T11:00:00Z", "amount_idr": 320000, "direction": "debit", "category": "groceries", "description": "belanja mingguan", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a015", "timestamp": "2026-03-26T12:00:00Z", "amount_idr": 90000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a016", "timestamp": "2026-03-27T08:00:00Z", "amount_idr": 100000, "direction": "debit", "category": "transport", "description": "Grab mingguan", "merchant": "Grab" },
  { "transaction_id": "aisyah-a017", "timestamp": "2026-03-29T11:00:00Z", "amount_idr": 350000, "direction": "debit", "category": "groceries", "description": "stok mingguan Indomaret", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a018", "timestamp": "2026-03-30T12:00:00Z", "amount_idr": 95000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a019", "timestamp": "2026-04-01T20:00:00Z", "amount_idr": 320000, "direction": "debit", "category": "shopping", "description": "Shopee baju lebaran anak", "merchant": null },
  { "transaction_id": "aisyah-a020", "timestamp": "2026-04-02T19:00:00Z", "amount_idr": 130000, "direction": "debit", "category": "food_beverage", "description": "makan malam keluarga", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a021", "timestamp": "2026-04-03T08:00:00Z", "amount_idr": 100000, "direction": "debit", "category": "transport", "description": "Grab mingguan", "merchant": "Grab" },
  { "transaction_id": "aisyah-a022", "timestamp": "2026-04-05T11:00:00Z", "amount_idr": 360000, "direction": "debit", "category": "groceries", "description": "belanja akhir bulan", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a023", "timestamp": "2026-04-06T12:00:00Z", "amount_idr": 80000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a024", "timestamp": "2026-04-08T09:00:00Z", "amount_idr": 8000000, "direction": "credit", "category": "income", "description": "gaji April", "merchant": null },
  { "transaction_id": "aisyah-a025", "timestamp": "2026-04-08T10:00:00Z", "amount_idr": 500000, "direction": "debit", "category": "utilities_bills", "description": "SPP anak bulan April", "merchant": null },
  { "transaction_id": "aisyah-a026", "timestamp": "2026-04-09T10:00:00Z", "amount_idr": 300000, "direction": "debit", "category": "investment", "description": "reksa dana syariah Bibit", "merchant": "Bibit" },
  { "transaction_id": "aisyah-a027", "timestamp": "2026-04-10T11:00:00Z", "amount_idr": 370000, "direction": "debit", "category": "groceries", "description": "belanja mingguan keluarga", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a028", "timestamp": "2026-04-11T12:00:00Z", "amount_idr": 90000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a029", "timestamp": "2026-04-12T08:00:00Z", "amount_idr": 100000, "direction": "debit", "category": "transport", "description": "Grab mingguan", "merchant": "Grab" },
  { "transaction_id": "aisyah-a030", "timestamp": "2026-04-13T19:00:00Z", "amount_idr": 115000, "direction": "debit", "category": "food_beverage", "description": "makan malam keluarga", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a031", "timestamp": "2026-04-14T20:00:00Z", "amount_idr": 290000, "direction": "debit", "category": "shopping", "description": "Shopee kebutuhan dapur", "merchant": null },
  { "transaction_id": "aisyah-a032", "timestamp": "2026-04-15T11:00:00Z", "amount_idr": 350000, "direction": "debit", "category": "groceries", "description": "Indomaret belanja", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a033", "timestamp": "2026-04-17T12:00:00Z", "amount_idr": 85000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a034", "timestamp": "2026-04-19T15:00:00Z", "amount_idr": 490000, "direction": "debit", "category": "utilities_bills", "description": "listrik + air", "merchant": null },
  { "transaction_id": "aisyah-a035", "timestamp": "2026-04-20T11:00:00Z", "amount_idr": 340000, "direction": "debit", "category": "groceries", "description": "Indomaret mingguan", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a036", "timestamp": "2026-04-21T12:00:00Z", "amount_idr": 95000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a037", "timestamp": "2026-04-22T08:00:00Z", "amount_idr": 100000, "direction": "debit", "category": "transport", "description": "Grab mingguan", "merchant": "Grab" },
  { "transaction_id": "aisyah-a038", "timestamp": "2026-04-23T19:00:00Z", "amount_idr": 120000, "direction": "debit", "category": "food_beverage", "description": "makan malam keluarga", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a039", "timestamp": "2026-04-25T20:00:00Z", "amount_idr": 180000, "direction": "debit", "category": "shopping", "description": "Shopee alat tulis anak", "merchant": null },
  { "transaction_id": "aisyah-a040", "timestamp": "2026-04-26T11:00:00Z", "amount_idr": 360000, "direction": "debit", "category": "groceries", "description": "stok mingguan", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a041", "timestamp": "2026-04-28T12:00:00Z", "amount_idr": 80000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a042", "timestamp": "2026-04-30T08:00:00Z", "amount_idr": 100000, "direction": "debit", "category": "transport", "description": "Grab mingguan", "merchant": "Grab" },
  { "transaction_id": "aisyah-a043", "timestamp": "2026-05-01T11:00:00Z", "amount_idr": 330000, "direction": "debit", "category": "groceries", "description": "Indomaret belanja", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a044", "timestamp": "2026-05-03T19:00:00Z", "amount_idr": 110000, "direction": "debit", "category": "food_beverage", "description": "makan malam keluarga", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a045", "timestamp": "2026-05-04T12:00:00Z", "amount_idr": 85000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a046", "timestamp": "2026-05-06T11:00:00Z", "amount_idr": 370000, "direction": "debit", "category": "groceries", "description": "belanja akhir bulan", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a047", "timestamp": "2026-05-08T09:00:00Z", "amount_idr": 8000000, "direction": "credit", "category": "income", "description": "gaji Mei", "merchant": null },
  { "transaction_id": "aisyah-a048", "timestamp": "2026-05-08T10:00:00Z", "amount_idr": 500000, "direction": "debit", "category": "utilities_bills", "description": "SPP anak bulan Mei", "merchant": null },
  { "transaction_id": "aisyah-a049", "timestamp": "2026-05-09T10:00:00Z", "amount_idr": 300000, "direction": "debit", "category": "investment", "description": "reksa dana syariah Bibit", "merchant": "Bibit" },
  { "transaction_id": "aisyah-a050", "timestamp": "2026-05-10T11:00:00Z", "amount_idr": 360000, "direction": "debit", "category": "groceries", "description": "belanja mingguan keluarga", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a051", "timestamp": "2026-05-11T12:00:00Z", "amount_idr": 90000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a052", "timestamp": "2026-05-12T08:00:00Z", "amount_idr": 100000, "direction": "debit", "category": "transport", "description": "Grab mingguan", "merchant": "Grab" },
  { "transaction_id": "aisyah-a053", "timestamp": "2026-05-14T19:00:00Z", "amount_idr": 125000, "direction": "debit", "category": "food_beverage", "description": "makan malam keluarga", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a054", "timestamp": "2026-05-15T20:00:00Z", "amount_idr": 215000, "direction": "debit", "category": "shopping", "description": "Shopee kebutuhan rumah", "merchant": null },
  { "transaction_id": "aisyah-a055", "timestamp": "2026-05-17T11:00:00Z", "amount_idr": 345000, "direction": "debit", "category": "groceries", "description": "Indomaret mingguan", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a056", "timestamp": "2026-05-18T12:00:00Z", "amount_idr": 85000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a057", "timestamp": "2026-05-19T15:00:00Z", "amount_idr": 475000, "direction": "debit", "category": "utilities_bills", "description": "listrik + air + internet", "merchant": null },
  { "transaction_id": "aisyah-a058", "timestamp": "2026-05-21T08:00:00Z", "amount_idr": 100000, "direction": "debit", "category": "transport", "description": "Grab mingguan", "merchant": "Grab" },
  { "transaction_id": "aisyah-a059", "timestamp": "2026-05-22T11:00:00Z", "amount_idr": 355000, "direction": "debit", "category": "groceries", "description": "stok mingguan", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a060", "timestamp": "2026-05-23T12:00:00Z", "amount_idr": 90000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a061", "timestamp": "2026-05-24T19:00:00Z", "amount_idr": 110000, "direction": "debit", "category": "food_beverage", "description": "makan malam keluarga", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a062", "timestamp": "2026-05-26T20:00:00Z", "amount_idr": 275000, "direction": "debit", "category": "shopping", "description": "Shopee baju anak", "merchant": null },
  { "transaction_id": "aisyah-a063", "timestamp": "2026-05-27T11:00:00Z", "amount_idr": 340000, "direction": "debit", "category": "groceries", "description": "Indomaret belanja", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a064", "timestamp": "2026-05-29T08:00:00Z", "amount_idr": 100000, "direction": "debit", "category": "transport", "description": "Grab mingguan", "merchant": "Grab" },
  { "transaction_id": "aisyah-a065", "timestamp": "2026-05-31T12:00:00Z", "amount_idr": 85000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a066", "timestamp": "2026-06-02T11:00:00Z", "amount_idr": 360000, "direction": "debit", "category": "groceries", "description": "belanja akhir bulan", "merchant": "Indomaret" },
  { "transaction_id": "aisyah-a067", "timestamp": "2026-06-04T19:00:00Z", "amount_idr": 115000, "direction": "debit", "category": "food_beverage", "description": "makan malam keluarga", "merchant": "GoFood" },
  { "transaction_id": "aisyah-a068", "timestamp": "2026-06-05T12:00:00Z", "amount_idr": 90000, "direction": "debit", "category": "food_beverage", "description": "makan siang", "merchant": "GoFood" },
];

// ─────────────────────────────────────────────────────────────────────────────
// CACHED_VOICE_INTAKES — three demo intakes with segment timelines
// Audio files live in web/public/audio/
// ─────────────────────────────────────────────────────────────────────────────

export const CACHED_VOICE_INTAKES: CachedVoiceIntake[] = [
  {
    id: "sari-canonical",
    label: "Sari — ojek driver, Penjaringan",
    audioSrc: "/audio/audio1_sari_canonical_90s.mp3",
    playbackMs: 90_000,
    transcriptSegments: [
      { text: "Dulu saya pernah beli reksa dana di Bibit lewat Shopee,", durationMs: 8_000 },
      { text: "tapi cuma sekali lalu saya tinggal begitu saja.", durationMs: 7_000 },
      { text: "Saya tidak punya asuransi apa pun.", durationMs: 5_000 },
      { text: "Saya kerja sebagai driver ojek online,", durationMs: 6_000 },
      { text: "jadi kalau banjir dan saya tidak bisa keluar,", durationMs: 6_000 },
      { text: "penghasilan saya langsung berhenti —", durationMs: 5_000 },
      { text: "saya tidak terlindungi sama sekali.", durationMs: 5_000 },
      { text: "Saya menabung sedikit,", durationMs: 4_000 },
      { text: "tapi sering tergoda checkout kalau ada diskon.", durationMs: 6_000 },
    ],
    transcript:
      "Dulu saya pernah beli reksa dana di Bibit lewat Shopee, tapi cuma sekali lalu saya tinggal begitu saja. " +
      "Saya tidak punya asuransi apa pun. Saya kerja sebagai driver ojek online, jadi kalau banjir dan saya " +
      "tidak bisa keluar, penghasilan saya langsung berhenti — saya tidak terlindungi sama sekali. " +
      "Saya menabung sedikit, tapi sering tergoda checkout kalau ada diskon.",
    persona: {
      ...SARI_PERSONA_BASE,
      transactions: SARI_TRANSACTIONS,
    },
  },
  {
    id: "male-younger-lower-income",
    label: "Budi — salaried, Tambora",
    audioSrc: "/audio/audio2_budi_canonical_90s.mp3",
    playbackMs: 82_000,
    transcriptSegments: [
      { text: "Saya baru mulai kerja serabutan", durationMs: 6_000 },
      { text: "dan penghasilan saya tidak tetap.", durationMs: 5_000 },
      { text: "Kalau ada uang lebih, saya simpan sedikit,", durationMs: 7_000 },
      { text: "tapi saya juga sering bantu keluarga.", durationMs: 6_000 },
      { text: "Saya belum punya asuransi", durationMs: 5_000 },
      { text: "dan belum sempat investasi", durationMs: 4_000 },
      { text: "karena takut uangnya kepakai lagi untuk kebutuhan harian.", durationMs: 6_000 },
    ],
    transcript:
      "Saya baru mulai kerja serabutan dan penghasilan saya tidak tetap. " +
      "Kalau ada uang lebih, saya simpan sedikit, tapi saya juga sering bantu keluarga. " +
      "Saya belum punya asuransi dan belum sempat investasi " +
      "karena takut uangnya kepakai lagi untuk kebutuhan harian.",
    // Correct Budi persona: age 22, Tambora, salaried
    persona: {
      ...BUDI_PERSONA_BASE,
      transactions: BUDI_TRANSACTIONS,
    },
  },
  {
    id: "female-older-halal",
    label: "Aisyah — halal investing, Kebayoran Baru",
    audioSrc: "/audio/audio3_aisyah_canonical_90s.mp3",
    playbackMs: 78_000,
    transcriptSegments: [
      { text: "Saya ingin produk yang sesuai syariah", durationMs: 6_000 },
      { text: "dan aman untuk jangka menengah.", durationMs: 5_000 },
      { text: "Saat ini saya sedang menyiapkan dana pendidikan anak", durationMs: 7_000 },
      { text: "dan dana darurat.", durationMs: 4_000 },
      { text: "Saya lebih nyaman kalau investasi saya transparan, halal,", durationMs: 7_000 },
      { text: "dan tidak terlalu berisiko.", durationMs: 5_000 },
    ],
    transcript:
      "Saya ingin produk yang sesuai syariah dan aman untuk jangka menengah. " +
      "Saat ini saya sedang menyiapkan dana pendidikan anak dan dana darurat. " +
      "Saya lebih nyaman kalau investasi saya transparan, halal, dan tidak terlalu berisiko.",
    // Correct Aisyah persona: age 35, Kebayoran Baru, household 4, syariah goals
    persona: {
      ...AISYAH_PERSONA_BASE,
      transactions: AISYAH_TRANSACTIONS,
    },
  },
];
