import type { ComplianceVerdict } from "@/lib/types";
import type { CopyShape } from "@/lib/copy";

interface Props {
  verdict: ComplianceVerdict;
  labels: CopyShape;
}

// Green for approved outcomes, red for everything else.
const isApproved = (status: string) =>
  status === "approved" || status === "approved_with_conditions";

export default function ComplianceBadge({ verdict, labels }: Props) {
  const approved = isApproved(verdict.status);
  const statusColor = approved ? "var(--signal)" : "var(--err)";
  const statusBg   = approved ? "var(--signal-bg)" : "var(--err-bg)";

  // Status label from locale (e.g. "Disetujui" / "Approved")
  const statusLabel =
    labels.complianceStatus[verdict.status] ?? verdict.status;

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

      {/* Rationale */}
      <p className="compliance-badge__rationale">{verdict.rationale}</p>

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

      {/* OJK disclaimer — always at the bottom */}
      {verdict.disclaimers.map((d, i) => (
        <p key={i} className="compliance-badge__disclaimer">
          {d}
        </p>
      ))}
    </div>
  );
}
