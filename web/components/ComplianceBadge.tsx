import type { ComplianceVerdict } from "@/lib/types";
import type { CopyShape } from "@/lib/copy";

interface Props {
  verdict: ComplianceVerdict;
  labels: CopyShape;
}

// Green for approved outcomes, red for everything else.
const isApproved = (status: string) =>
  status === "approved" || status === "approved_with_conditions";

// Maps the Bahasa backend disclaimer strings to locale keys.
// The backend always returns Bahasa (regulatory record); we translate in the UI.
const DISCLAIMER_KEY_MAP: Record<string, keyof CopyShape> = {
  "Ini adalah panduan umum, bukan nasihat keuangan yang dipersonalisasi, sesuai ketentuan OJK.": "disclaimerGeneral",
  "Kinerja masa lalu tidak menjamin hasil di masa depan.": "disclaimerPastPerf",
  "Investasi reksa dana mengandung risiko; nilai investasi dapat naik atau turun.": "disclaimerInvestRisk",
  "Konfirmasi manual diperlukan sebelum melakukan transaksi apa pun.": "disclaimerManualConfirm",
  "Asuransi parametrik membayar berdasarkan indeks cuaca BMKG, bukan penilaian kerugian individual.": "disclaimerParametric",
  "Beberapa pernyataan telah disesuaikan agar tidak menjanjikan hasil atau jaminan tertentu.": "disclaimerRewritten",
  "Terdapat dana yang belum tersertifikasi syariah; perlu tinjauan sebelum ditawarkan kepada investor syariah.": "disclaimerSharia",
};

// Maps the Bahasa compliance rationale prefix to a locale key.
const RATIONALE_KEY = "complianceRationale";
const RATIONALE_ID_PREFIX = "Semua keluaran ditinjau";

export default function ComplianceBadge({ verdict, labels }: Props) {
  const approved = isApproved(verdict.status);
  const statusColor = approved ? "var(--signal)" : "var(--err)";
  const statusBg   = approved ? "var(--signal-bg)" : "var(--err-bg)";

  // Status label from locale (e.g. "Disetujui" / "Approved")
  const statusLabel =
    labels.complianceStatus[verdict.status] ?? verdict.status;

  // Translate compliance rationale: if it starts with the Bahasa prefix,
  // replace with the locale string; otherwise show as-is.
  const rationaleText = verdict.rationale?.startsWith(RATIONALE_ID_PREFIX)
    ? (labels[RATIONALE_KEY] as string ?? verdict.rationale)
    : verdict.rationale;

  return (
    <div className="compliance-badge">

      {/* ── Status pill — green if approved, red otherwise ── */}
      <div
        className="compliance-badge__pill"
        style={{ background: statusBg, borderColor: statusColor }}
      >
        <span
          className="compliance-badge__dot"
          style={{ background: statusColor, boxShadow: `0 0 8px ${statusColor}` }}
        />
        <span
          className="compliance-badge__label"
          style={{ color: statusColor }}
        >
          {statusLabel}
        </span>
      </div>

      {/* ── Human confirmation gate — ALWAYS shown (regulatory requirement) ── */}
      <div className="compliance-badge__gate">
        <span className="compliance-badge__gate-icon">👤</span>
        <div className="compliance-badge__gate-text">
          <span className="compliance-badge__gate-heading">
            {labels.confirmationGateHeading}
          </span>
          <span className="compliance-badge__gate-sub">
            {labels.confirmationGateSub}
          </span>
        </div>
      </div>

      {/* Rationale — translated via locale map */}
      <p className="compliance-badge__rationale">{rationaleText}</p>

      {/* Reviewed dimensions */}
      {verdict.reviewed.length > 0 && (
        <div className="compliance-badge__reviewed">
          {verdict.reviewed.map((r) => (
            <span key={r} className="compliance-badge__chip">
              {r}
            </span>
          ))}
        </div>
      )}

      {/* OJK disclaimers — translated via locale map, fallback to backend string */}
      {verdict.disclaimers.map((d, i) => {
        const localeKey = DISCLAIMER_KEY_MAP[d.trim()];
        const text = localeKey ? (labels[localeKey] as string ?? d) : d;
        return (
          <p key={i} className="compliance-badge__disclaimer">
            {text}
          </p>
        );
      })}
    </div>
  );
}
