// Hardcoded fixtures for Block 1. Matches api/stubs.py output exactly.
// Phase 2: replace FIXTURE_RESULT with a real fetch to /orchestrate.

import type { FinalResponse, Persona } from "./types";

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
];

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
