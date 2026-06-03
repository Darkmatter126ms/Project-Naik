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

  return (
    <div className="fund-card">
      {/* Header row */}
      <div className="fund-card__header">
        <div>
          <span className="fund-card__type">
            {labels.fundType[pick.fund_type]}
          </span>
          {pick.is_sharia && (
            <span className="fund-card__badge">SYARIAH</span>
          )}
        </div>
        <div
          className="fund-card__score"
          style={{ color: "var(--signal)" }}
          title={labels.fundMatchScore}
        >
          {fmt(pick.match_score, 0)}
          <span className="fund-card__score-label">/100</span>
        </div>
      </div>

      <h3 className="fund-card__name">{pick.fund_name}</h3>
      <p className="fund-card__manager">{pick.manager}</p>

      {/* Metrics grid */}
      <div className="fund-card__metrics">
        <div className="metric">
          <span className="metric__label">1Y Return</span>
          <span className="metric__value" style={{ color: returnColor }}>
            {pick.return_1y_pct !== undefined
              ? `${pick.return_1y_pct >= 0 ? "+" : ""}${fmt(pick.return_1y_pct)}%`
              : "—"}
          </span>
        </div>
        <div className="metric">
          <span className="metric__label">3Y Ann.</span>
          <span className="metric__value">
            {pick.return_3y_annualised_pct !== undefined
              ? `${pick.return_3y_annualised_pct >= 0 ? "+" : ""}${fmt(pick.return_3y_annualised_pct)}%`
              : "—"}
          </span>
        </div>
        <div className="metric">
          <span className="metric__label">Expense</span>
          <span className="metric__value">{fmt(pick.expense_ratio_pct)}%</span>
        </div>
        <div className="metric">
          <span className="metric__label">Risiko</span>
          <span
            className="metric__value"
            style={{ color: RISK_COLOUR[pick.risk_level] }}
          >
            {pick.risk_level.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Allocation bar */}
      {allocationPct !== undefined && (
        <div className="fund-card__alloc">
          <span className="metric__label">Alokasi</span>
          <div className="fund-card__alloc-bar">
            <div
              className="fund-card__alloc-fill"
              style={{ width: `${allocationPct}%` }}
            />
          </div>
          <span className="metric__value">{allocationPct}%</span>
        </div>
      )}

      {/* Min investment */}
      <div className="fund-card__footer">
        <span className="metric__label">Min. investasi</span>
        <span className="metric__value">{fmtIdr(pick.min_investment_idr)}</span>
        {pick.is_ojk_licensed && (
          <span className="fund-card__ojk">✓ OJK</span>
        )}
      </div>

      {pick.rationale && (
        <p className="fund-card__rationale">{pick.rationale}</p>
      )}
    </div>
  );
}
