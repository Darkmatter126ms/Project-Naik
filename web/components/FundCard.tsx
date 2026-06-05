import type { FundPick } from "@/lib/types";
import type { CopyShape } from "@/lib/copy";

interface Props {
  pick: FundPick;
  allocationPct?: number;
  labels: CopyShape;
}

const RISK_COLOUR: Record<string, string> = {
  low: "var(--signal)",
  medium: "var(--warn)",
  high: "var(--err)",
};

function fmt(n: number, decimals = 2) {
  return n.toFixed(decimals);
}

function fmtIdr(n: number) {
  if (n >= 1_000_000_000_000)
    return `Rp ${(n / 1_000_000_000_000).toFixed(1)}T`;
  if (n >= 1_000_000_000) return `Rp ${(n / 1_000_000_000).toFixed(0)}M`;
  if (n >= 1_000_000) return `Rp ${(n / 1_000_000).toFixed(0)}jt`;
  return `Rp ${n.toLocaleString("id-ID")}`;
}

export default function FundCard({ pick, allocationPct, labels }: Props) {
  const returnColor =
    (pick.return_1y_pct ?? 0) >= 0 ? "var(--signal)" : "var(--err)";

  // Localised risk level: "Rendah" / "Low", "Menengah" / "Medium", etc.
  const riskLabel =
    labels.riskLevel[pick.risk_level] ?? pick.risk_level.toUpperCase();

  return (
    <div className="fund-card">
      {/* Header row: type chip + sharia badge | match score */}
      <div className="fund-card__header">
        <div className="fund-card__chips">
          <span className="fund-card__type">
            {labels.fundType[pick.fund_type]}
          </span>
          {pick.is_sharia && (
            <span className="fund-card__badge">SYARIAH ✦</span>
          )}
        </div>
        <div className="fund-card__score-wrap" title={labels.fundMatchScore}>
          <span className="fund-card__score">{fmt(pick.match_score, 0)}</span>
          <span className="fund-card__score-label">/100</span>
        </div>
      </div>

      {/* Score bar — visual match quality indicator */}
      <div className="fund-card__score-bar">
        <div
          className="fund-card__score-bar-fill"
          style={{ width: `${pick.match_score}%` }}
        />
      </div>

      <h3 className="fund-card__name">{pick.fund_name}</h3>
      <p className="fund-card__manager">{pick.manager}</p>

      {/* Metrics grid — all labels from locale */}
      <div className="fund-card__metrics">
        <div className="metric">
          <span className="metric__label">{labels.fund1yReturn}</span>
          <span className="metric__value" style={{ color: returnColor }}>
            {pick.return_1y_pct !== undefined
              ? `${pick.return_1y_pct >= 0 ? "+" : ""}${fmt(pick.return_1y_pct)}%`
              : "—"}
          </span>
        </div>
        <div className="metric">
          <span className="metric__label">{labels.fund3yAnn}</span>
          <span className="metric__value">
            {pick.return_3y_annualised_pct !== undefined
              ? `${pick.return_3y_annualised_pct >= 0 ? "+" : ""}${fmt(pick.return_3y_annualised_pct)}%`
              : "—"}
          </span>
        </div>
        <div className="metric">
          <span className="metric__label">{labels.fundExpense}</span>
          <span className="metric__value">{fmt(pick.expense_ratio_pct)}%</span>
        </div>
        <div className="metric">
          <span className="metric__label">{labels.fundRisk}</span>
          <span
            className="metric__value"
            style={{ color: RISK_COLOUR[pick.risk_level] }}
          >
            {riskLabel}
          </span>
        </div>
      </div>

      {/* Allocation bar */}
      {allocationPct !== undefined && (
        <div className="fund-card__alloc">
          <span className="metric__label">{labels.fundAllocation}</span>
          <div className="fund-card__alloc-bar">
            <div
              className="fund-card__alloc-fill"
              style={{ width: `${allocationPct}%` }}
            />
          </div>
          <span className="metric__value">{allocationPct}%</span>
        </div>
      )}

      {/* Footer: min investment + OJK badge */}
      <div className="fund-card__footer">
        <span className="metric__label">{labels.fundMinInvest}</span>
        <span className="metric__value">{fmtIdr(pick.min_investment_idr)}</span>
        {pick.is_ojk_licensed && (
          <span className="fund-card__ojk">✓ OJK</span>
        )}
      </div>

      {/* Bahasa justification — why this fund fits this user */}
      {pick.rationale && (
        <div className="fund-card__rationale-wrap">
          <span className="fund-card__rationale-label">
            {labels.fundReasoning}
          </span>
          <p className="fund-card__rationale">{pick.rationale}</p>
        </div>
      )}
    </div>
  );
}
