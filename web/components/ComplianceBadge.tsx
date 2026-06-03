import type { ComplianceVerdict } from "@/lib/types";
import type { CopyShape } from "@/lib/copy";

interface Props {
  verdict: ComplianceVerdict;
  labels: CopyShape;
}

const STATUS_LABEL: Record<string, string> = {
  approved: "Disetujui",
  approved_with_conditions: "Disetujui (bersyarat)",
  needs_human_review: "Perlu Tinjauan Manusia",
  rejected: "Ditolak",
};

const STATUS_COLOR: Record<string, string> = {
  approved: "var(--signal)",
  approved_with_conditions: "var(--warn)",
  needs_human_review: "var(--warn)",
  rejected: "var(--err)",
};

export default function ComplianceBadge({ verdict, labels }: Props) {
  const color = STATUS_COLOR[verdict.status] ?? "var(--fog)";
  const label = STATUS_LABEL[verdict.status] ?? verdict.status;

  return (
    <div className="compliance-badge">
      {/* Status indicator */}
      <div className="compliance-badge__status">
        <span
          className="compliance-badge__dot"
          style={{ background: color, boxShadow: `0 0 10px ${color}` }}
        />
        <span className="compliance-badge__label" style={{ color }}>
          {label}
        </span>
      </div>

      {/* Human confirmation gate */}
      {verdict.requires_human_confirmation && (
        <div className="compliance-badge__gate">
          <span className="compliance-badge__gate-icon">👤</span>
          <span>
            {labels.confirmedBy} {labels.human} — konfirmasi diperlukan sebelum
            transaksi
          </span>
        </div>
      )}

      {/* OJK framing */}
      <p className="compliance-badge__rationale">{verdict.rationale}</p>

      {/* Reviewed dimensions */}
      <div className="compliance-badge__reviewed">
        {verdict.reviewed.map((r) => (
          <span key={r} className="compliance-badge__chip">
            {r}
          </span>
        ))}
      </div>

      {/* Disclaimer */}
      {verdict.disclaimers.map((d, i) => (
        <p key={i} className="compliance-badge__disclaimer">
          {d}
        </p>
      ))}
    </div>
  );
}
