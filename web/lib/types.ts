// Naik frontend types — mirror api/schemas.py field names exactly.
// When Allen changes a schema field, update here too and grep for usages.

export type Lang = "id" | "en";

export type RiskProfile = "conservative" | "moderate" | "aggressive";
export type WellnessDimension =
  | "diversification"
  | "liquidity"
  | "growth"
  | "risk_management"
  | "tax_efficiency"
  | "emergency_fund"
  | "behavioural_resilience";

export interface WellnessVector {
  diversification: number;
  liquidity: number;
  growth: number;
  risk_management: number;
  tax_efficiency: number;
  emergency_fund: number;
  behavioural_resilience: number;
  priority_gap: WellnessDimension;
  overall_score: number;
  rationale?: string;
}

export type FundType =
  | "pasar_uang"
  | "pendapatan_tetap"
  | "campuran"
  | "saham"
  | "indeks";
export type FundRiskLevel = "low" | "medium" | "high";

export interface FundPick {
  fund_id: string;
  fund_name: string;
  fund_type: FundType;
  manager: string;
  risk_level: FundRiskLevel;
  expense_ratio_pct: number;
  return_1y_pct?: number;
  return_3y_annualised_pct?: number;
  min_investment_idr: number;
  is_ojk_licensed: boolean;
  is_sharia: boolean;
  match_score: number;
  rationale?: string;
}

export interface WealthRecommendation {
  user_id: string;
  risk_profile_used: RiskProfile;
  investment_horizon_years: number;
  recommended_monthly_contribution_idr: number;
  picks: FundPick[];
  allocation_pct?: number[];
  rationale: string;
}

export interface ParametricTrigger {
  metric: "rainfall_mm" | "wind_speed_kmh";
  threshold: number;
  unit: string;
  kecamatan: string;
  observation_window_hours: number;
  data_source: string;
}

export interface InsuranceQuote {
  quote_id: string;
  user_id: string;
  product_name: string;
  trigger: ParametricTrigger;
  estimated_daily_earnings_idr: number;
  payout_multiple: number;
  payout_per_event_idr: number;
  max_payouts_per_term: number;
  coverage_term_days: number;
  premium_idr: number;
  premium_frequency: "monthly" | "annual" | "per_term";
  expected_annual_loss_idr: number;
  loss_ratio_estimate?: number;
}

export type ComplianceStatus =
  | "approved"
  | "approved_with_conditions"
  | "needs_human_review"
  | "rejected";
export type NextStep =
  | "confirm_investment"
  | "confirm_insurance"
  | "confirm_both"
  | "review_only"
  | "escalate_to_human";

export interface ComplianceVerdict {
  verdict_id: string;
  status: ComplianceStatus;
  is_general_guidance: boolean;
  requires_human_confirmation: boolean;
  reviewed: string[];
  flags: string[];
  disclaimers: string[];
  rationale: string;
}

export interface FinalResponse {
  request_id: string;
  user_id: string;
  language: string;
  wellness: WellnessVector;
  wealth?: WealthRecommendation;
  insurance?: InsuranceQuote;
  compliance: ComplianceVerdict;
  narrative: string;
  next_step: NextStep;
  disclaimers: string[];
}

// Persona shape used by the / page selector
export interface Persona {
  id: string;
  name: string;
  age: number;
  kecamatan: string;
  city: string;
  monthly_income_idr: number;
  risk_tolerance: RiskProfile;
  is_gig_worker: boolean;
  tagline_id: string; // one-line Bahasa descriptor
  tagline_en: string;
}
