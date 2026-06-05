import type { InsuranceQuote } from "@/lib/types";
import type { CopyShape } from "@/lib/copy";

interface Props {
  quote: InsuranceQuote;
  labels: CopyShape;
}

function fmtIdr(n: number) {
  return `Rp ${n.toLocaleString("id-ID")}`;
}

/**
 * Derive the weekly premium from the stored monthly figure.
 * InsuranceQuote stores premium_idr as monthly (= weekly × 52/12).
 * Reverse: weekly = monthly × 12 / 52.
 */
function weeklyFromMonthly(monthly: number): number {
  return Math.round((monthly * 12) / 52);
}

export default function InsuranceCard({ quote, labels }: Props) {
  const weeklyPremium = weeklyFromMonthly(quote.premium_idr);

  // Sentence-case metric name from locale (e.g. "curah hujan" / "rainfall")
  const metricName = labels.triggerMetric[quote.trigger.metric] ?? quote.trigger.metric;
  const unit = labels.triggerUnit[quote.trigger.metric] ?? quote.trigger.unit;
  const payoutDays = Math.round(quote.payout_multiple);

  // Full trigger sentence assembled from locale parts:
  // ID: "Bila curah hujan >150 mm/24j di Penjaringan"
  // EN: "If rainfall >150 mm/24h in Penjaringan"
  const triggerSentence = `${labels.insuranceTriggerIf} ${metricName} >${quote.trigger.threshold}\u202f${unit} ${labels.insuranceTriggerAt} ${quote.trigger.kecamatan}`;

  return (
    <div className="insurance-card">
      {/* Product header */}
      <div className="insurance-card__header">
        <span className="insurance-card__product">{quote.product_name}</span>
        <span className="insurance-card__tag">
          {labels.insuranceTagParametric}
        </span>
      </div>

      {/* ── Trigger block — THE differentiator. Prominent by design. ── */}
      <div className="insurance-card__trigger insurance-card__trigger--hero">
        <span className="insurance-card__trigger-label">
          {labels.triggerLabel}
        </span>
        <span className="insurance-card__trigger-value">
          {triggerSentence}
        </span>
        <span className="insurance-card__trigger-payout">
          {labels.insuranceAutoPayoutPrefix}{" "}
          <strong>
            {payoutDays} {labels.insuranceDaysIncome}
          </strong>{" "}
          ({fmtIdr(quote.payout_per_event_idr)})
        </span>
        <span className="insurance-card__trigger-src">
          {labels.insuranceSource} {quote.trigger.data_source} ·{" "}
          {labels.insuranceNoClaimNeeded}
        </span>
      </div>

      {/* Key numbers */}
      <div className="insurance-card__metrics">
        {/* Weekly premium — the number gig workers think in */}
        <div className="metric">
          <span className="metric__label">{labels.insuranceWeeklyPremium}</span>
          <span className="metric__value metric__value--accent">
            {fmtIdr(weeklyPremium)}
          </span>
        </div>

        {/* Monthly premium — what gets billed */}
        <div className="metric">
          <span className="metric__label">{labels.premiumLabel}</span>
          <span className="metric__value">{fmtIdr(quote.premium_idr)}</span>
        </div>

        {/* Payout per event */}
        <div className="metric">
          <span className="metric__label">{labels.payoutLabel}</span>
          <span className="metric__value">
            {fmtIdr(quote.payout_per_event_idr)}
          </span>
        </div>

        {/* Max claims in term */}
        <div className="metric">
          <span className="metric__label">{labels.insuranceMaxClaim}</span>
          <span className="metric__value">
            {quote.max_payouts_per_term}× / {quote.coverage_term_days}{" "}
            {labels.insuranceDays}
          </span>
        </div>
      </div>

      {/* Daily earnings context */}
      <div className="insurance-card__context">
        <span className="metric__label">{labels.insuranceDailyEarnings}</span>
        <span className="metric__value">
          {fmtIdr(quote.estimated_daily_earnings_idr)}
        </span>
      </div>
    </div>
  );
}
