// All user-facing strings. Import COPY[lang].key in every page/component.
// Keeping copy here means the Bahasa toggle is a one-liner per page.

export const COPY = {
  id: {
    // Global
    appName: "Naik",
    tagline: "Panduan keuangan cerdas di dalam Monee",
    langToggle: "EN",
    disclaimer:
      "Panduan umum saja — bukan nasihat keuangan personal. Konfirmasi manusia diperlukan.",

    // / — persona selector
    heroEyebrow: "Lapisan agentik di dalam Monee",
    heroHeadline: "Kenali Kesehatan\nKeuangan Anda",
    heroBody:
      "Naik menggabungkan data transaksi Shopee dengan wawancara suara 90 detik untuk mendiagnosis celah keuangan Anda dan merekomendasikan langkah nyata.",
    selectPersona: "Pilih persona untuk demo",
    useSari: "Gunakan Sari",
    orSpeakNow: "atau bicara langsung",
    startIntake: "Mulai Wawancara Suara",
    incomeLabel: "Penghasilan",
    locationLabel: "Lokasi",
    profileLabel: "Profil",
    gigYes: "Pekerja gig",
    gigNo: "Karyawan tetap",

    // /intake
    intakeTitle: "Wawancara Suara",
    intakeInstruction:
      "Tekan tombol dan ceritakan tentang keuangan Anda dalam Bahasa Indonesia. Anda punya 90 detik.",
    recordStart: "Mulai Bicara",
    recordStop: "Selesai",
    transcriptLabel: "Transkrip",
    transcriptPlaceholder: "Transkrip akan muncul di sini...",
    analyzing: "Menganalisis...",
    analyzeBtn: "Analisis Sekarang",
    timeLeft: "detik tersisa",

    // /results
    resultsTitle: "Hasil Diagnosis",
    overallScore: "Skor Keseluruhan",
    priorityGap: "Prioritas Utama",
    priorityGapLabel: "Dimensi terendah — fokus di sini dulu",
    radarTitle: "Peta Kesehatan Keuangan",
    wealthTitle: "Rekomendasi Investasi",
    insuranceTitle: "Proteksi Penghasilan",
    complianceTitle: "Status Kepatuhan",
    monthlyContrib: "Kontribusi Bulanan",
    fundMatchScore: "Skor Kecocokan",
    triggerLabel: "Pemicu Pembayaran",
    premiumLabel: "Premi Bulanan",
    payoutLabel: "Pembayaran per Kejadian",
    confirmedBy: "Dikonfirmasi oleh",
    human: "Manusia",
    viewDetails: "Lihat Detail",
    confirmAction: "Konfirmasi & Lanjutkan",
    backToHome: "← Kembali",

    // /eval
    evalTitle: "Dasbor Evaluasi",
    evalBody:
      "Jalankan 50 persona melalui pipeline Naik dan lihat metrik kualitas secara langsung.",
    openDashboard: "Buka Dasbor Streamlit →",

    // dimension labels (short)
    dim: {
      diversification: "Diversifikasi",
      liquidity: "Likuiditas",
      growth: "Pertumbuhan",
      risk_management: "Proteksi",
      tax_efficiency: "Efisiensi Pajak",
      emergency_fund: "Dana Darurat",
      behavioural_resilience: "Disiplin",
    },

    // fund type labels
    fundType: {
      pasar_uang: "Pasar Uang",
      pendapatan_tetap: "Pendapatan Tetap",
      campuran: "Campuran",
      saham: "Saham",
      indeks: "Indeks",
    },
  },

  en: {
    appName: "Naik",
    tagline: "Smart financial guidance inside Monee",
    langToggle: "ID",
    disclaimer:
      "General guidance only — not personalised financial advice. Human confirmation required.",

    heroEyebrow: "Agentic layer inside Monee",
    heroHeadline: "Know Your Financial\nWellness",
    heroBody:
      "Naik combines your Shopee transaction data with a 90-second voice interview to diagnose financial gaps and recommend concrete next steps.",
    selectPersona: "Select a demo persona",
    useSari: "Use Sari",
    orSpeakNow: "or speak directly",
    startIntake: "Start Voice Interview",
    incomeLabel: "Income",
    locationLabel: "Location",
    profileLabel: "Profile",
    gigYes: "Gig worker",
    gigNo: "Salaried",

    intakeTitle: "Voice Interview",
    intakeInstruction:
      "Press the button and talk about your finances in Bahasa Indonesia. You have 90 seconds.",
    recordStart: "Start Speaking",
    recordStop: "Done",
    transcriptLabel: "Transcript",
    transcriptPlaceholder: "Transcript will appear here...",
    analyzing: "Analysing...",
    analyzeBtn: "Analyse Now",
    timeLeft: "seconds left",

    resultsTitle: "Diagnosis Results",
    overallScore: "Overall Score",
    priorityGap: "Top Priority",
    priorityGapLabel: "Lowest dimension — address this first",
    radarTitle: "Financial Wellness Map",
    wealthTitle: "Investment Recommendation",
    insuranceTitle: "Income Protection",
    complianceTitle: "Compliance Status",
    monthlyContrib: "Monthly Contribution",
    fundMatchScore: "Match Score",
    triggerLabel: "Payout Trigger",
    premiumLabel: "Monthly Premium",
    payoutLabel: "Payout per Event",
    confirmedBy: "Confirmed by",
    human: "Human",
    viewDetails: "View Details",
    confirmAction: "Confirm & Proceed",
    backToHome: "← Back",

    evalTitle: "Evaluation Dashboard",
    evalBody:
      "Run 50 personas through the Naik pipeline and see quality metrics live.",
    openDashboard: "Open Streamlit Dashboard →",

    dim: {
      diversification: "Diversification",
      liquidity: "Liquidity",
      growth: "Growth",
      risk_management: "Protection",
      tax_efficiency: "Tax Efficiency",
      emergency_fund: "Emergency Fund",
      behavioural_resilience: "Discipline",
    },

    fundType: {
      pasar_uang: "Money Market",
      pendapatan_tetap: "Fixed Income",
      campuran: "Balanced",
      saham: "Equity",
      indeks: "Index",
    },
  },
} as const;

// CopyShape uses a recursive string-value type so COPY[lang] (the union of
// both locales) is assignable to it — avoiding "literal 'Diversification' not
// assignable to 'Diversifikasi'" errors when passing t = COPY[lang] to props.
export type CopyShape = {
  [K in keyof (typeof COPY)["id"]]: (typeof COPY)["id"][K] extends Record<string, string>
    ? Record<string, string>
    : string;
};
