import type { InsuranceQuote } from "@/lib/types";
import type { CopyShape } from "@/lib/copy";

interface Props {
  quote: InsuranceQuote;
  labels: CopyShape;
}

function fmtIdr(n: number) {
  return `Rp ${n.toLocaleString("id-ID")}`;
}

export default function InsuranceCard({ quote, labels }: Props) {
  const metricLabel =
    quote.trigger.metric === "rainfall_mm" ? "Curah Hujan" : "Kecepatan Angin";

  return (
    <div className="insurance-card">
      <div className="insurance-card__header">
        <span className="insurance-card__product">{quote.product_name}</span>
        <span className="insurance-card__tag">PARAMETRIK</span>
      </div>

      {/* Trigger block — the differentiator vs SiProPer */}
      <div className="insurance-card__trigger">
        <span className="insurance-card__trigger-label">
          {labels.triggerLabel}
        </span>
        <span className="insurance-card__trigger-value">
          {metricLabel} &gt;{quote.trigger.threshold}
          {quote.trigger.unit} di {quote.trigger.kecamatan}
        </span>
        <span className="insurance-card__trigger-src">
          Sumber: {quote.trigger.data_source}
        </span>
      </div>

      {/* Key numbers */}
      <div className="insurance-card__metrics">
        <div className="metric">
          <span className="metric__label">{labels.premiumLabel}</span>
          <span className="metric__value metric__value--accent">
            {fmtIdr(quote.premium_idr)}
          </span>
        </div>
        <div className="metric">
          <span className="metric__label">{labels.payoutLabel}</span>
          <span className="metric__value">
            {fmtIdr(quote.payout_per_event_idr)}
          </span>
        </div>
        <div className="metric">
          <span className="metric__label">Maks. Klaim</span>
          <span className="metric__value">
            {quote.max_payouts_per_term}× / {quote.coverage_term_days} hari
          </span>
        </div>
        <div className="metric">
          <span className="metric__label">Penghasilan Harian</span>
          <span className="metric__value">
            {fmtIdr(quote.estimated_daily_earnings_idr)}
          </span>
        </div>
      </div>

      <p className="insurance-card__note">
        Pembayaran otomatis saat data {quote.trigger.data_source} melampaui
        ambang batas. Tidak perlu klaim.
      </p>
    </div>
  );
}
