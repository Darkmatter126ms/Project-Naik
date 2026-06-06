// Thin client for the Naik API. The base URL is read from the public env var
// (inlined at build time by Next). All calls are client-side for this proof.

import type { FinalResponse } from "./types";

export const API_BASE: string =
  (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/+$/, "");

export interface HealthResponse {
  service: string;
  status: string;
  version: string;
  schema_version: string;
  time: string;
  db: "ok" | "not_configured" | "error" | string;
}

export class ApiError extends Error {}

/** Fetch the backend's /health. Throws ApiError on transport/HTTP failure. */
export async function pingHealth(signal?: AbortSignal): Promise<HealthResponse> {
  if (!API_BASE) {
    throw new ApiError(
      "NEXT_PUBLIC_API_BASE_URL is not set. Configure it in Vercel project settings.",
    );
  }
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/health`, { cache: "no-store", signal });
  } catch (err) {
    throw new ApiError(`Network error reaching ${API_BASE}/health: ${String(err)}`);
  }
  if (!resp.ok) {
    throw new ApiError(`Backend returned HTTP ${resp.status} from /health`);
  }
  return (await resp.json()) as HealthResponse;
}

/**
 * POST a DiagnosticInput-shaped payload to /orchestrate and return the
 * validated FinalResponse. Throws ApiError on network failure, non-2xx
 * status, or missing API_BASE. The payload must contain at minimum:
 *   user_id, age, monthly_income_idr, kecamatan, risk_tolerance
 * plus either voice_transcript or at least one transaction
 * (the backend's do-no-harm validator requires one signal).
 */
export async function postOrchestrate(
  payload: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<FinalResponse> {
  if (!API_BASE) {
    throw new ApiError(
      "NEXT_PUBLIC_API_BASE_URL is not set. Configure it in Vercel project settings.",
    );
  }
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/orchestrate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal,
    });
  } catch (err) {
    throw new ApiError(
      `Tidak dapat terhubung ke server (${String(err)}). Periksa koneksi internet Anda.`,
    );
  }
  if (!resp.ok) {
    let detail = "";
    try {
      const body = await resp.json();
      detail = body.detail ?? body.error ?? "";
    } catch {
      /* ignore parse error */
    }
    throw new ApiError(
      `Server mengembalikan HTTP ${resp.status}${detail ? `: ${detail}` : ""}`,
    );
  }
  return (await resp.json()) as FinalResponse;
}

// ── Issuance types (mirror api/schemas.py) ──────────────────────────────────

export interface PersonaIdentity {
  user_id: string;
  applicant_name?: string;
  age: number;
  monthly_income_idr: number;
  kecamatan: string;
  is_gig_worker: boolean;
  risk_tolerance: string;
  household_size: number;
}

export interface IssuanceRequest {
  quote: import("./types").InsuranceQuote;
  persona: PersonaIdentity;
}

export interface IssuanceResult {
  status: string;
  polis_id: string;
  user_id: string;
  applicant_name: string;
  kecamatan: string;
  trigger_metric: string;
  trigger_threshold: number;
  payout_per_event_idr: number;
  premium_idr: number;
  coverage_term_days: number;
  start_date: string;
  end_date: string;
  requires_human_confirmation: boolean;
  issued_at: string;
}

export interface IssuanceResponse {
  form_data: Record<string, string>;
  issuance: IssuanceResult;
}

/**
 * POST /issue — issue a MoneeInsure policy from a pre-computed InsuranceQuote.
 *
 * The quote comes from FinalResponse.insurance (already in state on the
 * results page) and the persona identity from sessionStorage('naik_persona_input').
 * The backend runs the Playwright driver and returns form_data (for the iframe
 * animation) plus the issuance result (polis_id etc.).
 */
export async function postIssue(
  payload: IssuanceRequest,
  signal?: AbortSignal,
): Promise<IssuanceResponse> {
  if (!API_BASE) throw new ApiError("NEXT_PUBLIC_API_BASE_URL is not set.");
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/issue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal,
    });
  } catch (err) {
    throw new ApiError(`Network error reaching /issue: ${String(err)}`);
  }
  if (!resp.ok) {
    let detail = "";
    try { const b = await resp.json(); detail = b.detail ?? b.error ?? ""; } catch { /**/ }
    throw new ApiError(`/issue returned HTTP ${resp.status}${detail ? `: ${detail}` : ""}`);
  }
  return (await resp.json()) as IssuanceResponse;
}
